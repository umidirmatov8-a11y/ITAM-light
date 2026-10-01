"""Severity levels and score bucketing."""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"

    @property
    def rank(self) -> int:
        return _RANK[self]

    @property
    def label(self) -> str:
        return self.value.upper()

    @property
    def icon(self) -> str:
        return _ICON[self]

    @classmethod
    def parse(cls, value: str | "Severity" | None, default: "Severity | None" = None) -> "Severity":
        if isinstance(value, Severity):
            return value
        if value:
            v = str(value).strip().lower()
            aliases = {"info": "informational", "information": "informational", "crit": "critical",
                       "med": "medium", "moderate": "medium", "important": "high", "none": "informational"}
            v = aliases.get(v, v)
            for member in cls:
                if member.value == v:
                    return member
        if default is not None:
            return default
        raise ValueError(f"Unknown severity: {value!r}")


_RANK = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFORMATIONAL: 0,
}

_ICON = {
    Severity.CRITICAL: "\U0001F534",  # red circle
    Severity.HIGH: "\U0001F7E0",  # orange circle
    Severity.MEDIUM: "\U0001F7E1",  # yellow circle
    Severity.LOW: "\U0001F535",  # blue circle
    Severity.INFORMATIONAL: "⚪",  # white circle
}

SEVERITY_ORDER: list[Severity] = [
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFORMATIONAL,
]

SEVERITY_COLORS: dict[str, str] = {
    "critical": "#ff3b5c",
    "high": "#ff8a3d",
    "medium": "#f5c542",
    "low": "#3fa9f5",
    "informational": "#8b949e",
}


def severity_from_score(score: float, thresholds: "object") -> Severity:
    """Map a 0-100 risk score to a severity using configurable thresholds.

    ``thresholds`` must expose ``critical``, ``high``, ``medium`` and ``low`` lower bounds.
    """
    if score >= thresholds.critical:
        return Severity.CRITICAL
    if score >= thresholds.high:
        return Severity.HIGH
    if score >= thresholds.medium:
        return Severity.MEDIUM
    if score >= thresholds.low:
        return Severity.LOW
    return Severity.INFORMATIONAL
