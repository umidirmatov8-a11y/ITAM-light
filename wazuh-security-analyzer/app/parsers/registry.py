"""Parser registry and automatic format detection.

New vendor parsers are registered with :func:`register_parser`.  Detection reads the
first 64 KB of a file and asks every parser for a confidence score; the extension is
only a tie-breaker, so mislabelled files are still parsed correctly.
"""

from __future__ import annotations

import codecs
import io
import logging
from typing import BinaryIO, TextIO

from app.parsers.base import BaseParser
from app.parsers.cef import CEFParser
from app.parsers.generic_log import GenericLogParser
from app.parsers.wazuh_csv import WazuhCSVParser
from app.parsers.wazuh_json import WazuhJSONParser
from app.parsers.wazuh_jsonl import WazuhJSONLParser
from app.parsers.wazuh_text import WazuhAlertsLogParser
from app.parsers.wazuh_xml import WazuhXMLParser

log = logging.getLogger(__name__)

SNIFF_BYTES = 64 * 1024

_REGISTRY: list[type[BaseParser]] = [
    WazuhJSONLParser,
    WazuhJSONParser,
    WazuhAlertsLogParser,
    WazuhCSVParser,
    WazuhXMLParser,
    CEFParser,
    GenericLogParser,
]


def register_parser(parser_cls: type[BaseParser], first: bool = False) -> None:
    if parser_cls in _REGISTRY:
        return
    if first:
        _REGISTRY.insert(0, parser_cls)
    else:
        _REGISTRY.insert(len(_REGISTRY) - 1, parser_cls)  # keep the generic fallback last


def registered_parsers() -> list[type[BaseParser]]:
    return list(_REGISTRY)


def get_parser(name: str) -> type[BaseParser] | None:
    for cls in _REGISTRY:
        if cls.name == name:
            return cls
    return None


def detect_encoding(head: bytes) -> str:
    if head.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if head.startswith(codecs.BOM_UTF16_LE) or head.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    if len(head) >= 4 and head[1:4:2] == b"\x00\x00" and head[0] != 0:
        return "utf-16-le"
    return "utf-8"


def decode_head(head: bytes, encoding: str) -> str:
    try:
        return head.decode(encoding, errors="replace")
    except LookupError:
        return head.decode("utf-8", errors="replace")


def detect_parser(head_text: str, filename: str) -> tuple[type[BaseParser], float]:
    best: type[BaseParser] = GenericLogParser
    best_score = 0.0
    lower = filename.lower()
    for cls in _REGISTRY:
        try:
            score = cls.sniff(head_text, filename)
        except Exception as exc:  # a buggy sniffer must not break detection
            log.debug("sniffer %s failed: %s", cls.name, exc)
            continue
        if score > 0 and any(lower.endswith(ext) for ext in cls.extensions):
            score += 0.01
        if score > best_score:
            best, best_score = cls, score
    return best, best_score


def open_text(binary: BinaryIO, encoding: str) -> TextIO:
    return io.TextIOWrapper(binary, encoding=encoding, errors="replace", newline=None)
