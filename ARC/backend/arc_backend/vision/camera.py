"""Camera capture with OpenCV. Frames stay in memory; nothing is written to disk."""
from __future__ import annotations

import logging
import sys
import threading
from typing import Optional, Protocol

import numpy as np

log = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """User-facing (Russian) message about the camera."""


class Camera(Protocol):
    def open(self) -> None: ...
    def read(self) -> Optional[np.ndarray]: ...
    def close(self) -> None: ...


def _cv2():
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise CameraError(f"OpenCV недоступен: {exc}") from exc
    return cv2


class OpenCvCamera:
    def __init__(self, index: int = 0, width: int = 640, height: int = 480):
        self.index, self.width, self.height = index, width, height
        self._cap = None
        self._lock = threading.Lock()

    def open(self) -> None:
        cv2 = _cv2()
        with self._lock:
            if self._cap is not None:
                return
            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            cap = cv2.VideoCapture(self.index, backend)
            if not cap.isOpened():
                cap.release()
                raise CameraError(f"Камера {self.index} не найдена или занята другой программой. "
                                  "Проверьте «Конфиденциальность → Камера».")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            ok, _frame = cap.read()
            if not ok:
                cap.release()
                raise CameraError(f"Камера {self.index} не отдаёт изображение")
            self._cap = cap
            log.info("camera %s opened", self.index)

    def read(self) -> Optional[np.ndarray]:
        cap = self._cap
        if cap is None:
            return None
        ok, frame = cap.read()
        return frame if ok else None

    def close(self) -> None:
        with self._lock:
            cap, self._cap = self._cap, None
        if cap is not None:
            cap.release()
            log.info("camera %s closed", self.index)


def probe_cameras(max_index: int = 4) -> list[dict]:
    """Opens each index briefly (only on explicit request from the setup screen)."""
    found = []
    try:
        cv2 = _cv2()
    except CameraError:
        return found
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    for index in range(max_index + 1):
        cap = cv2.VideoCapture(index, backend)
        try:
            if cap.isOpened():
                ok, frame = cap.read()
                if ok and frame is not None:
                    h, w = frame.shape[:2]
                    found.append({"index": index, "name": f"Камера {index}", "resolution": f"{w}×{h}"})
        finally:
            cap.release()
    return found
