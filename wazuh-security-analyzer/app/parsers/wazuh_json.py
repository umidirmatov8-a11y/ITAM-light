"""Streaming parser for JSON documents: arrays, concatenated / pretty-printed objects and
export wrappers (OpenSearch ``hits.hits``, Wazuh API ``data.affected_items``).

Objects are decoded one at a time with ``json.JSONDecoder.raw_decode`` over a sliding
buffer, so a multi-gigabyte top-level array never has to be loaded into memory.
Corrupted objects are skipped by re-synchronising on the next object start.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator, TextIO

from app.parsers.base import BaseParser, ParseContext, iter_alert_dicts

_CHUNK = 1 << 20
_RESYNC = re.compile(r"[\n,\[]\s*\{")
_WS = " \t\r\n,"


class WazuhJSONParser(BaseParser):
    name = "wazuh_json"
    description = "Wazuh alerts JSON (array, pretty-printed or export wrapper)"
    extensions = (".json",)

    @classmethod
    def sniff(cls, head: str, filename: str) -> float:
        text = head.lstrip("﻿ \t\r\n")
        if not text or text[0] not in "[{":
            return 0.0
        score = 0.6 if text[0] == "[" else 0.5
        if '"rule"' in head or '"_source"' in head or '"affected_items"' in head:
            score += 0.3
        if filename.lower().endswith(".json"):
            score += 0.05
        return min(score, 0.95)

    def parse(self, stream: TextIO, ctx: ParseContext) -> Iterator[dict[str, Any]]:
        decoder = json.JSONDecoder()
        buf = ""
        pos = 0
        eof = False
        # Wrapper documents (API exports) are decoded as one object, so allow more than a line.
        max_object = max(ctx.max_line_bytes, 256 * 1024 * 1024)

        def fill(size: int = _CHUNK) -> bool:
            nonlocal buf, pos, eof
            chunk = stream.read(size)
            if not chunk:
                eof = True
                return False
            buf = buf[pos:] + chunk
            pos = 0
            return True

        fill()
        if buf.startswith("﻿"):
            pos = 1
        while True:
            while pos < len(buf) and (buf[pos] in _WS or buf[pos] in "[]"):
                pos += 1
            if pos >= len(buf):
                if eof or not fill():
                    break
                continue
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except RecursionError:
                ctx.error("JSON nesting too deep - object skipped")
                pos = self._resync(buf, pos)
                continue
            except json.JSONDecodeError as exc:
                # Incomplete (needs more data) iff the decoder hit the end of the buffer.  A corrupt
                # object fails *before* the end and is skipped immediately.
                incomplete = exc.msg.startswith("Unterminated string") or not buf[exc.pos:].strip()
                if incomplete and not eof and len(buf) - pos < max_object:
                    # Grow geometrically so large objects are not re-decoded O(n^2) times.
                    if fill(max(_CHUNK, len(buf) - pos)):
                        continue
                if not eof and len(buf) - pos >= max_object:
                    ctx.error(f"JSON object larger than {max_object // (1024 * 1024)} MB - skipped")
                else:
                    ctx.error(f"corrupted JSON near offset {exc.pos}: {exc.msg}")
                new_pos = self._resync(buf, pos)
                if new_pos >= len(buf) and not eof:
                    buf, pos = "", 0
                    if not fill():
                        break
                    continue
                pos = new_pos
                continue
            pos = end
            for record in iter_alert_dicts(obj):
                ctx.records += 1
                yield record
            if pos > _CHUNK and not eof:
                buf = buf[pos:]
                pos = 0

    @staticmethod
    def _resync(buf: str, pos: int) -> int:
        match = _RESYNC.search(buf, pos + 1)
        if match:
            return match.end() - 1
        return len(buf)
