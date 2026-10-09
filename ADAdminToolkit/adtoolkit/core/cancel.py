"""Cooperative cancellation token shared by services and background workers."""
from __future__ import annotations

import threading

from .errors import OperationCancelledError


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise OperationCancelledError()

    def wait(self, seconds: float) -> bool:
        """Sleep up to *seconds*; returns True if cancelled meanwhile."""
        return self._event.wait(seconds)


class Progress:
    """Callback adaptor: services report ``(percent | None, message)``; ``None`` means indeterminate."""

    def __init__(self, callback=None) -> None:
        self._callback = callback

    def __call__(self, percent: int | None, message: str = "") -> None:
        if self._callback:
            self._callback(percent, message)


NULL_PROGRESS = Progress()
