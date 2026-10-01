"""ArcSight Common Event Format (CEF), optionally prefixed by a syslog header."""

from __future__ import annotations

import re
from typing import Any, Iterator, TextIO

from app.parsers.base import BaseParser, ParseContext

_EXT_KEY = re.compile(r"(?:^|\s)([A-Za-z0-9_.\[\]-]+)=")
_SEVERITY_WORDS = {"low": 3, "medium": 6, "high": 8, "very-high": 10, "very high": 10, "unknown": 0}

_EXT_MAP = {
    "src": ("data", "srcip"), "sourceaddress": ("data", "srcip"),
    "dst": ("data", "dstip"), "destinationaddress": ("data", "dstip"),
    "spt": ("data", "srcport"), "dpt": ("data", "dstport"),
    "suser": ("data", "srcuser"), "duser": ("data", "dstuser"),
    "request": ("data", "url"), "requesturl": ("data", "url"),
    "act": ("data", "action"), "proto": ("data", "protocol"),
    "fname": ("data", "filename"), "filepath": ("syscheck", "path"),
    "filehash": ("data", "file_hash"), "sproc": ("data", "process"), "dproc": ("data", "process"),
    "msg": ("data", "msg"),
}


def _split_header(text: str) -> list[str] | None:
    parts: list[str] = []
    current = []
    i = 0
    while i < len(text) and len(parts) < 7:
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in "|\\":
            current.append(text[i + 1])
            i += 2
            continue
        if ch == "|":
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    if len(parts) < 7:
        return None
    parts.append(text[i:])  # extension
    return parts


def parse_extension(ext: str) -> dict[str, str]:
    result: dict[str, str] = {}
    matches = list(_EXT_KEY.finditer(ext))
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(ext)
        value = ext[start:end].strip()
        value = value.replace("\\=", "=").replace("\\n", "\n").replace("\\r", "\r").replace("\\\\", "\\")
        result[match.group(1)] = value
    return result


class CEFParser(BaseParser):
    name = "cef"
    vendor = "generic"
    description = "Common Event Format (CEF) lines"
    extensions = (".cef", ".log", ".txt")

    @classmethod
    def sniff(cls, head: str, filename: str) -> float:
        lines = [ln for ln in head.splitlines()[:20] if ln.strip()]
        if not lines:
            return 0.0
        hits = sum(1 for ln in lines if "CEF:" in ln)
        return 0.96 * hits / len(lines) if hits else 0.0

    def parse(self, stream: TextIO, ctx: ParseContext) -> Iterator[dict[str, Any]]:
        for line_no, line in enumerate(stream, start=1):
            idx = line.find("CEF:")
            if idx < 0:
                continue
            prefix = line[:idx].strip()
            parts = _split_header(line[idx + 4:].rstrip("\r\n"))
            if not parts:
                ctx.error(f"line {line_no}: malformed CEF header")
                continue
            _version, dev_vendor, dev_product, _dev_version, sig_id, name, severity, ext = parts
            extension = parse_extension(ext)
            sev = severity.strip().lower()
            try:
                sev_num = float(sev)
            except ValueError:
                sev_num = _SEVERITY_WORDS.get(sev, 3)
            level = max(0, min(15, round(sev_num * 1.5)))
            is_wazuh = any(v in dev_vendor.lower() for v in ("wazuh", "ossec"))
            record: dict[str, Any] = {
                "rule": {
                    "id": sig_id if is_wazuh else f"cef:{dev_vendor}:{sig_id}",
                    "level": level,
                    "description": name,
                    "groups": ["cef", dev_product.lower()],
                },
                "agent": {"name": extension.get("dvchost") or extension.get("shost") or
                          (prefix.split()[-1] if prefix else dev_product)},
                "data": {},
                "decoder": {"name": f"cef:{dev_product}"},
                "full_log": line.strip()[:8192],
            }
            ts = extension.get("rt") or extension.get("end") or extension.get("start")
            if ts:
                record["timestamp"] = int(ts) if ts.isdigit() else ts
            elif prefix:
                record["timestamp"] = prefix
            for key, value in extension.items():
                mapped = _EXT_MAP.get(key.lower())
                if mapped:
                    record.setdefault(mapped[0], {})[mapped[1]] = value
                else:
                    record["data"][key] = value
            if not is_wazuh:
                record["_vendor"] = dev_vendor.lower() or "generic"
            ctx.records += 1
            yield record
