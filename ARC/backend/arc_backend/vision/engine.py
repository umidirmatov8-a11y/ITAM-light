"""VisionEngine: camera → MediaPipe hand landmarks → gesture → bound safe action.

* The camera is opened only while gesture control is on, and never when it is disabled in settings.
* Frames live only in memory. A JPEG preview exists only in setup mode (camera check), expires
  automatically, and is served only to the local UI.
* Every action goes through the Permission Manager with Source.GESTURE (category A, gesture_allowed).
"""
from __future__ import annotations

import collections
import logging
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from ..storage.settings import GestureBinding, SettingsStore
from ..voice.models import ModelManager
from .camera import Camera, CameraError, OpenCvCamera
from .gestures import GESTURE_TITLES, Observation, classify, largest_hand
from .state import GestureConfig, GestureStateMachine
from .tracker import HandTracker, MediaPipeTracker

log = logging.getLogger(__name__)

MODEL_ID = "mediapipe-hand"
PREVIEW_TTL_S = 120.0
CALIBRATION_S = 3.0
DARK_BRIGHTNESS = 45.0
HAND_CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
                    (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]

Dispatch = Callable[[str, GestureBinding], dict]


class VisionState(str, Enum):
    DISABLED = "disabled"
    NOT_INSTALLED = "not_installed"
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CALIBRATING = "calibrating"
    ERROR = "error"


class VisionError(RuntimeError):
    pass


class VisionEngine:
    def __init__(self, settings: SettingsStore, models: ModelManager, dispatch: Dispatch, *,
                 camera_factory: Callable[[int], Camera] = OpenCvCamera,
                 tracker_factory: Callable[[Path], HandTracker] = MediaPipeTracker,
                 clock: Callable[[], float] = time.monotonic):
        self.settings = settings
        self.models = models
        self.dispatch = dispatch
        self._camera_factory = camera_factory
        self._tracker_factory = tracker_factory
        self._clock = clock
        self._lock = threading.RLock()
        self._camera: Optional[Camera] = None
        self._tracker: Optional[HandTracker] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._sm = GestureStateMachine()
        self.state = VisionState.IDLE
        self.message = ""
        self.paused = False
        self.fps = 0.0
        self.brightness: Optional[float] = None
        self.observation: Optional[Observation] = None
        self.landmarks: Optional[list[list[float]]] = None
        self.events: collections.deque[dict] = collections.deque(maxlen=20)
        self._event_id = 0
        self._preview_until = 0.0
        self._preview_jpeg: Optional[bytes] = None
        self._calibration: Optional[dict[str, Any]] = None

    # ================================================================== status
    def availability(self) -> tuple[VisionState, str]:
        s = self.settings.get()
        if not s.devices.camera_enabled:
            return VisionState.DISABLED, "Камера выключена в настройках"
        if not self.models.installed(MODEL_ID):
            return VisionState.NOT_INSTALLED, "Модель распознавания рук не установлена: «Настройки → Жесты»"
        return VisionState.IDLE, ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict:
        base, reason = self.availability()
        with self._lock:
            state, message = self.state, self.message
            if not self.running and state not in (VisionState.ERROR,) and base != VisionState.IDLE:
                state, message = base, reason
            obs = self.observation
            effective = self._sm.candidate if self.running else "none"
            calibration = dict(self._calibration) if self._calibration else None
        s = self.settings.get().vision
        return {
            "state": state.value,
            "message": message or {VisionState.IDLE: "Жесты выключены", VisionState.RUNNING: "Слежу за жестами",
                                   VisionState.PAUSED: "Пауза: покажите жест паузы ещё раз, чтобы продолжить"}.get(state, ""),
            "running": self.running,
            "paused": self.paused,
            "fps": round(self.fps, 1),
            "brightness": None if self.brightness is None else round(self.brightness),
            "dark": self.brightness is not None and self.brightness < DARK_BRIGHTNESS,
            "gesture": effective,
            "gesture_title": GESTURE_TITLES.get(effective, effective),
            "raw_gesture": obs.gesture if obs else "none",
            "confidence": round(obs.confidence, 2) if obs else 0.0,
            "fingers": obs.fingers if obs else {},
            "progress": round(self._sm.progress, 2),
            "landmarks": self.landmarks,
            "zone": s.zone,
            "events": list(self.events),
            "preview": self._clock() < self._preview_until,
            "calibration": s.calibration.model_dump() if s.calibration else None,
            "calibrating": calibration,
            "model_installed": self.models.installed(MODEL_ID),
        }

    # ================================================================== control
    def start(self) -> dict:
        with self._lock:
            if self.running:
                return self.status()
            state, reason = self.availability()
            if state != VisionState.IDLE:
                raise VisionError(reason)
            s = self.settings.get().vision
            try:
                tracker = self._tracker_factory(self.models.path(MODEL_ID))
            except Exception as exc:
                self._set(VisionState.ERROR, f"Не удалось загрузить модель рук: {exc}")
                raise VisionError(self.message) from exc
            camera = self._camera_factory(s.camera_index)
            try:
                camera.open()
            except CameraError as exc:
                tracker.close()
                self._set(VisionState.ERROR, str(exc))
                raise VisionError(str(exc)) from exc
            self._tracker, self._camera = tracker, camera
            self._sm = GestureStateMachine(self._config())
            self.paused = False
            self._stop.clear()
            self._set(VisionState.RUNNING)
            self._thread = threading.Thread(target=self._loop, name="vision-engine", daemon=True)
            self._thread.start()
            return self.status()

    def stop(self, message: str = "", error: bool = False) -> dict:
        thread = self._thread
        self._stop.set()
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5)
        with self._lock:
            self._release()
            self._thread = None
            self.landmarks, self.observation, self.fps = None, None, 0.0
            self._preview_jpeg = None
            self._set(VisionState.ERROR if error else VisionState.IDLE, message)
        return self.status()

    def shutdown(self) -> None:
        self.stop()

    def set_paused(self, paused: bool) -> dict:
        with self._lock:
            self.paused = paused
            if self.running:
                self._set(VisionState.PAUSED if paused else VisionState.RUNNING)
            self._sm.reset()
        return self.status()

    def set_preview(self, enabled: bool) -> dict:
        with self._lock:
            self._preview_until = self._clock() + PREVIEW_TTL_S if enabled else 0.0
            if not enabled:
                self._preview_jpeg = None
        return self.status()

    def preview_jpeg(self) -> Optional[bytes]:
        if self._clock() >= self._preview_until:
            self._preview_jpeg = None
            return None
        return self._preview_jpeg

    def calibrate(self) -> dict:
        if not self.running:
            raise VisionError("Сначала включите жесты")
        with self._lock:
            self._calibration = {"started": self._clock(), "samples": [], "progress": 0.0,
                                 "message": "Покажите открытую ладонь на обычном расстоянии"}
            self._set(VisionState.CALIBRATING)
        return self.status()

    # ================================================================== internals
    def _config(self) -> GestureConfig:
        v = self.settings.get().vision
        min_scale = v.calibration.palm_scale * 0.5 if v.calibration else 0.0
        return GestureConfig(confidence=v.confidence, hold_ms=v.hold_ms, cooldown_ms=v.cooldown_ms,
                             min_interval_ms=v.min_interval_ms, zone=list(v.zone), zone_hold_ms=v.zone_hold_ms,
                             min_palm_scale=min_scale)

    def _set(self, state: VisionState, message: str = "") -> None:
        self.state, self.message = state, message

    def _release(self) -> None:
        camera, self._camera = self._camera, None
        tracker, self._tracker = self._tracker, None
        if camera is not None:
            camera.close()
        if tracker is not None:
            tracker.close()

    def _pause_gesture(self) -> Optional[str]:
        for gesture, binding in self.settings.get().vision.bindings.items():
            if binding.enabled and binding.action == "gestures.pause_toggle":
                return gesture
        return None

    def _loop(self) -> None:
        failures = 0
        last_settings = 0.0
        frame_times: collections.deque[float] = collections.deque(maxlen=20)
        try:
            while not self._stop.is_set():
                started = self._clock()
                s = self.settings.get()
                if started - last_settings > 1.0:
                    last_settings = started
                    if not s.devices.camera_enabled:
                        self._stop.set()
                        threading.Thread(target=self.stop, args=("Камера выключена в настройках",), daemon=True).start()
                        return
                    self._sm.config = self._config()
                camera, tracker = self._camera, self._tracker
                if camera is None or tracker is None:
                    return
                frame = camera.read()
                if frame is None:
                    failures += 1
                    if failures > 30:
                        self._set(VisionState.ERROR, "Камера перестала отдавать изображение")
                        threading.Thread(target=self.stop, args=(self.message, True), daemon=True).start()
                        return
                    time.sleep(0.05)
                    continue
                failures = 0
                self._process(frame, s, started)
                frame_times.append(started)
                if len(frame_times) > 1:
                    span = frame_times[-1] - frame_times[0]
                    self.fps = (len(frame_times) - 1) / span if span > 0 else 0.0
                delay = 1.0 / s.vision.fps - (self._clock() - started)
                if delay > 0:
                    self._stop.wait(delay)
        except Exception:
            log.exception("vision loop crashed")
            self._set(VisionState.ERROR, "Сбой модуля жестов (подробности в журнале ядра)")
            threading.Thread(target=self.stop, args=(self.message, True), daemon=True).start()

    def _process(self, frame: np.ndarray, s, now: float) -> None:
        if s.vision.mirror:
            frame = frame[:, ::-1]
        rgb = frame[:, :, ::-1]  # OpenCV gives BGR
        gray_mean = float(frame.mean())
        self.brightness = gray_mean if self.brightness is None else self.brightness * 0.9 + gray_mean * 0.1
        tracker = self._tracker
        if tracker is None:
            return
        hands = tracker.detect(rgb, int(now * 1000))
        hand = largest_hand(hands)
        obs = classify(*hand) if hand else None
        self.observation = obs
        self.landmarks = [[round(x, 4), round(y, 4)] for x, y, _z in hand[0]] if hand else None
        if self._calibration is not None:
            self._calibrate_step(obs, gray_mean, now)
        elif not (self.paused and self._pause_gesture() is None):
            allowed = {self._pause_gesture()} if self.paused else None
            fired = self._sm.feed(obs, now * 1000, allowed=allowed)  # type: ignore[arg-type]
            if fired:
                self._fire(fired)
        if now < self._preview_until:
            self._preview_jpeg = self._render_preview(frame, hand)

    def _fire(self, gesture: str) -> None:
        binding = self.settings.get().vision.bindings.get(gesture)
        title = GESTURE_TITLES.get(gesture, gesture)
        event: dict[str, Any] = {"gesture": gesture, "title": title, "ts": time.time()}
        if binding is None or not binding.enabled:
            event.update(action=None, status="ignored", message=f"{title}: действие не назначено")
        elif binding.action == "gestures.pause_toggle":
            self.set_paused(not self.paused)
            event.update(action=binding.action, status="done",
                         message="Жесты на паузе" if self.paused else "Жесты снова активны")
        else:
            try:
                result = self.dispatch(gesture, binding)
            except Exception as exc:
                log.exception("gesture dispatch failed")
                result = {"status": "error", "message": f"Ошибка: {exc}"}
            event.update(action=binding.action, **result)
        self._event_id += 1
        event["id"] = self._event_id
        self.events.append(event)
        log.info("gesture %s -> %s (%s)", gesture, event.get("action"), event.get("status"))

    def _calibrate_step(self, obs: Optional[Observation], brightness: float, now: float) -> None:
        cal = self._calibration
        assert cal is not None
        if obs is not None and obs.gesture == "open_palm" and obs.confidence >= 0.6:
            cal["samples"].append((obs.palm_scale, brightness))
        elapsed = now - cal["started"]
        cal["progress"] = round(min(1.0, elapsed / CALIBRATION_S), 2)
        if elapsed < CALIBRATION_S:
            return
        samples = cal["samples"]
        if len(samples) < 5:
            self._calibration = None
            self._set(VisionState.PAUSED if self.paused else VisionState.RUNNING,
                      "Калибровка не удалась: ладонь не была видна. Попробуйте ещё раз.")
            return
        palm = float(np.median([x[0] for x in samples]))
        light = float(np.mean([x[1] for x in samples]))
        self.settings.update({"vision": {"calibration": {"palm_scale": round(palm, 4), "brightness": round(light, 1),
                                                         "ts": time.time()}}})
        self._calibration = None
        self._sm.config = self._config()
        hint = " Освещение слабое — добавьте свет." if light < DARK_BRIGHTNESS else ""
        self._set(VisionState.PAUSED if self.paused else VisionState.RUNNING,
                  f"Калибровка завершена: руки дальше ~2× от этого расстояния игнорируются.{hint}")

    def _render_preview(self, frame: np.ndarray, hand) -> Optional[bytes]:
        try:
            import cv2  # type: ignore
        except ImportError:
            return None
        img = np.ascontiguousarray(frame).copy()
        h, w = img.shape[:2]
        zone = self.settings.get().vision.zone
        cv2.rectangle(img, (int(zone[0] * w), int(zone[1] * h)), (int(zone[2] * w), int(zone[3] * h)), (0, 140, 255), 1)
        if hand is not None:
            pts = [(int(x * w), int(y * h)) for x, y, _z in hand[0]]
            for a, b in HAND_CONNECTIONS:
                cv2.line(img, pts[a], pts[b], (0, 176, 255), 2)
            for pt in pts:
                cv2.circle(img, pt, 3, (120, 230, 140), -1)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        return buf.tobytes() if ok else None
