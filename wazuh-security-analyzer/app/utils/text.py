"""Text helpers."""

from __future__ import annotations

import re

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(value, max_len: int = 0) -> str:
    """Convert to str, strip control characters and optionally truncate."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    text = _CONTROL.sub("", text).strip()
    if max_len and len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    return f"{count:,} {singular if count == 1 else (plural_form or singular + 's')}"


def truncate_list(values, limit: int = 5) -> str:
    values = [v for v in values if v]
    if not values:
        return "-"
    shown = ", ".join(str(v) for v in values[:limit])
    if len(values) > limit:
        shown += f" (+{len(values) - limit} more)"
    return shown


def csv_safe(value) -> str:
    """Neutralise spreadsheet formula injection in exported cells."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text
