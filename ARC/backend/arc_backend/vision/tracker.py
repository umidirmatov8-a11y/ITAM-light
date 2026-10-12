"""Hand landmark detection with MediaPipe Tasks (HandLandmarker), fully local."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)

MODEL_FILE = "hand_landmarker.task"


class HandTracker(Protocol):
    def detect(self, rgb: np.ndarray, timestamp_ms: int) -> list[tuple[np.ndarray, float]]: ...
    def close(self) -> None: ...


class MediaPipeTracker:
    def __init__(self, model_dir: Path, max_hands: int = 2, video: bool = True):
        model = Path(model_dir) / MODEL_FILE
        if not model.is_file():
            raise RuntimeError("Модель распознавания рук не установлена: «Настройки → Жесты → Загрузить»")
        import mediapipe as mp  # type: ignore
        from mediapipe.tasks.python import BaseOptions, vision  # type: ignore
        self._mp_image = mp.Image
        self._mp_format = mp.ImageFormat
        self._video = video
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)), num_hands=max_hands,
            running_mode=vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE,
            min_hand_detection_confidence=0.5, min_hand_presence_confidence=0.5, min_tracking_confidence=0.5)
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_ts = -1

    def detect(self, rgb: np.ndarray, timestamp_ms: int) -> list[tuple[np.ndarray, float]]:
        image = self._mp_image(image_format=self._mp_format.SRGB, data=np.ascontiguousarray(rgb))
        if self._video:
            timestamp_ms = max(timestamp_ms, self._last_ts + 1)  # MediaPipe requires increasing timestamps
            self._last_ts = timestamp_ms
            result = self._landmarker.detect_for_video(image, timestamp_ms)
        else:
            result = self._landmarker.detect(image)
        hands = []
        for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            points = np.array([[lm.x, lm.y, lm.z] for lm in landmarks], dtype=np.float64)
            hands.append((points, float(handedness[0].score) if handedness else 1.0))
        return hands

    def close(self) -> None:
        landmarker, self._landmarker = getattr(self, "_landmarker", None), None
        if landmarker is not None:
            try:
                landmarker.close()
            except Exception as exc:
                log.debug("landmarker close: %s", exc)
