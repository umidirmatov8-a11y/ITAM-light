"""Context-aware false-positive probability estimation.

The estimate is an explainable heuristic, not a statistical model: each observation adds
or removes probability and is reported as a human-readable reason, so the analyst can
judge it.  Reasons supporting a benign explanation are kept separately from reasons
against it.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

from app.models.analysis import AlertGroup
from app.models.categories import Category
from app.utils.net import NetworkClassifier
from app.utils.timeutil import fmt_duration

C = Category

_BENIGN_PRONE = {C.SYSTEM.value, C.POLICY.value, C.FIM.value, C.PROCESS_ACTIVITY.value,
                 C.PRIVILEGE_ESCALATION.value, C.AUTH_SUCCESS.value, C.NETWORK.value, C.OTHER.value}


def _periodicity(timestamps: list[float]) -> tuple[bool, float]:
    if len(timestamps) < 6:
        return False, 0.0
    ts = sorted(timestamps)
    intervals = [b - a for a, b in zip(ts, ts[1:]) if b - a > 0]
    if len(intervals) < 5:
        return False, 0.0
    mean = statistics.fmean(intervals)
    if mean < 30:  # bursts are not "scheduled"
        return False, mean
    cv = statistics.pstdev(intervals) / mean if mean else 1.0
    return cv < 0.15, mean


def _weekly(timestamps: list[float]) -> str:
    if len(timestamps) < 3:
        return ""
    ts = sorted(timestamps)
    if ts[-1] - ts[0] < 13 * 86400:
        return ""
    days = {datetime.fromtimestamp(t, tz=timezone.utc).strftime("%A") for t in ts}
    weeks = {datetime.fromtimestamp(t, tz=timezone.utc).isocalendar()[1] for t in ts}
    if len(days) == 1 and len(weeks) >= 3:
        return days.pop()
    return ""


class FalsePositiveAnalyzer:
    def __init__(self, network: NetworkClassifier, rule_kb=None):
        self.network = network
        self.rule_kb = rule_kb

    def analyze(self, group: AlertGroup) -> tuple[float, list[str], list[str]]:
        prob = 0.15
        benign: list[str] = []
        malicious: list[str] = []
        category = group.category

        scanners = [ip for ip in group.src_ips if self.network.is_known_scanner(ip)]
        if scanners:
            prob += 0.5
            benign.append(f"The source IP {scanners[0]} is configured as an authorised/internal scanner.")
        if group.src_ip and self.network.is_internal(group.src_ip) and category in (
                C.AUTH_FAILURE.value, C.BRUTE_FORCE.value, C.SCAN.value, C.WEB_ATTACK.value):
            prob += 0.1
            benign.append(f"The source {group.src_ip} is an internal address.")
        periodic, mean = _periodicity(group.timestamps)
        if periodic:
            prob += 0.15
            benign.append(f"The activity repeats at a regular interval (about every {fmt_duration(mean)}), "
                          "which is typical for scheduled jobs, monitoring or scanners.")
        weekday = _weekly(group.timestamps)
        if weekday:
            prob += 0.15
            benign.append(f"The same activity recurs every {weekday}.")
        if category == C.AUTH_FAILURE.value and group.count >= 3 and group.peak_count < 5:
            prob += 0.15
            benign.append(f"Failures are spread out over time (at most {group.peak_count} per correlation window) "
                          "rather than a rapid burst.")
        if category in (C.AUTH_FAILURE.value, C.BRUTE_FORCE.value) and not group.success_after_failures:
            prob += 0.05
            benign.append("No successful authentication from the same source was detected.")
        if not group.chain_ids and category not in (C.MALWARE.value, C.IMPACT.value, C.CREDENTIAL_ACCESS.value):
            prob += 0.05
            benign.append("No suspicious follow-up activity (execution, persistence, C2) was correlated.")
        if category in _BENIGN_PRONE:
            prob += 0.1
        if group.rule_level <= 3:
            prob += 0.15
            benign.append(f"Wazuh rule level {group.rule_level} is informational.")
        info = self.rule_kb.get(group.rule_id) if self.rule_kb else None
        if info and info.false_positives:
            prob += 0.05
            benign.append("Known benign causes for this rule: " + "; ".join(info.false_positives[:3]) + ".")
        if group.vendor == "generic":
            prob += 0.05

        if group.ioc_verdict == "malicious":
            prob -= 0.45
            malicious.append("An indicator in this alert is known to be malicious ("
                             + ", ".join(group.ioc_verdict_sources[:3]) + ").")
        elif group.ioc_verdict == "suspicious":
            prob -= 0.15
            malicious.append("An indicator in this alert has a suspicious reputation.")
        if group.chain_ids:
            prob -= 0.3
            malicious.append("The alert is part of a correlated multi-stage activity chain.")
        if group.success_after_failures:
            prob -= 0.3
            malicious.append(f"A successful authentication followed {group.failures_before_success} failures.")
        if group.vt_positives:
            prob -= 0.35
            malicious.append(f"{group.vt_positives} antivirus engines flagged the file as malicious.")
        if group.kev:
            prob -= 0.1
            malicious.append("The vulnerability is known to be exploited in the wild (CISA KEV).")
        if category in (C.CREDENTIAL_ACCESS.value, C.IMPACT.value):
            prob -= 0.2
            malicious.append("The command line contains attacker tooling patterns.")
        if group.src_external and category in (C.AUTH_SUCCESS.value,) and group.success_after_failures:
            prob -= 0.1
        if len(group.users) >= 5 and category in (C.AUTH_FAILURE.value, C.BRUTE_FORCE.value):
            prob -= 0.1
            malicious.append(f"{len(group.users)} different accounts were targeted, typical of username guessing.")
        if scanners:
            prob = max(prob, 0.6)
        return round(min(max(prob, 0.02), 0.95), 2), benign, malicious
