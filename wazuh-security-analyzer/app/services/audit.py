"""Security audit trail (JSON lines in logs/audit.log)."""

from __future__ import annotations

import getpass
import logging
from typing import Any

from app.core.logging_setup import AUDIT_LOGGER

_audit = logging.getLogger(AUDIT_LOGGER)


def _current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def audit(event: str, **fields: Any) -> None:
    """Record a security-relevant action, e.g. data sent to an external provider.

    Never pass secrets or raw log content here - only metadata.
    """
    payload = {"os_user": _current_user(), **fields}
    _audit.info(event, extra={"audit_fields": payload})
