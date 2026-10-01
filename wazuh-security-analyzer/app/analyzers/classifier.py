"""Deterministic behavioural classification of normalized alerts.

Order of precedence: rule knowledge base -> Wazuh rule groups -> Windows/Sysmon event IDs ->
description keywords.  Concrete command-line evidence (credential dumping, shadow copy
deletion, log clearing, encoded PowerShell, ...) can escalate a benign category.
"""

from __future__ import annotations

import re

from app.models.alert import NormalizedAlert
from app.models.categories import Category
from app.utils.net import NetworkClassifier

C = Category

_GROUP_MAP: list[tuple[frozenset[str], Category]] = [
    (frozenset({"vulnerability-detector", "vulnerability_detector", "vulnerability"}), C.VULNERABILITY),
    (frozenset({"rootcheck"}), C.MALWARE),
    (frozenset({"sca"}), C.POLICY),
    (frozenset({"syscheck", "syscheck_entry_modified", "syscheck_entry_added", "syscheck_entry_deleted",
                "syscheck_file", "syscheck_registry"}), C.FIM),
    (frozenset({"sql_injection", "xss", "web_attack", "attack_web"}), C.WEB_ATTACK),
    (frozenset({"web_scan", "recon", "scan", "portscan"}), C.SCAN),
    (frozenset({"authentication_success", "win_authentication_success"}), C.AUTH_SUCCESS),
    (frozenset({"authentication_failed", "authentication_failures", "invalid_login", "win_authentication_failed",
                "login_denied"}), C.AUTH_FAILURE),
    (frozenset({"adduser", "addgroup", "account_changed", "group_changed", "group_created", "user_created",
                "account_created", "account_deleted", "account_enabled"}), C.ACCOUNT_CHANGE),
    (frozenset({"sudo", "su"}), C.PRIVILEGE_ESCALATION),
    (frozenset({"firewall_drop", "firewall", "iptables", "netscreenfw", "pf", "fortigate"}), C.NETWORK),
    (frozenset({"ids", "suricata", "snort"}), C.NETWORK),
    (frozenset({"ossec", "wazuh", "agent", "agent_restarting", "agent_flooding", "service_availability"}), C.SYSTEM),
]

_WIN_EVENT_MAP = {
    "1102": C.DEFENSE_EVASION, "104": C.DEFENSE_EVASION,
    "4720": C.ACCOUNT_CHANGE, "4722": C.ACCOUNT_CHANGE, "4724": C.ACCOUNT_CHANGE, "4728": C.ACCOUNT_CHANGE,
    "4732": C.ACCOUNT_CHANGE, "4756": C.ACCOUNT_CHANGE, "4738": C.ACCOUNT_CHANGE,
    "4625": C.AUTH_FAILURE, "4771": C.AUTH_FAILURE, "4776": C.AUTH_FAILURE,
    "4624": C.AUTH_SUCCESS, "4648": C.AUTH_SUCCESS,
    "7045": C.PERSISTENCE, "4697": C.PERSISTENCE, "4698": C.PERSISTENCE,
    "4672": C.PRIVILEGE_ESCALATION,
}

_SYSMON_GROUP_HINTS = (
    ("sysmon_event1", C.PROCESS_ACTIVITY), ("sysmon_eid1", C.PROCESS_ACTIVITY),
    ("sysmon_event3", C.NETWORK), ("sysmon_eid3", C.NETWORK),
    ("sysmon_event_10", C.CREDENTIAL_ACCESS), ("sysmon_eid10", C.CREDENTIAL_ACCESS),
    ("sysmon_event_13", C.PERSISTENCE), ("sysmon_eid13", C.PERSISTENCE),
    ("sysmon_event_11", C.PROCESS_ACTIVITY), ("sysmon_event_22", C.NETWORK),
)

_KEYWORDS: list[tuple[re.Pattern[str], Category]] = [
    (re.compile(r"brute.?force|multiple (?:authentication|logon|login) fail|password spray", re.I), C.BRUTE_FORCE),
    (re.compile(r"ransom|wiper|shadow cop(?:y|ies) delet", re.I), C.IMPACT),
    (re.compile(r"malware|trojan|virus|backdoor|rootkit|virustotal|infected|yara", re.I), C.MALWARE),
    (re.compile(r"mimikatz|credential dump|lsass", re.I), C.CREDENTIAL_ACCESS),
    (re.compile(r"sql injection|xss|cross site|web attack|path traversal|command injection|shellshock", re.I),
     C.WEB_ATTACK),
    (re.compile(r"(?:port )?scan|reconnaissance|version gathering|enumeration", re.I), C.SCAN),
    (re.compile(r"authentication fail|login fail|logon fail|failed password|invalid user|non-existent user|"
                r"bad password|unknown user", re.I), C.AUTH_FAILURE),
    (re.compile(r"authentication success|logon success|login success|accepted password|session opened|"
                r"successful login", re.I), C.AUTH_SUCCESS),
    (re.compile(r"audit log was cleared|log cleared|event log.*clear|defender.*disabled|tamper", re.I),
     C.DEFENSE_EVASION),
    (re.compile(r"powershell|encoded command|script block|cmd\.exe|wscript|cscript|mshta", re.I), C.EXECUTION),
    (re.compile(r"scheduled task|new service|service installed|run key|autorun|cron", re.I), C.PERSISTENCE),
    (re.compile(r"user (?:account )?(?:created|added|deleted)|group (?:created|changed|member)|added to .*group",
                re.I), C.ACCOUNT_CHANGE),
    (re.compile(r"sudo|privilege|elevat", re.I), C.PRIVILEGE_ESCALATION),
    (re.compile(r"psexec|wmiexec|remote service|pass.the.hash|lateral", re.I), C.LATERAL_MOVEMENT),
    (re.compile(r"checksum changed|integrity|file (?:added|deleted|modified)", re.I), C.FIM),
    (re.compile(r"vulnerab|cve-", re.I), C.VULNERABILITY),
    (re.compile(r"agent (?:started|stopped|disconnected)|wazuh server|ossec server", re.I), C.SYSTEM),
    (re.compile(r"firewall|connection (?:dropped|blocked)|outbound connection", re.I), C.NETWORK),
]

_IMPACT_CMD = re.compile(r"vssadmin(?:\.exe)?\s+delete\s+shadows|wmic\s+shadowcopy\s+delete|wbadmin\s+delete|"
                         r"bcdedit.*recoveryenabled\s+no|cipher(?:\.exe)?\s+/w", re.I)
_CRED_CMD = re.compile(r"mimikatz|sekurlsa|lsadump|procdump.*lsass|comsvcs(?:\.dll)?,?\s*minidump|"
                       r"reg(?:\.exe)?\s+save\s+hklm\\(?:sam|security)", re.I)
_EVASION_CMD = re.compile(r"wevtutil(?:\.exe)?\s+cl\b|clear-eventlog|set-mppreference\s+.*-disable|"
                          r"netsh\s+advfirewall\s+set\s+.*state\s+off", re.I)
_PERSIST_CMD = re.compile(r"schtasks(?:\.exe)?\s+/create|\\currentversion\\run|\bsc(?:\.exe)?\s+create\b|new-service",
                          re.I)
_EXEC_CMD = re.compile(r"\s-(?:e|en|enc|enco|encodedcommand)\s+[A-Za-z0-9+/=]{16,}|frombase64string|downloadstring|"
                       r"downloadfile|invoke-expression|\biex\b|invoke-webrequest|-nop\b.*-w(?:indowstyle)?\s+hidden|"
                       r"certutil(?:\.exe)?\s+.*-urlcache|bitsadmin(?:\.exe)?\s+/transfer|mshta(?:\.exe)?\s+http|"
                       r"regsvr32(?:\.exe)?\s+.*/i:http|(?:curl|wget)\b[^|;]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b|"
                       r"base64\s+(?:-d|--decode)[^|]*\|\s*(?:ba)?sh\b|/dev/tcp/", re.I)
_SCRIPT_PROCS = re.compile(r"(?:^|[\\/])(?:powershell|pwsh|cmd|rundll32|regsvr32|mshta|wscript|cscript|certutil|"
                           r"bitsadmin|msbuild|installutil|bash|sh|dash|zsh|nc|ncat|socat|perl|python[0-9.]*)"
                           r"(?:\.exe)?$", re.I)


class AlertClassifier:
    def __init__(self, rule_kb, network: NetworkClassifier):
        self.rule_kb = rule_kb
        self.network = network

    def classify(self, alert: NormalizedAlert) -> str:
        category = self._base_category(alert)
        return self._escalate(alert, category).value

    def _base_category(self, alert: NormalizedAlert) -> Category:
        if alert.vt_positives is not None:
            return C.MALWARE if alert.vt_positives > 0 else C.OTHER
        info = self.rule_kb.get(alert.rule_id) if self.rule_kb else None
        if info:
            return Category.parse(info.category)
        groups = {g.lower() for g in alert.rule_groups}
        if alert.cves and (alert.cvss is not None or alert.package or "vulnerability-detector" in groups):
            return C.VULNERABILITY
        for hint, category in _SYSMON_GROUP_HINTS:
            if hint in groups:
                return category
        event_id = (alert.raw or {}).get("_win_event_id", "") if alert.raw else ""
        if event_id and event_id in _WIN_EVENT_MAP:
            return _WIN_EVENT_MAP[event_id]
        description = alert.rule_description
        # Composite "multiple failures" rules describe brute force even when grouped as auth failures.
        if re.search(r"brute.?force|multiple .*fail", description, re.I) and \
                groups & {"authentication_failed", "authentication_failures", "invalid_login"}:
            return C.BRUTE_FORCE
        for group_set, category in _GROUP_MAP:
            if groups & group_set:
                return category
        if alert.file_path and ("syscheck" in (alert.decoder or "") or groups & {"syscheck"}):
            return C.FIM
        for regex, category in _KEYWORDS:
            if regex.search(description):
                return category
        return C.OTHER

    def _escalate(self, alert: NormalizedAlert, category: Category) -> Category:
        if category in (C.MALWARE, C.VULNERABILITY, C.IMPACT, C.CREDENTIAL_ACCESS):
            return category
        text = f"{alert.process} {alert.command_line}" if (alert.process or alert.command_line) else ""
        if category == C.CREDENTIAL_ACCESS or not text.strip():
            return category
        if _IMPACT_CMD.search(text):
            return C.IMPACT
        if _CRED_CMD.search(text):
            return C.CREDENTIAL_ACCESS
        if _EVASION_CMD.search(text):
            return C.DEFENSE_EVASION
        if category in (C.PROCESS_ACTIVITY, C.OTHER, C.EXECUTION, C.NETWORK, C.PERSISTENCE, C.PRIVILEGE_ESCALATION):
            if _PERSIST_CMD.search(text):
                return C.PERSISTENCE
            if _EXEC_CMD.search(text):
                return C.EXECUTION
        if category == C.NETWORK and alert.process and _SCRIPT_PROCS.search(alert.process.strip('"')):
            if alert.dst_ip and self.network.is_external(alert.dst_ip):
                return C.NETWORK_C2
        if category == C.PROCESS_ACTIVITY and alert.rule_level >= 10:
            return C.EXECUTION
        return category
