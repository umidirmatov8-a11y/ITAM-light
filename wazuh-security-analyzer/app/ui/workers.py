"""Background execution so the GUI never blocks (analysis, AI, enrichment, export)."""

from __future__ import annotations

import logging
import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.core.errors import AnalysisCancelled

log = logging.getLogger(__name__)


class TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(object)


class Task(QRunnable):
    """Runs ``fn(progress_callback, cancel_event)`` in the global thread pool."""

    def __init__(self, fn: Callable[[Callable[[Any], None], threading.Event], Any]):
        super().__init__()
        self.fn = fn
        self.signals = TaskSignals()
        self.cancel_event = threading.Event()
        self.setAutoDelete(False)

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            result = self.fn(self.signals.progress.emit, self.cancel_event)
        except AnalysisCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:
            log.error("Background task failed: %s\n%s", exc, traceback.format_exc())
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)


_running: set[Task] = set()


def start(task: Task) -> Task:
    """Start a task and keep a reference until it completes."""
    _running.add(task)
    for sig in (task.signals.finished, task.signals.failed, task.signals.cancelled):
        sig.connect(lambda *_args, t=task: _running.discard(t))
    QThreadPool.globalInstance().start(task)
    return task
