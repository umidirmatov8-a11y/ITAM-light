"""Analysis artefacts: alert groups, risk factors, chains, incidents, IOC and CVE records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any


class IncidentStatus(str, Enum):
    NEW = "NEW"
    INVESTIGATING = "INVESTIGATING"
    CONFIRMED = "CONFIRMED"
    FALSE_POSITIVE = "FALSE POSITIVE"
    RESOLVED = "RESOLVED"

    @classmethod
    def parse(cls, value: str | None) -> "IncidentStatus":
        for member in cls:
            if member.value == (value or "").upper() or member.name == (value or "").upper():
                return member
        return cls.NEW


def _filter_kwargs(cls, data: dict[str, Any]) -> dict[str, Any]:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


@dataclass
class RiskFactor:
    name: str
    points: float
    reason: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RiskFactor":
        return cls(**_filter_kwargs(cls, data))


@dataclass
class MitreMapping:
    technique_id: str
    name: str
    tactics: list[str] = field(default_factory=list)
    confidence: str = "low"  # high | medium | low
    source: str = "heuristic"  # wazuh_rule | rule_kb | heuristic | ai
    evidence: str = ""
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MitreMapping":
        return cls(**_filter_kwargs(cls, data))


@dataclass
class AlertGroup:
    """Aggregation of repeated alerts that share rule, host, source and user."""

    id: int
    key: str
    rule_id: str
    rule_level: int
    rule_description: str
    category: str
    rule_groups: list[str] = field(default_factory=list)
    agent_name: str = ""
    agent_ip: str = ""
    src_ip: str = ""
    src_external: bool = False
    user: str = ""
    cve: str = ""
    file_hash: str = ""
    count: int = 0
    first_ts: float | None = None
    last_ts: float | None = None
    timestamps: list[float] = field(default_factory=list)
    peak_count: int = 0  # max events inside one correlation window (burst size)
    users: list[str] = field(default_factory=list)
    src_ips: list[str] = field(default_factory=list)
    dst_ips: list[str] = field(default_factory=list)
    processes: list[str] = field(default_factory=list)
    command_lines: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)
    iocs: dict[str, int] = field(default_factory=dict)  # "type|value" -> count
    cves: list[str] = field(default_factory=list)
    cvss: float | None = None
    vuln_severity: str = ""
    packages: list[str] = field(default_factory=list)
    vt_positives: int | None = None
    vt_total: int | None = None
    rule_mitre_ids: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    sample_uids: list[str] = field(default_factory=list)
    sample_logs: list[str] = field(default_factory=list)
    representative: dict[str, Any] = field(default_factory=dict)
    vendor: str = "wazuh"
    parser: str = ""
    # Correlation
    success_after_failures: bool = False
    failures_before_success: int = 0
    chain_ids: list[int] = field(default_factory=list)
    campaign: bool = False
    # Enrichment
    ioc_verdict: str = "unknown"  # malicious | suspicious | clean | unknown
    ioc_verdict_sources: list[str] = field(default_factory=list)
    kev: bool = False
    # Analysis
    asset_criticality: str = "medium"
    mitre: list[MitreMapping] = field(default_factory=list)
    risk_factors: list[RiskFactor] = field(default_factory=list)
    risk_score: float = 0.0
    severity: str = "informational"
    confidence: float = 0.5
    fp_probability: float = 0.0
    fp_reasons: list[str] = field(default_factory=list)
    fp_counter_reasons: list[str] = field(default_factory=list)
    assessment: str = ""
    title: str = ""
    what_happened: str = ""
    why_it_matters: str = ""
    possible_attack: str = ""
    evidence: list[str] = field(default_factory=list)
    recommendations: dict[str, list[str]] = field(default_factory=dict)
    incident_id: str = ""
    ai_analysis: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        # Shallow conversion (much faster than dataclasses.asdict, which deep-copies every value).
        data = dict(self.__dict__)
        data["mitre"] = [dict(m.__dict__) for m in self.mitre]
        data["risk_factors"] = [dict(r.__dict__) for r in self.risk_factors]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlertGroup":
        data = dict(data)
        data["mitre"] = [MitreMapping.from_dict(m) for m in data.get("mitre", [])]
        data["risk_factors"] = [RiskFactor.from_dict(r) for r in data.get("risk_factors", [])]
        return cls(**_filter_kwargs(cls, data))

    @property
    def mitre_ids(self) -> list[str]:
        return [m.technique_id for m in self.mitre]

    @property
    def display_id(self) -> str:
        return f"ALERT #{self.id:05d}"

    def ioc_items(self) -> list[tuple[str, str, int]]:
        items = []
        for key, count in self.iocs.items():
            ioc_type, _, value = key.partition("|")
            items.append((ioc_type, value, count))
        return sorted(items, key=lambda x: -x[2])


@dataclass
class ChainStage:
    stage: str
    label: str
    order: int
    first_ts: float | None
    last_ts: float | None
    count: int
    group_ids: list[int] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChainStage":
        return cls(**_filter_kwargs(cls, data))


@dataclass
class AttackChain:
    id: int
    entity_type: str  # host
    entity: str
    stages: list[ChainStage]
    first_ts: float | None
    last_ts: float | None
    scenario: str
    src_ips: list[str] = field(default_factory=list)
    users: list[str] = field(default_factory=list)
    group_ids: list[int] = field(default_factory=list)
    success_after_failures: bool = False

    @property
    def distinct_stages(self) -> int:
        return len({s.stage for s in self.stages})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AttackChain":
        data = dict(data)
        data["stages"] = [ChainStage.from_dict(s) for s in data.get("stages", [])]
        return cls(**_filter_kwargs(cls, data))


@dataclass
class Incident:
    id: str
    fingerprint: str
    kind: str
    title: str
    severity: str
    risk_score: float
    confidence: float
    assessment: str
    summary: str
    status: str = IncidentStatus.NEW.value
    affected_hosts: list[str] = field(default_factory=list)
    affected_users: list[str] = field(default_factory=list)
    source_ips: list[str] = field(default_factory=list)
    event_count: int = 0
    first_ts: float | None = None
    last_ts: float | None = None
    timeline: list[dict[str, Any]] = field(default_factory=list)
    chain: list[str] = field(default_factory=list)
    scenario: str = ""
    mitre: list[MitreMapping] = field(default_factory=list)
    iocs: list[str] = field(default_factory=list)
    cves: list[str] = field(default_factory=list)
    group_ids: list[int] = field(default_factory=list)
    fp_probability: float = 0.0
    fp_reasons: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    recommendations: dict[str, list[str]] = field(default_factory=dict)
    note: str = ""
    ai_analysis: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["mitre"] = [dict(m.__dict__) for m in self.mitre]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Incident":
        data = dict(data)
        data["mitre"] = [MitreMapping.from_dict(m) for m in data.get("mitre", [])]
        return cls(**_filter_kwargs(cls, data))


@dataclass
class IOCRecord:
    type: str  # ip | domain | url | md5 | sha1 | sha256
    value: str
    count: int = 0
    internal: bool = False
    first_seen: float | None = None
    last_seen: float | None = None
    hosts: list[str] = field(default_factory=list)
    group_ids: list[int] = field(default_factory=list)
    verdict: str = "unknown"
    sources: list[dict[str, Any]] = field(default_factory=list)
    country: str = ""
    asn: str = ""
    as_owner: str = ""
    tags: list[str] = field(default_factory=list)
    enriched: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IOCRecord":
        return cls(**_filter_kwargs(cls, data))


@dataclass
class CVERecord:
    cve: str
    count: int = 0
    hosts: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    cvss: float | None = None
    cvss_vector: str = ""
    severity: str = ""
    description: str = ""
    published: str = ""
    cwe: list[str] = field(default_factory=list)
    affected_software: list[str] = field(default_factory=list)
    known_exploited: bool = False
    kev_checked: bool = False  # True when the CISA KEV catalog was available for the lookup
    kev: dict[str, Any] = field(default_factory=dict)
    references: list[dict[str, str]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    remediation: str = ""
    enriched: bool = False
    group_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CVERecord":
        return cls(**_filter_kwargs(cls, data))


@dataclass
class AnalysisSummary:
    files: int = 0
    file_names: list[str] = field(default_factory=list)
    events: int = 0
    duplicates: int = 0
    parse_errors: int = 0
    rejected_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    first_ts: float | None = None
    last_ts: float | None = None
    agents: int = 0
    rules: int = 0
    groups: int = 0
    severity_counts: dict[str, int] = field(default_factory=dict)
    group_severity_counts: dict[str, int] = field(default_factory=dict)
    affected_hosts: int = 0
    affected_users: int = 0
    external_ips: int = 0
    cves: int = 0
    mitre_techniques: int = 0
    incidents: int = 0
    chains: int = 0
    iocs: int = 0
    parsers_used: dict[str, int] = field(default_factory=dict)
    mode: str = "offline"
    enrichment_status: str = ""
    duration_seconds: float = 0.0
    analyzed_at: float = 0.0
    executive_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisSummary":
        return cls(**_filter_kwargs(cls, data))
