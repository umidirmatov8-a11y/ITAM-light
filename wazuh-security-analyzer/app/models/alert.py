"""Normalized representation of a single security alert."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NormalizedAlert:
    uid: str
    timestamp: float | None
    rule_id: str
    rule_level: int
    rule_description: str
    rule_groups: tuple[str, ...] = ()
    rule_mitre_ids: tuple[str, ...] = ()
    agent_id: str = ""
    agent_name: str = ""
    agent_ip: str = ""
    manager: str = ""
    src_ip: str = ""
    src_port: str = ""
    dst_ip: str = ""
    dst_port: str = ""
    src_user: str = ""
    user: str = ""
    process: str = ""
    command_line: str = ""
    parent_process: str = ""
    file_path: str = ""
    hashes: dict[str, str] = field(default_factory=dict)
    urls: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    cves: tuple[str, ...] = ()
    cvss: float | None = None
    vuln_severity: str = ""
    package: str = ""
    vt_positives: int | None = None
    vt_total: int | None = None
    location: str = ""
    decoder: str = ""
    full_log: str = ""
    category: str = "other"
    iocs: tuple[tuple[str, str], ...] = ()
    source_file: str = ""
    vendor: str = "wazuh"
    parser: str = ""
    raw: dict[str, Any] | None = None

    @property
    def primary_hash(self) -> str:
        for key in ("sha256", "sha1", "md5"):
            if self.hashes.get(key):
                return self.hashes[key]
        return ""

    @property
    def primary_cve(self) -> str:
        return self.cves[0] if self.cves else ""

    def context_dict(self) -> dict[str, Any]:
        """Compact, AI/report friendly view without the raw event."""
        data = {
            "rule_id": self.rule_id,
            "rule_level": self.rule_level,
            "description": self.rule_description,
            "rule_groups": list(self.rule_groups),
            "timestamp": self.timestamp,
            "agent": self.agent_name,
            "agent_ip": self.agent_ip,
            "source_ip": self.src_ip,
            "destination_ip": self.dst_ip,
            "user": self.user,
            "source_user": self.src_user,
            "process": self.process,
            "command_line": self.command_line[:1000],
            "parent_process": self.parent_process,
            "file_path": self.file_path,
            "hashes": dict(self.hashes),
            "cves": list(self.cves),
            "cvss": self.cvss,
            "package": self.package,
            "category": self.category,
            "location": self.location,
            "full_log": self.full_log[:1000],
        }
        return {k: v for k, v in data.items() if v not in ("", None, [], {}, ())}
