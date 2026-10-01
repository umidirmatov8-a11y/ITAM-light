"""Line-delimited JSON (JSONL / NDJSON) - the native format of Wazuh ``alerts.json``."""

from __future__ import annotations

import json
from typing import Any, Iterator, TextIO

from app.parsers.base import BaseParser, ParseContext, iter_alert_dicts


class WazuhJSONLParser(BaseParser):
    name = "wazuh_jsonl"
    description = "Wazuh alerts.json (one JSON alert per line), JSONL, NDJSON"
    extensions = (".jsonl", ".ndjson", ".json")

    @classmethod
    def sniff(cls, head: str, filename: str) -> float:
        lines = [ln.strip() for ln in head.lstrip("﻿").splitlines() if ln.strip()]
        if not lines or not lines[0].startswith("{"):
            return 0.0
        complete = 0
        checked = lines[:5] if len(lines) > 1 else lines
        for line in checked[:-1] if len(checked) > 1 else checked:
            try:
                if isinstance(json.loads(line), dict):
                    complete += 1
            except ValueError:
                return 0.1
        if not complete:
            return 0.1
        score = 0.85
        if '"rule"' in head:
            score += 0.1
        if filename.lower().endswith((".jsonl", ".ndjson")):
            score += 0.04
        return min(score, 0.99)

    def parse(self, stream: TextIO, ctx: ParseContext) -> Iterator[dict[str, Any]]:
        line_no = 0
        for line in stream:
            line_no += 1
            if len(line) > ctx.max_line_bytes:
                ctx.error(f"line {line_no}: exceeds the maximum line length - skipped")
                continue
            line = line.strip().lstrip("﻿")
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, RecursionError) as exc:
                ctx.error(f"line {line_no}: invalid JSON ({str(exc)[:80]})")
                continue
            for record in iter_alert_dicts(obj):
                ctx.records += 1
                yield record
