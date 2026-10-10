"""Application operation journal.

Records only the operations performed *through this application*: Windows user, time, operation type, target object,
result and error. It is NOT a full audit of Active Directory changes — for that use the Security logs of the domain
controllers (see the "Журналы безопасности" module).
"""
from __future__ import annotations

import getpass
import logging
import os
import threading
import uuid
from contextlib import contextmanager

from ..core.errors import OperationCancelledError, ToolkitError, describe_exception
from ..storage.database import Database

log = logging.getLogger(__name__)

RESULT_SUCCESS = "success"
RESULT_FAILED = "failed"
RESULT_DRY_RUN = "dry-run"
RESULT_SKIPPED = "skipped"
RESULT_CANCELLED = "cancelled"

RESULT_LABELS = {RESULT_SUCCESS: "Успешно", RESULT_FAILED: "Ошибка", RESULT_DRY_RUN: "Dry Run (смоделировано)",
                 RESULT_SKIPPED: "Пропущено", RESULT_CANCELLED: "Отменено"}

JOURNAL_DISCLAIMER = ("Журнал содержит только операции, выполненные через AD Admin Toolkit на этом компьютере. "
                      "Это не полный аудит изменений Active Directory: используйте журналы безопасности "
                      "контроллеров домена (события 4720–4767, 5136 и др.).")


def windows_user() -> str:
    user = os.environ.get("USERNAME") or getpass.getuser()
    domain = os.environ.get("USERDOMAIN")
    return f"{domain}\\{user}" if domain else user


class OperationJournal:
    def __init__(self, db: Database):
        self.db = db
        self.context = {"ldap_identity": "", "domain": "", "dc": ""}
        self.listeners = []
        self._local = threading.local()

    @contextmanager
    def batch(self, batch_id: str):
        """All records made by this thread inside the block carry *batch_id* (bulk operations)."""
        prev = getattr(self._local, "batch", None)
        self._local.batch = batch_id
        try:
            yield batch_id
        finally:
            self._local.batch = prev

    def set_context(self, *, ldap_identity: str = "", domain: str = "", dc: str = "") -> None:
        self.context = {"ldap_identity": ldap_identity, "domain": domain, "dc": dc}

    def record(self, operation: str, target: str, result: str, *, error: str | None = None,
               details: dict | None = None, batch_id: str | None = None) -> int:
        batch_id = batch_id or getattr(self._local, "batch", None)
        try:
            rid = self.db.add_operation(windows_user=windows_user(), operation=operation, target=target, result=result,
                                        error=error, details=details, batch_id=batch_id, **self.context)
        except Exception:  # journal failures must be visible in the log but never mask the real operation result
            log.exception("Не удалось записать операцию в журнал приложения")
            return -1
        for listener in list(self.listeners):
            try:
                listener()
            except Exception:
                pass
        return rid

    @contextmanager
    def track(self, operation: str, target: str, details: dict | None = None, batch_id: str | None = None):
        """Context manager: records success, or failure with the masked error, then re-raises."""
        try:
            yield
        except OperationCancelledError:
            self.record(operation, target, RESULT_CANCELLED, details=details, batch_id=batch_id)
            raise
        except ToolkitError as exc:
            self.record(operation, target, RESULT_FAILED, error=exc.message + (f" | {exc.details}" if exc.details else ""),
                        details=details, batch_id=batch_id)
            raise
        except Exception as exc:
            self.record(operation, target, RESULT_FAILED, error=describe_exception(exc), details=details, batch_id=batch_id)
            raise
        else:
            self.record(operation, target, RESULT_SUCCESS, details=details, batch_id=batch_id)

    @staticmethod
    def new_batch_id() -> str:
        return uuid.uuid4().hex[:12]
