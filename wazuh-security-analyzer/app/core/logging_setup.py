"""Application logging: application.log, errors.log, analysis.log and audit.log."""

from __future__ import annotations

import json
import logging
import logging.handlers
import re
from datetime import datetime, timezone
from pathlib import Path

from app.core import paths

ANALYSIS_LOGGER = "wsa.analysis"
AUDIT_LOGGER = "wsa.audit"

_configured = False

# Defensive redaction so that a secret accidentally passed to a log call never hits disk.
_REDACT_PATTERNS = [
    re.compile(r"(?i)(x-apikey|x-api-key|api[_-]?key|authorization|key|token|password)(\"?\s*[:=]\s*\"?)([^\s\",&]+)"),
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
]


def redact(text: str) -> str:
    text = _REDACT_PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    text = _REDACT_PATTERNS[1].sub("Bearer ***", text)
    text = _REDACT_PATTERNS[2].sub("sk-***", text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "event": record.getMessage(),
        }
        extra = getattr(record, "audit_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return redact(json.dumps(payload, ensure_ascii=False, default=str))


def _rotating(path: Path, level: int, max_mb: int, backups: int, formatter: logging.Formatter) -> logging.Handler:
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=max_mb * 1024 * 1024, backupCount=backups, encoding="utf-8", delay=True
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def setup_logging(level: str = "INFO", max_mb: int = 10, backups: int = 5, console: bool = False,
                  log_dir: Path | None = None) -> Path:
    """Configure logging once. Returns the log directory."""
    global _configured
    log_dir = log_dir or paths.logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    if _configured:
        logging.getLogger().setLevel(level)
        return log_dir

    fmt = RedactingFormatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(_rotating(log_dir / "application.log", logging.DEBUG, max_mb, backups, fmt))
    root.addHandler(_rotating(log_dir / "errors.log", logging.ERROR, max_mb, backups, fmt))
    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        stream.setLevel(level)
        root.addHandler(stream)

    analysis = logging.getLogger(ANALYSIS_LOGGER)
    analysis.addHandler(_rotating(log_dir / "analysis.log", logging.DEBUG, max_mb, backups, fmt))

    audit = logging.getLogger(AUDIT_LOGGER)
    audit.setLevel(logging.INFO)
    audit.propagate = False
    audit.addHandler(_rotating(log_dir / "audit.log", logging.INFO, max_mb, backups, JsonLinesFormatter()))

    # Third-party libraries are chatty at DEBUG.
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "PIL", "fontTools"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True
    return log_dir
