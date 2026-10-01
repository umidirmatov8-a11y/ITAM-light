"""MITRE ATT&CK knowledge and evidence-based technique mapping.

Mapping sources and their confidence:

* ``wazuh_rule`` (high)   - technique IDs attached to the Wazuh rule in the alert itself.
* ``rule_kb`` (medium)    - technique from the local rule knowledge base for that rule ID.
* ``heuristic`` (medium/low) - derived from concrete evidence in the event (process name,
  command line, repeated failures).  Every heuristic mapping carries the evidence string.

Nothing is mapped without evidence; unknown IDs are validated against the local catalogue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import yaml

from app.core import paths
from app.models.analysis import MitreMapping
from app.models.categories import Category

TECHNIQUE_RE = re.compile(r"^T\d{4}(?:\.\d{3})?$")


@dataclass(frozen=True)
class Technique:
    id: str
    name: str
    tactics: tuple[str, ...]

    @property
    def url(self) -> str:
        return "https://attack.mitre.org/techniques/" + self.id.replace(".", "/") + "/"


class MitreCatalog:
    def __init__(self, path=None):
        data = yaml.safe_load((path or paths.knowledge_dir() / "mitre_techniques.yaml").read_text(encoding="utf-8"))
        self.tactics: dict[str, dict[str, str]] = data.get("tactics", {})
        self.techniques: dict[str, Technique] = {
            tid: Technique(tid, info["name"], tuple(info.get("tactics", [])))
            for tid, info in (data.get("techniques") or {}).items()
        }
        self._tactic_order = list(self.tactics.keys())

    def get(self, technique_id: str) -> Technique | None:
        return self.techniques.get(technique_id)

    def is_valid_id(self, technique_id: str) -> bool:
        return bool(TECHNIQUE_RE.match(technique_id or ""))

    def tactic_name(self, shortname: str) -> str:
        return self.tactics.get(shortname, {}).get("name", shortname.replace("-", " ").title())

    @property
    def tactic_order(self) -> list[str]:
        return self._tactic_order

    def mapping(self, technique_id: str, confidence: str, source: str, evidence: str) -> MitreMapping | None:
        technique_id = technique_id.strip().upper()
        if not self.is_valid_id(technique_id):
            return None
        tech = self.get(technique_id)
        if tech is None:
            parent = self.get(technique_id.split(".")[0])
            name = f"{parent.name} (sub-technique)" if parent else "Unknown technique (not in local catalogue)"
            tactics = list(parent.tactics) if parent else []
            url = "https://attack.mitre.org/techniques/" + technique_id.replace(".", "/") + "/"
        else:
            name, tactics, url = tech.name, list(tech.tactics), tech.url
        return MitreMapping(technique_id, name, tactics, confidence, source, evidence, url)


@lru_cache(maxsize=1)
def default_catalog() -> MitreCatalog:
    return MitreCatalog()


_CONF_RANK = {"high": 3, "medium": 2, "low": 1}

# (regex over process + command line, technique, confidence, evidence label)
_COMMAND_HEURISTICS: list[tuple[re.Pattern[str], str, str, str]] = [
    (re.compile(r"(?:^|[\\/\s\"'])(?:powershell|pwsh)(?:\.exe)?\b", re.I), "T1059.001", "medium", "PowerShell process"),
    (re.compile(r"(?:^|[\\/\s\"'])cmd(?:\.exe)?\s+/[ck]\b", re.I), "T1059.003", "medium", "cmd.exe /c execution"),
    (re.compile(r"(?:^|[\\/\s])(?:bash|sh|zsh)\s+-c\b", re.I), "T1059.004", "low", "Unix shell -c execution"),
    (re.compile(r"\s-(?:e|en|enc|enco|encodedcommand)\s+[A-Za-z0-9+/=]{16,}", re.I), "T1027", "medium",
     "Base64-encoded PowerShell command"),
    (re.compile(r"frombase64string", re.I), "T1140", "medium", "FromBase64String decoding"),
    (re.compile(r"downloadstring|downloadfile|invoke-webrequest|\biwr\b|start-bitstransfer|wget\s+http|curl\s+-[a-z]*o",
                re.I), "T1105", "medium", "Download command in command line"),
    (re.compile(r"certutil(?:\.exe)?\s+.*-urlcache", re.I), "T1105", "high", "certutil -urlcache download"),
    (re.compile(r"bitsadmin(?:\.exe)?\s+/transfer", re.I), "T1105", "medium", "bitsadmin /transfer"),
    (re.compile(r"mimikatz|sekurlsa|lsadump", re.I), "T1003.001", "high", "Mimikatz keywords"),
    (re.compile(r"procdump.*lsass|comsvcs(?:\.dll)?,?\s*minidump|lsass\.dmp", re.I), "T1003.001", "high",
     "LSASS memory dump"),
    (re.compile(r"reg(?:\.exe)?\s+save\s+hklm\\sam", re.I), "T1003.002", "high", "SAM hive export"),
    (re.compile(r"vssadmin(?:\.exe)?\s+delete\s+shadows|wmic\s+shadowcopy\s+delete|wbadmin\s+delete", re.I),
     "T1490", "high", "Shadow copy / backup deletion"),
    (re.compile(r"wevtutil(?:\.exe)?\s+cl\b|clear-eventlog", re.I), "T1070.001", "high", "Event log clearing"),
    (re.compile(r"schtasks(?:\.exe)?\s+/create", re.I), "T1053.005", "medium", "Scheduled task creation"),
    (re.compile(r"\\currentversion\\run", re.I), "T1547.001", "medium", "Run key modification"),
    (re.compile(r"\bsc(?:\.exe)?\s+create\b|new-service", re.I), "T1543.003", "medium", "Service creation"),
    (re.compile(r"rundll32(?:\.exe)?", re.I), "T1218.011", "low", "rundll32 execution"),
    (re.compile(r"mshta(?:\.exe)?", re.I), "T1218.005", "medium", "mshta execution"),
    (re.compile(r"regsvr32(?:\.exe)?\s+.*/i:", re.I), "T1218.010", "medium", "regsvr32 /i scriptlet"),
    (re.compile(r"set-mppreference\s+.*-disable|disableantispyware|netsh\s+advfirewall\s+set\s+.*state\s+off",
                re.I), "T1562.001", "high", "Security tool tampering"),
    (re.compile(r"\bnet(?:1)?(?:\.exe)?\s+user\s+\S+\s+\S+\s+/add", re.I), "T1136.001", "high", "net user /add"),
    (re.compile(r"\bnet(?:1)?(?:\.exe)?\s+localgroup\s+administrators\s+\S+\s+/add", re.I), "T1098", "high",
     "Added to local administrators"),
    (re.compile(r"\bwmic(?:\.exe)?\s+.*process\s+call\s+create", re.I), "T1047", "medium", "WMI process creation"),
    (re.compile(r"psexec|paexec", re.I), "T1569.002", "medium", "PsExec-style service execution"),
]


def map_alert_group(group, catalog: MitreCatalog, rule_kb, bruteforce_threshold: int) -> list[MitreMapping]:
    """Return evidence-based MITRE mappings for an alert group (deduplicated, best confidence wins)."""
    found: dict[str, MitreMapping] = {}

    def add(mapping: MitreMapping | None) -> None:
        if mapping is None:
            return
        existing = found.get(mapping.technique_id)
        if existing is None or _CONF_RANK[mapping.confidence] > _CONF_RANK[existing.confidence]:
            found[mapping.technique_id] = mapping

    for tid in group.rule_mitre_ids:
        add(catalog.mapping(tid, "high", "wazuh_rule", f"Technique attached to Wazuh rule {group.rule_id}"))

    info = rule_kb.get(group.rule_id) if rule_kb else None
    if info:
        for tid in info.mitre:
            add(catalog.mapping(tid, "medium", "rule_kb", f"Local rule knowledge base for rule {group.rule_id}"))

    category = group.category
    if category in (Category.AUTH_FAILURE.value, Category.BRUTE_FORCE.value) and \
            (group.peak_count >= bruteforce_threshold or category == Category.BRUTE_FORCE.value):
        if len(group.users) >= 5 and group.count >= bruteforce_threshold:
            add(catalog.mapping("T1110.003", "low", "heuristic",
                                f"{len(group.users)} different accounts targeted from one source"))
        add(catalog.mapping("T1110", "medium", "heuristic",
                            f"{group.peak_count} authentication failures from the same source in one window"))
    if group.success_after_failures:
        add(catalog.mapping("T1078", "medium", "heuristic",
                            f"Successful authentication after {group.failures_before_success} failures"))

    text = " ".join(group.processes[:5] + group.command_lines[:5])
    if text:
        for regex, tid, conf, label in _COMMAND_HEURISTICS:
            if regex.search(text):
                add(catalog.mapping(tid, conf, "heuristic", label))

    if category == Category.NETWORK_C2.value:
        ports = {str(p) for p in (group.representative.get("dst_port"),) if p}
        if ports & {"80", "443", "8080", "8443"}:
            add(catalog.mapping("T1071.001", "low", "heuristic", "Outbound web connection from a scripting process"))
        else:
            add(catalog.mapping("T1071", "low", "heuristic", "Outbound connection from a scripting process"))
    if category == Category.WEB_ATTACK.value and re.search(r"sql|injection|traversal|command", group.rule_description,
                                                           re.I):
        add(catalog.mapping("T1190", "medium", "heuristic", "Exploit attempt against a web application"))
    if category == Category.SCAN.value and not found:
        add(catalog.mapping("T1595", "low", "heuristic", "Scanning pattern from one source"))
    return sorted(found.values(), key=lambda m: (-_CONF_RANK[m.confidence], m.technique_id))
