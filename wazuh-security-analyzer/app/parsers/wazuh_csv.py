"""CSV / TSV exports (Wazuh dashboard "Export CSV", OpenSearch Discover exports, custom reports).

Dotted column names such as ``rule.id`` or ``_source.agent.name`` are converted back
into nested dictionaries so the normalizer handles them like native JSON alerts.
"""

from __future__ import annotations

import csv
import json
import sys
from typing import Any, Iterator, TextIO

from app.parsers.base import BaseParser, ParseContext, unflatten

_KNOWN_COLUMNS = ("rule.id", "rule.level", "rule.description", "agent.name", "timestamp", "@timestamp",
                  "data.srcip", "full_log", "_source.rule.id", "rule_id", "level", "description")

try:
    csv.field_size_limit(min(sys.maxsize, 64 * 1024 * 1024))
except OverflowError:  # pragma: no cover - 32-bit platforms
    csv.field_size_limit(2**31 - 1)


def _parse_list(value: str) -> Any:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            return json.loads(text)
        except ValueError:
            return [v.strip().strip("'\"") for v in text[1:-1].split(",") if v.strip()]
    return value


_ALIASES = {
    "rule_id": "rule.id", "ruleid": "rule.id", "level": "rule.level", "rule_level": "rule.level",
    "description": "rule.description", "rule_description": "rule.description",
    "agent": "agent.name", "agent_name": "agent.name", "agentname": "agent.name", "agent_ip": "agent.ip",
    "srcip": "data.srcip", "src_ip": "data.srcip", "source_ip": "data.srcip",
    "dstip": "data.dstip", "dst_ip": "data.dstip", "dstuser": "data.dstuser", "user": "data.dstuser",
    "username": "data.dstuser", "srcuser": "data.srcuser", "groups": "rule.groups", "rule_groups": "rule.groups",
    "mitre": "rule.mitre.id", "mitre_id": "rule.mitre.id", "time": "timestamp", "date": "timestamp",
    "message": "full_log", "log": "full_log",
}


class WazuhCSVParser(BaseParser):
    name = "wazuh_csv"
    description = "CSV/TSV exports from Wazuh dashboard or OpenSearch"
    extensions = (".csv", ".tsv")

    @classmethod
    def sniff(cls, head: str, filename: str) -> float:
        lines = head.lstrip("﻿").splitlines()
        if not lines:
            return 0.0
        header = lines[0].lower()
        if header.startswith(("{", "[", "<")):
            return 0.0
        hits = sum(1 for col in _KNOWN_COLUMNS if col in header)
        delimiters = sum(header.count(d) for d in (",", ";", "\t", "|"))
        if delimiters == 0:
            return 0.0
        score = 0.2 + 0.15 * hits
        if filename.lower().endswith((".csv", ".tsv")):
            score += 0.35
        return min(score, 0.95)

    def parse(self, stream: TextIO, ctx: ParseContext) -> Iterator[dict[str, Any]]:
        sample = stream.read(64 * 1024)
        if not sample:
            return
        try:
            dialect = csv.Sniffer().sniff(sample.splitlines()[0] if sample else "", delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rest = stream

        def lines():
            parts = sample.split("\n")
            carry = parts.pop()  # possibly incomplete last line of the sample
            for part in parts:
                yield part + "\n"
            for line in rest:
                if carry:
                    line, carry = carry + line, ""
                yield line
            if carry:
                yield carry

        reader = csv.reader(lines(), dialect)
        try:
            header = next(reader)
        except (StopIteration, csv.Error) as exc:
            ctx.error(f"cannot read CSV header: {exc}")
            return
        columns = [_ALIASES.get(h.strip().lstrip("﻿").lower(), h.strip().lstrip("﻿")) for h in header]
        if not any(columns):
            ctx.error("CSV header is empty")
            return
        row_no = 1
        while True:
            row_no += 1
            try:
                row = next(reader)
            except StopIteration:
                break
            except csv.Error as exc:
                ctx.error(f"row {row_no}: malformed CSV ({exc})")
                continue
            if not row or all(not c.strip() for c in row):
                continue
            if len(row) != len(columns):
                ctx.error(f"row {row_no}: expected {len(columns)} columns, found {len(row)}")
                if len(row) < 2:
                    continue
            flat: dict[str, Any] = {}
            for col, value in zip(columns, row):
                if not col or value is None or value == "" or value == "-":
                    continue
                flat[col] = _parse_list(value) if col.endswith(("groups", "mitre.id", "mitre.tactic",
                                                                  "mitre.technique")) else value
            if not flat:
                continue
            record = unflatten(flat)
            ctx.records += 1
            yield record
