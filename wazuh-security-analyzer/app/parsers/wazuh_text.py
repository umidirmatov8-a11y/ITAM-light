"""Classic Wazuh/OSSEC ``alerts.log`` text format.

Example::

    ** Alert 1696156800.12345: - syslog,sshd,invalid_login,authentication_failed,
    2023 Oct 01 10:00:00 (web-01) 10.0.0.5->/var/log/auth.log
    Rule: 5710 (level 5) -> 'sshd: Attempt to login using a non-existent user'
    Src IP: 203.0.113.10
    User: admin
    Oct  1 10:00:00 web-01 sshd[123]: Invalid user admin from 203.0.113.10 port 51234
"""

from __future__ import annotations

import re
from typing import Any, Iterator, TextIO

from app.parsers.base import BaseParser, ParseContext

_HEADER = re.compile(r"^\*\* Alert (?P<id>[\d.]+):(?P<rest>.*)$")
_LOCATION = re.compile(
    r"^(?P<ts>\d{4} \w{3} \d{1,2} \d{2}:\d{2}:\d{2})\s+(?:\((?P<agent>[^)]+)\)\s+(?P<agent_ip>\S+?)->|(?P<host>[^\s>]+?)->)(?P<loc>.*)$")
_RULE = re.compile(r"^Rule:\s*(?P<id>\d+)\s*\(level\s*(?P<level>\d+)\)\s*->\s*'(?P<desc>.*)'\s*$")
_FIELD = re.compile(r"^(?P<key>[A-Za-z][A-Za-z ._-]{0,30}):\s?(?P<value>.*)$")

_FIELD_MAP = {
    "src ip": ("data", "srcip"),
    "src port": ("data", "srcport"),
    "dst ip": ("data", "dstip"),
    "dst port": ("data", "dstport"),
    "user": ("data", "dstuser"),
    "src user": ("data", "srcuser"),
    "srcuser": ("data", "srcuser"),
    "dstuser": ("data", "dstuser"),
    "url": ("data", "url"),
    "file": ("syscheck", "path"),
}


class WazuhAlertsLogParser(BaseParser):
    name = "wazuh_alerts_log"
    description = "Wazuh/OSSEC alerts.log (multi-line text)"
    extensions = (".log", ".txt")

    @classmethod
    def sniff(cls, head: str, filename: str) -> float:
        return 0.97 if "** Alert " in head[:8192] and "Rule: " in head else 0.0

    def parse(self, stream: TextIO, ctx: ParseContext) -> Iterator[dict[str, Any]]:
        block: list[str] = []
        for line in stream:
            line = line.rstrip("\r\n")
            if line.startswith("** Alert "):
                if block:
                    rec = self._parse_block(block, ctx)
                    if rec:
                        yield rec
                block = [line]
            elif block:
                if len(block) < 500:
                    block.append(line)
        if block:
            rec = self._parse_block(block, ctx)
            if rec:
                yield rec

    def _parse_block(self, block: list[str], ctx: ParseContext) -> dict[str, Any] | None:
        header = _HEADER.match(block[0])
        if not header:
            ctx.error(f"malformed alert header: {block[0][:80]}")
            return None
        groups = [g.strip() for g in header["rest"].replace("-", " ", 1).split(",") if g.strip()]
        record: dict[str, Any] = {"id": header["id"], "rule": {"groups": groups}, "agent": {}, "data": {}}
        log_lines: list[str] = []
        rule_found = False
        for line in block[1:]:
            if not line.strip():
                continue
            loc = _LOCATION.match(line)
            if loc and "timestamp" not in record:
                record["timestamp"] = loc["ts"]
                if loc["agent"]:
                    record["agent"] = {"name": loc["agent"], "ip": loc["agent_ip"] if loc["agent_ip"] != "any" else ""}
                else:
                    record["agent"] = {"name": loc["host"]}
                record["location"] = loc["loc"]
                continue
            rule = _RULE.match(line)
            if rule and not rule_found:
                record["rule"].update({"id": rule["id"], "level": int(rule["level"]), "description": rule["desc"]})
                rule_found = True
                continue
            if rule_found:
                fld = _FIELD.match(line)
                if fld and fld["key"].lower() in _FIELD_MAP and not log_lines:
                    section, key = _FIELD_MAP[fld["key"].lower()]
                    record.setdefault(section, {})[key] = fld["value"].strip()
                    continue
                log_lines.append(line)
        if not rule_found:
            ctx.error(f"alert {header['id']}: no 'Rule:' line")
            return None
        record["full_log"] = "\n".join(log_lines)[:8192]
        ctx.records += 1
        return record
