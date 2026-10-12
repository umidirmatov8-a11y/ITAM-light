"""VoiceEngine: microphone → VAD → Whisper → Assistant → speech reply.

Modes
  * push-to-talk: the user presses the button / Ctrl+Alt+Space; the utterance ends on silence
    or on the second press. Pressing is an explicit activation, so no wake word is needed.
  * continuous: the microphone stays open; commands are executed only if they start with the
    wake word (checked by the router) and pass the confidence threshold.

The microphone is opened only while listening, and never when it is disabled in settings.
While A.R.C. speaks, captured audio is discarded (half duplex) so it does not hear itself.
"""
from __future__ import annotations

import collections
import logging
import queue
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ..models import CommandResponse, Status
from ..storage.settings import SettingsStore
from .audio import FRAME_MS, AudioError, AudioInput, SoundDeviceInput, list_input_devices, rms_level
from .models import ModelManager
from .stt import Recognizer, Transcript, WhisperRecognizer, cuda_available
from .tts import Synthesizer, create_synthesizer
from .vad import EnergyVAD, VadConfig

log = logging.getLogger(__name__)

PTT_NO_SPEECH_TIMEOUT_S = 6.0


class VoiceState(str, Enum):
    DISABLED = "disabled"            # microphone switched off in settings
    NOT_INSTALLED = "not_installed"  # no speech recognition model
    IDLE = "idle"
    LISTENING = "listening"          # push-to-talk capture
    CONTINUOUS = "continuous"        # waiting for speech with the wake word
    HEARING = "hearing"              # speech in progress
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


class VoiceError(RuntimeError):
    """User-facing reason why voice cannot start."""


UtteranceHandler = Callable[[str, float, bool], Optional[CommandResponse]]


class VoiceEngine:
    def __init__(self, settings: SettingsStore, models: ModelManager, on_utterance: UtteranceHandler, *,
                 audio_factory: Callable[[Optional[str]], AudioInput] = SoundDeviceInput,
                 recognizer_factory: Callable[[Path, str], Recognizer] = WhisperRecognizer,
                 synth_factory: Callable[[str, str, Path], tuple[Synthesizer, Optional[str]]] = create_synthesizer,
                 hints: Callable[[], list[str]] = lambda: [],
                 device_lister: Callable[[], list[dict]] = list_input_devices):
        self.settings = settings
        self.models = models
        self.on_utterance = on_utterance
        self._audio_factory = audio_factory
        self._recognizer_factory = recognizer_factory
        self._synth_factory = synth_factory
        self._hints = hints
        self._device_lister = device_lister

        self._lock = threading.RLock()
        self._frames: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=1000)
        self._audio: Optional[AudioInput] = None
        self._recognizer: Optional[Recognizer] = None
        self._recognizer_key: tuple = ()
        self._synth: Optional[Synthesizer] = None
        self._synth_key: tuple = ()
        self._vad = EnergyVAD()
        self._ptt = False
        self._ptt_started = 0.0
        self._continuous = False
        self._speaking = False
        self._busy = False
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self.levels: collections.deque[float] = collections.deque([0.0] * 48, maxlen=48)
        self.state = VoiceState.IDLE
        self.message = ""
        self.last_transcript: Optional[dict] = None
        self.tts_warning: Optional[str] = None

    # ================================================================== status
    def availability(self) -> tuple[VoiceState, str]:
        s = self.settings.get()
        if not s.devices.microphone_enabled:
            return VoiceState.DISABLED, "Микрофон выключен в настройках"
        if not self.models.installed(s.voice.stt_model):
            return VoiceState.NOT_INSTALLED, ("Модель распознавания речи не установлена: «Настройки → Голос» "
                                              f"({s.voice.stt_model})")
        return VoiceState.IDLE, ""

    def status(self) -> dict:
        s = self.settings.get()
        base, reason = self.availability()
        with self._lock:
            state = self.state
            message = self.message
            if state in (VoiceState.IDLE, VoiceState.DISABLED, VoiceState.NOT_INSTALLED, VoiceState.ERROR) and \
                    not self._ptt and not self._continuous:
                if base != VoiceState.IDLE:
                    state, message = base, reason
            recognizer = self._recognizer
        return {
            "state": state.value,
            "message": message or {VoiceState.IDLE: "Готов: нажмите кнопку или Ctrl+Alt+Space",
                                   VoiceState.LISTENING: "Слушаю…",
                                   VoiceState.CONTINUOUS: f"Слушаю постоянно — начните со слова «{s.general.wake_word}»",
                                   VoiceState.HEARING: "Слышу речь…",
                                   VoiceState.PROCESSING: "Распознаю…",
                                   VoiceState.SPEAKING: "Отвечаю…"}.get(state, ""),
            "mode": s.voice.mode,
            "ptt": self._ptt,
            "continuous": self._continuous,
            "capturing": self._audio is not None,
            "levels": [round(x, 3) for x in self.levels],
            "stt": {"model": s.voice.stt_model, "installed": self.models.installed(s.voice.stt_model),
                    "device": getattr(recognizer, "device", None), "loaded": bool(getattr(recognizer, "loaded", False))},
            "tts": {"engine": s.voice.tts_engine, "warning": self.tts_warning},
            "last_transcript": self.last_transcript,
        }

    def devices(self) -> list[dict]:
        return self._device_lister()

    def _set(self, state: VoiceState, message: str = "") -> None:
        with self._lock:
            self.state = state
            self.message = message

    # ================================================================== control
    def _check_ready(self) -> None:
        state, reason = self.availability()
        if state != VoiceState.IDLE:
            raise VoiceError(reason)

    def start_ptt(self) -> dict:
        with self._lock:
            self._check_ready()
            if self._busy or self._speaking:
                self.stop_speaking()
            self._open_mic()
            self._vad = self._new_vad()
            self._ptt = True
            self._ptt_started = time.monotonic()
            self._set(VoiceState.LISTENING)
            self._preload()
            return self.status()

    def stop_ptt(self) -> dict:
        """Second press: finish the utterance now."""
        with self._lock:
            if not self._ptt:
                return self.status()
        # processed by the worker after the audio already queued, so no captured speech is lost
        self._frames.put(_FLUSH)
        return self.status()

    def toggle_ptt(self) -> dict:
        return self.stop_ptt() if self._ptt else self.start_ptt()

    def set_continuous(self, enabled: bool) -> dict:
        with self._lock:
            if enabled:
                self._check_ready()
                self._open_mic()
                self._continuous = True
                self._vad = self._new_vad()
                self._set(VoiceState.CONTINUOUS)
                self._preload()
            else:
                self._continuous = False
                if not self._ptt:
                    self._close_mic()
                    self._set(VoiceState.IDLE)
            return self.status()

    def stop_all(self) -> None:
        """Microphone switched off / emergency: close everything immediately."""
        with self._lock:
            self._ptt = False
            self._continuous = False
            self._close_mic()
            self.stop_speaking()
            self._set(VoiceState.IDLE)

    def shutdown(self) -> None:
        self.stop_all()
        self._stop.set()
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=5)

    # ================================================================== speech output
    def _synthesizer(self) -> Synthesizer:
        v = self.settings.get().voice
        key = (v.tts_engine, v.tts_voice)
        if self._synth is None or key != self._synth_key:
            self._synth, self.tts_warning = self._synth_factory(v.tts_engine, v.tts_voice, self.models.models_dir)
            self._synth_key = key
        return self._synth

    def speak(self, text: str, force: bool = False) -> bool:
        s = self.settings.get()
        if not text or s.voice.tts_engine == "off" or (s.profile.silent and not force):
            return False
        synth = self._synthesizer()
        previous = self.state
        self._speaking = True
        self._set(VoiceState.SPEAKING)
        try:
            synth.speak(text, s.voice.tts_rate, s.voice.tts_volume)
            return synth.name != "off"
        except Exception as exc:
            log.warning("tts failed: %s", exc)
            self.tts_warning = f"Синтез речи недоступен: {exc}"
            return False
        finally:
            self._speaking = False
            self._drain()
            if self.state == VoiceState.SPEAKING:
                self._set(previous if previous != VoiceState.SPEAKING else VoiceState.IDLE)

    def stop_speaking(self) -> None:
        if self._synth is not None:
            try:
                self._synth.stop()
            except Exception:
                pass

    # ================================================================== internals
    def _new_vad(self) -> EnergyVAD:
        v = self.settings.get().voice
        vad = EnergyVAD(VadConfig(sensitivity=v.vad_sensitivity, silence_ms=v.silence_ms,
                                  max_utterance_s=v.max_utterance_s))
        if self._vad.calibrated:  # keep the learned noise floor between activations
            vad.noise_db, vad.calibrated = self._vad.noise_db, True
        return vad

    def _open_mic(self) -> None:
        if self._audio is not None:
            return
        device = self.settings.get().voice.input_device
        audio = self._audio_factory(device)
        try:
            audio.start(self._on_frame)
        except AudioError as exc:
            self._set(VoiceState.ERROR, str(exc))
            raise VoiceError(str(exc)) from exc
        self._audio = audio
        self._ensure_worker()

    def _close_mic(self) -> None:
        audio, self._audio = self._audio, None
        if audio is not None:
            audio.stop()
        self.levels.extend([0.0] * 8)

    def _on_frame(self, frame: np.ndarray) -> None:
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            pass  # recognition is behind; dropping audio is better than growing memory

    def _drain(self) -> None:
        dropped = 0
        while True:
            try:
                item = self._frames.get_nowait()
            except queue.Empty:
                break
            if item is _FLUSH:
                continue
            dropped += 1
        self._vad.reset()

    def _ensure_worker(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._stop.clear()
            self._worker = threading.Thread(target=self._loop, name="voice-engine", daemon=True)
            self._worker.start()

    def _preload(self) -> None:
        def load():
            try:
                rec = self._get_recognizer()
                loader = getattr(rec, "load", None)
                if loader:
                    loader()
            except Exception as exc:
                log.warning("speech model preload failed: %s", exc)
                self._set(VoiceState.ERROR, str(exc))
        threading.Thread(target=load, name="whisper-preload", daemon=True).start()

    def _get_recognizer(self) -> Recognizer:
        v = self.settings.get().voice
        key = (v.stt_model, v.stt_device)
        with self._lock:
            if self._recognizer is None or self._recognizer_key != key:
                self._recognizer = self._recognizer_factory(self.models.path(v.stt_model), v.stt_device)
                self._recognizer_key = key
            return self._recognizer

    def _loop(self) -> None:
        last_settings_check = 0.0
        while not self._stop.is_set():
            try:
                item = self._frames.get(timeout=0.2)
            except queue.Empty:
                item = None
            now = time.monotonic()
            if now - last_settings_check > 1.0:
                last_settings_check = now
                if not self.settings.get().devices.microphone_enabled and (self._ptt or self._continuous):
                    self.stop_all()
                    self._set(VoiceState.DISABLED, "Микрофон выключен в настройках")
                if self._ptt and not self._vad.in_speech and now - self._ptt_started > PTT_NO_SPEECH_TIMEOUT_S:
                    self._ptt = False
                    self._after_utterance(heard=False, message="Речь не услышана")
            if item is None:
                continue
            if item is _FLUSH:
                if self._ptt:
                    self._ptt = False
                    utterance = self._vad.flush()
                    if utterance is not None:
                        self._handle(utterance, explicit=True)
                    else:
                        self._after_utterance(heard=False, message="Речь не услышана")
                continue
            self.levels.append(rms_level(item))
            if self._speaking or self._busy or not (self._ptt or self._continuous):
                continue
            utterance = self._vad.process(item)
            with self._lock:
                if self._vad.in_speech and self.state in (VoiceState.CONTINUOUS, VoiceState.LISTENING):
                    self.state = VoiceState.HEARING
            if utterance is not None:
                explicit = self._ptt
                self._ptt = False
                self._handle(utterance, explicit=explicit)

    def _handle(self, audio: np.ndarray, explicit: bool) -> None:
        self._busy = True
        self._set(VoiceState.PROCESSING)
        try:
            transcript: Transcript = self._get_recognizer().transcribe(audio, self._hints())
        except Exception as exc:
            log.exception("speech recognition failed")
            self._busy = False
            self._after_utterance(heard=False, message=f"Ошибка распознавания: {exc}", error=True)
            return
        self.last_transcript = {"text": transcript.text, "confidence": round(transcript.confidence, 3),
                                "duration_s": round(transcript.duration_s, 2), "elapsed_s": round(transcript.elapsed_s, 2),
                                "ts": time.time(), "explicit": explicit}
        response: Optional[CommandResponse] = None
        if transcript.text:
            try:
                response = self.on_utterance(transcript.text, transcript.confidence, explicit)
            except Exception:
                log.exception("assistant failed on voice input")
        self._busy = False
        if response is not None and response.status != Status.IGNORED:
            self.speak(response.message)
        elif explicit and not transcript.text:
            self._after_utterance(heard=False, message="Речь не распознана")
            return
        self._after_utterance(heard=True)

    def _after_utterance(self, heard: bool, message: str = "", error: bool = False) -> None:
        with self._lock:
            self._drain()
            if self._continuous:
                self._set(VoiceState.CONTINUOUS, message)
            else:
                self._close_mic()
                self._set(VoiceState.ERROR if error else VoiceState.IDLE, message)


_FLUSH = object()  # queue marker: push-to-talk released


def stt_device_info() -> dict:
    return {"cuda": cuda_available()}


__all__ = ["VoiceEngine", "VoiceError", "VoiceState", "FRAME_MS", "stt_device_info"]
