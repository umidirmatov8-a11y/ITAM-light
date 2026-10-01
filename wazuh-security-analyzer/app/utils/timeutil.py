"""Fast, tolerant timestamp parsing for security logs (returns UTC epoch seconds)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

_TZ_NO_COLON = re.compile(r"([+-]\d{2})(\d{2})$")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_SYSLOG = re.compile(r"^(?P<mon>[A-Za-z]{3})\s+(?P<day>\d{1,2})\s+(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})")
_WAZUH_TEXT = re.compile(
    r"^(?P<y>\d{4})\s+(?P<mon>[A-Za-z]{3})\s+(?P<day>\d{1,2})\s+(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})")

# Reject absurd timestamps (before 2000 or after 2100) that usually indicate a parse problem.
_MIN_TS = 946684800.0
_MAX_TS = 4102444800.0


def parse_timestamp(value, default_year: int | None = None) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:  # milliseconds
            ts /= 1000.0
        return ts if _MIN_TS <= ts <= _MAX_TS else None
    text = str(value).strip()
    if not text:
        return None
    if text.replace(".", "", 1).isdigit():
        return parse_timestamp(float(text))
    candidate = text.replace(" ", "T", 1) if len(text) > 10 and text[10] == " " else text
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    candidate = _TZ_NO_COLON.sub(r"\1:\2", candidate)
    try:
        dt = datetime.fromisoformat(candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ts = dt.timestamp()
        return ts if _MIN_TS <= ts <= _MAX_TS else None
    except ValueError:
        pass
    m = _WAZUH_TEXT.match(text)
    if m:
        return _build(int(m["y"]), m["mon"], m["day"], m["h"], m["m"], m["s"])
    m = _SYSLOG.match(text)
    if m:
        year = default_year or datetime.now(timezone.utc).year
        return _build(year, m["mon"], m["day"], m["h"], m["m"], m["s"])
    return None


def _build(year: int, mon: str, day: str, h: str, mi: str, s: str) -> float | None:
    month = _MONTHS.get(mon.lower()[:3])
    if not month:
        return None
    try:
        return datetime(year, month, int(day), int(h), int(mi), int(s), tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def fmt_ts(ts: float | None, with_seconds: bool = True) -> str:
    if ts is None:
        return "-"
    fmt = "%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt) + " UTC"


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    from app.i18n import get_language
    ru = get_language() == "ru"
    d_, h_, m_, s_ = ("д", "ч", "мин", "с") if ru else ("d", "h", "m", "s")
    sep = " " if ru else ""
    if seconds < 10:
        return f"{seconds:.1f}{sep}{s_}".replace(".", ",") if ru else f"{seconds:.1f}s"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}{sep}{s_}"
    if seconds < 3600:
        return f"{seconds // 60}{sep}{m_} {seconds % 60}{sep}{s_}"
    if seconds < 86400:
        return f"{seconds // 3600}{sep}{h_} {(seconds % 3600) // 60}{sep}{m_}"
    return f"{seconds // 86400}{sep}{d_} {(seconds % 86400) // 3600}{sep}{h_}"
