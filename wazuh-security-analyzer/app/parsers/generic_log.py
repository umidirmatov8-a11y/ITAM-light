"""Fallback parser for unknown line-based logs (syslog, auth.log, application logs).

Lines are converted into *generic* events.  Because no Wazuh rule matched them, the
rule id is ``generic:<pattern>`` and a conservative level is derived from well-known
patterns only.  Confidence for these events is reduced by the risk engine.
"""

from __future__ import annotations

import re
from typing import Any, Iterator, TextIO

from app.parsers.base import BaseParser, ParseContext

_ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
_SYSLOG = re.compile(
    r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<prog>[\w./-]+)(?:\[\d+\])?:\s*(?P<msg>.*)$")
_IPV4 = re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])")

# (pattern id, regex, level, description, groups)
_PATTERNS: list[tuple[str, re.Pattern[str], int, str, list[str]]] = [
    ("ssh_invalid_user", re.compile(r"Invalid user (?P<user>\S+) from (?P<ip>\S+)", re.I), 5,
     "SSH login attempt with a non-existent user", ["authentication_failed", "invalid_login", "sshd"]),
    ("ssh_failed_password", re.compile(r"Failed (?:password|publickey) for (?:invalid user )?(?P<user>\S+) from (?P<ip>\S+)", re.I), 5,
     "SSH authentication failed", ["authentication_failed", "sshd"]),
    ("ssh_accepted", re.compile(r"Accepted (?:password|publickey|keyboard-interactive/pam) for (?P<user>\S+) from (?P<ip>\S+)", re.I), 3,
     "SSH authentication success", ["authentication_success", "sshd"]),
    ("pam_auth_failure", re.compile(r"pam_unix\(\S+\):\s*authentication failure.*?(?:rhost=(?P<ip>\S+))?.*?(?:user=(?P<user>\S+))?$", re.I), 5,
     "PAM authentication failure", ["authentication_failed", "pam"]),
    ("sudo_command", re.compile(r"sudo:\s+(?P<user>\S+)\s*:.*COMMAND=(?P<cmd>.*)$", re.I), 3,
     "Command executed with sudo", ["sudo"]),
    ("sudo_failure", re.compile(r"sudo:.*(?:incorrect password attempts|authentication failure)", re.I), 6,
     "Failed sudo authentication", ["sudo", "authentication_failed"]),
    ("useradd", re.compile(r"useradd\[\d+\]:\s*new user: name=(?P<user>[^,\s]+)", re.I), 8,
     "New user added to the system", ["adduser", "account_changed"]),
    ("firewall_block", re.compile(r"(?:UFW BLOCK|iptables.*DROP|DENY).*SRC=(?P<ip>\S+)", re.I), 4,
     "Firewall blocked connection", ["firewall", "firewall_drop"]),
    ("segfault", re.compile(r"segfault at", re.I), 4, "Process crashed (segmentation fault)", ["system"]),
    ("error", re.compile(r"\b(?:error|failed|failure|denied)\b", re.I), 2, "Error or failure message", ["errors"]),
]


class GenericLogParser(BaseParser):
    name = "generic_log"
    vendor = "generic"
    description = "Unknown line-based logs (syslog, auth.log, ...)"
    extensions = (".log", ".txt")

    @classmethod
    def sniff(cls, head: str, filename: str) -> float:
        return 0.1 if head.strip() else 0.0

    def parse(self, stream: TextIO, ctx: ParseContext) -> Iterator[dict[str, Any]]:
        for line_no, line in enumerate(stream, start=1):
            if len(line) > ctx.max_line_bytes:
                ctx.error(f"line {line_no}: exceeds the maximum line length - skipped")
                continue
            line = line.strip().lstrip("﻿")
            if not line:
                continue
            record = self.parse_line(line)
            ctx.records += 1
            yield record

    @staticmethod
    def parse_line(line: str) -> dict[str, Any]:
        record: dict[str, Any] = {"agent": {}, "data": {}, "decoder": {"name": "generic"}, "full_log": line[:8192]}
        message = line
        sm = _SYSLOG.match(line)
        if sm:
            record["timestamp"] = sm["ts"]
            record["agent"]["name"] = sm["host"]
            record["program_name"] = sm["prog"]
            record["decoder"]["name"] = f"generic:{sm['prog']}"
            message = sm["msg"]
        else:
            ts = _ISO_TS.search(line[:64])
            if ts:
                record["timestamp"] = ts.group(0)
        rule = {"id": "generic:event", "level": 1, "description": "Unclassified log line", "groups": ["generic"]}
        for pattern_id, regex, level, description, groups in _PATTERNS:
            match = regex.search(message)
            if not match:
                continue
            rule = {"id": f"generic:{pattern_id}", "level": level, "description": description,
                    "groups": ["generic", *groups]}
            named = match.groupdict()
            if named.get("user"):
                record["data"]["dstuser"] = named["user"].strip("'\"")
            if named.get("ip") and _IPV4.fullmatch(named["ip"]):
                record["data"]["srcip"] = named["ip"]
            if named.get("cmd"):
                record["data"]["command"] = named["cmd"]
            break
        if "srcip" not in record["data"]:
            ips = _IPV4.findall(message)
            if ips:
                record["data"]["srcip"] = ips[0]
        record["rule"] = rule
        return record
