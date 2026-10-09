"""Masking of secret values before anything is written to logs, journals, reports or error dialogs.

The application never intentionally passes passwords to loggers; this module is a second line of
defence for text produced by third-party libraries (ldap3 exception messages, subprocess output, etc.).
"""
from __future__ import annotations

import logging
import re
from typing import Any

MASK = "********"

# Attribute / parameter names whose values are secret.
SECRET_KEYS = {
    "password", "passwd", "pwd", "new_password", "old_password", "unicodepwd", "userpassword",
    "secret", "token", "credential", "credentials", "dbcspwd", "supplementalcredentials",
    "ntpwdhistory", "lmpwdhistory", "unixuserpassword", "mssfu30password", "sasl_credentials",
}

_KEY_GROUP = r"(?:" + "|".join(sorted((re.escape(k) for k in SECRET_KEYS), key=len, reverse=True)) + r")"

# key=value, key: value, "key": "value", key => value
_KV_RE = re.compile(
    r"""(?P<key>["']?\b""" + _KEY_GROUP + r"""\b["']?\s*(?:=>|=|:)\s*)(?P<val>"[^"]*"|'[^']*'|[^\s,;})\]]+)""",
    re.IGNORECASE,
)


def _kv_repl(m: re.Match) -> str:
    val = m.group("val")
    if val[:1] in ("'", '"'):
        return f"{m.group('key')}{val[0]}{MASK}{val[0]}"
    return f"{m.group('key')}{MASK}"


# -Password / /p: style command line arguments
_CLI_RE = re.compile(r"(?P<key>(?:^|\s)(?:-|/)(?:password|pwd|p)(?:\s+|:))(?P<val>\S+)", re.IGNORECASE)
# Quoted UTF-16 password blobs as produced for unicodePwd (b'"\x00P\x00...')
_BYTES_RE = re.compile(r"b(['\"])\\?\"\\x00.*?\1")


def mask_text(text: Any, extra_secrets: tuple[str, ...] | list[str] = ()) -> str:
    """Return *text* with secret values replaced by a mask.

    ``extra_secrets`` are literal values (for example the password the user just typed) that must never
    appear in the output, whatever the surrounding context.
    """
    if text is None:
        return ""
    s = str(text)
    for secret in extra_secrets:
        if secret and len(secret) >= 1:
            s = s.replace(secret, MASK)
    s = _BYTES_RE.sub(MASK, s)
    s = _KV_RE.sub(_kv_repl, s)
    s = _CLI_RE.sub(lambda m: f"{m.group('key')}{MASK}", s)
    return s


def mask_mapping(data: Any) -> Any:
    """Recursively mask a dict/list structure (values under secret keys are replaced)."""
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if str(k).lower().replace("-", "_") in SECRET_KEYS:
                out[k] = MASK
            else:
                out[k] = mask_mapping(v)
        return out
    if isinstance(data, (list, tuple)):
        return type(data)(mask_mapping(v) for v in data)
    if isinstance(data, (bytes, bytearray)):
        return f"<{len(data)} bytes>"
    if isinstance(data, str):
        return mask_text(data)
    return data


class SecretMaskingFilter(logging.Filter):
    """Logging filter that masks secrets in every record (message and args)."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - malformed record
            msg = str(record.msg)
        record.msg = mask_text(msg)
        record.args = ()
        if record.exc_text:
            record.exc_text = mask_text(record.exc_text)
        return True
