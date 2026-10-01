"""Parser interface and shared helpers.

A parser turns a text stream into an iterator of *raw event dictionaries* shaped like
Wazuh alerts (``{"rule": {...}, "agent": {...}, "data": {...}}``).  Non-JSON formats
(CSV, XML, CEF, text) are converted into that shape so that a single normalizer can
handle everything.  New vendors (ESET, FortiGate, Sysmon, ...) plug in by subclassing
:class:`BaseParser` and registering in :mod:`app.parsers.registry`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterator, TextIO

log = logging.getLogger("wsa.analysis")

MAX_REPORTED_ERRORS = 20


@dataclass
class ParseContext:
    source_name: str
    max_line_bytes: int = 16 * 1024 * 1024
    errors: int = 0
    error_samples: list[str] = field(default_factory=list)
    records: int = 0

    def error(self, message: str) -> None:
        self.errors += 1
        if len(self.error_samples) < MAX_REPORTED_ERRORS:
            self.error_samples.append(message)
            log.warning("%s: %s", self.source_name, message)


class BaseParser(ABC):
    name: ClassVar[str] = "base"
    vendor: ClassVar[str] = "wazuh"
    description: ClassVar[str] = ""
    extensions: ClassVar[tuple[str, ...]] = ()

    @classmethod
    @abstractmethod
    def sniff(cls, head: str, filename: str) -> float:
        """Return a confidence (0..1) that this parser understands a file starting with ``head``."""

    @abstractmethod
    def parse(self, stream: TextIO, ctx: ParseContext) -> Iterator[dict[str, Any]]:
        """Yield raw event dictionaries. Must never raise on malformed records - count them in ``ctx``."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_WRAPPER_PATHS = (
    ("hits", "hits"),
    ("data", "affected_items"),
    ("alerts",),
    ("events",),
    ("items",),
    ("results",),
    ("records",),
    ("data",),
)


def looks_like_alert(obj: dict[str, Any]) -> bool:
    if not isinstance(obj, dict):
        return False
    rule = obj.get("rule")
    if isinstance(rule, dict) and ("id" in rule or "level" in rule or "description" in rule):
        return True
    if "rule.id" in obj or "rule.level" in obj:
        return True
    return ("full_log" in obj and ("agent" in obj or "timestamp" in obj)) or ("decoder" in obj and "agent" in obj)


def iter_alert_dicts(obj: Any, depth: int = 0) -> Iterator[dict[str, Any]]:
    """Find alert-like dictionaries inside common export wrappers.

    Handles plain alerts, Wazuh indexer / OpenSearch exports (``hits.hits[]._source``),
    Wazuh API responses (``data.affected_items``) and generic ``{"alerts": [...]}`` files.
    Dictionaries that are not recognisable as Wazuh alerts but contain scalar fields are
    yielded as generic events.
    """
    if depth > 8:
        return
    if isinstance(obj, list):
        for item in obj:
            yield from iter_alert_dicts(item, depth + 1)
        return
    if not isinstance(obj, dict):
        return
    source = obj.get("_source")
    if isinstance(source, dict):
        yield source
        return
    if looks_like_alert(obj):
        yield obj
        return
    for path in _WRAPPER_PATHS:
        node: Any = obj
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, list) and node and isinstance(node[0], dict):
            yield from iter_alert_dicts(node, depth + 1)
            return
    nested_lists = [v for v in obj.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
    if nested_lists and not any(looks_like_alert(v) for v in obj.values() if isinstance(v, dict)):
        scalar_fields = [v for v in obj.values() if isinstance(v, (str, int, float))]
        if len(scalar_fields) <= 3:
            for lst in nested_lists:
                yield from iter_alert_dicts(lst, depth + 1)
            return
    if obj:
        yield obj


def unflatten(flat: dict[str, Any]) -> dict[str, Any]:
    """Convert ``{"rule.id": 5710, "agent.name": "x"}`` into nested dictionaries."""
    result: dict[str, Any] = {}
    for key, value in flat.items():
        if key is None:
            continue
        key = str(key).strip().lstrip("﻿")
        if key.startswith("_source."):
            key = key[len("_source."):]
        if key in ("", "_id", "_index", "_score", "_type"):
            continue
        parts = key.split(".")
        node = result
        ok = True
        for part in parts[:-1]:
            existing = node.get(part)
            if existing is None:
                existing = node[part] = {}
            elif not isinstance(existing, dict):
                ok = False
                break
            node = existing
        if ok and not isinstance(node.get(parts[-1]), dict):
            node[parts[-1]] = value
    return result
