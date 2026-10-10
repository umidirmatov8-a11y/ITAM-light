"""Background execution of directory operations.

All LDAP / network work runs in ``QThreadPool`` workers; results are delivered to the GUI thread through queued Qt
signals, so the interface never blocks. Every task gets a :class:`CancelToken`; long operations check it between
pages / objects (a single in-flight LDAP request cannot be interrupted — it ends by the configured timeout).
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..core.cancel import CancelToken, Progress
from ..core.errors import OperationCancelledError, ToolkitError
from ..security.masking import mask_text

log = logging.getLogger(__name__)


class TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(object)
    progress = Signal(object, str)


class Task(QRunnable):
    def __init__(self, fn: Callable[[CancelToken, Progress], Any], title: str = "", cancellable: bool = True,
                 silent: bool = False):
        super().__init__()
        self.setAutoDelete(False)
        self.fn = fn
        self.title = title
        self.cancellable = cancellable
        self.silent = silent
        self.cancel_token = CancelToken()
        self.signals = TaskSignals()

    def run(self) -> None:  # executed in a worker thread
        progress = Progress(lambda p, m: self.signals.progress.emit(p, m))
        try:
            result = self.fn(self.cancel_token, progress)
        except (OperationCancelledError, ToolkitError) as exc:
            # expected, already user-facing errors: no traceback in the log
            log.info("Задача «%s» завершилась: %s", self.title, mask_text(getattr(exc, "message", str(exc))))
            self.signals.failed.emit(exc)
        except Exception as exc:  # noqa: BLE001 - delivered to the GUI as an error dialog
            log.error("Ошибка фоновой задачи «%s»: %s", self.title, mask_text(traceback.format_exc()))
            self.signals.failed.emit(exc)
        else:
            self.signals.finished.emit(result)

    def cancel(self) -> None:
        self.cancel_token.cancel()


class TaskManager(QObject):
    """Tracks running tasks for the status bar (progress, cancel)."""

    changed = Signal()
    progress = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(4, self.pool.maxThreadCount()))
        self.active: list[Task] = []

    def run(self, fn: Callable[[CancelToken, Progress], Any], on_done: Callable[[Any], None] | None = None,
            on_error: Callable[[BaseException], None] | None = None, *, title: str = "", cancellable: bool = True,
            silent: bool = False) -> Task:
        task = Task(fn, title, cancellable, silent)
        self.active.append(task)

        def finished(result):
            self._remove(task)
            if on_done:
                on_done(result)

        def failed(exc):
            self._remove(task)
            if on_error:
                on_error(exc)

        def prog(p, m):
            if not task.silent:
                self.progress.emit(p, m or task.title)

        task.signals.finished.connect(finished)
        task.signals.failed.connect(failed)
        task.signals.progress.connect(prog)
        self.changed.emit()
        if not silent:
            self.progress.emit(None, title)
        self.pool.start(task)
        return task

    def _remove(self, task: Task) -> None:
        if task in self.active:
            self.active.remove(task)
        self.changed.emit()

    def visible_tasks(self) -> list[Task]:
        return [t for t in self.active if not t.silent]

    def cancel_all(self) -> None:
        for t in list(self.active):
            if t.cancellable:
                t.cancel()

    def wait_all(self, msecs: int = 5000) -> bool:
        return self.pool.waitForDone(msecs)
