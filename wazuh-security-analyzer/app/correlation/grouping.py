"""Aggregation of repeated alerts into :class:`AlertGroup` objects.

Grouping keys depend on behaviour: authentication failures, web attacks and scans are
grouped per (rule, host, source IP) with the set of targeted users collected, so that
"147 attempts with 60 usernames" becomes one finding instead of 60.  Other alerts are
grouped per (rule, host, source, user, CVE, file hash).  Memory is bounded by
``max_groups``; beyond it a coarser (rule, host) key is used.
"""

from __future__ import annotations

from app.models.alert import NormalizedAlert
from app.models.analysis import AlertGroup
from app.models.categories import Category
from app.utils.net import NetworkClassifier

_SOURCE_KEYED = {Category.AUTH_FAILURE.value, Category.BRUTE_FORCE.value, Category.WEB_ATTACK.value,
                 Category.SCAN.value, Category.NETWORK.value}

MAX_TIMESTAMPS = 400
MAX_LIST = 50
MAX_SAMPLES = 5
MAX_IOCS = 60


def _add_unique(values: list, value, limit: int = MAX_LIST) -> None:
    if value and len(values) < limit and value not in values:
        values.append(value)


def peak_in_window(timestamps: list[float], window_seconds: float, total: int) -> int:
    """Largest number of events inside any window of ``window_seconds`` (burst size).

    Only the first ``MAX_TIMESTAMPS`` timestamps are kept per group; when the group is larger
    than that and all sampled events fall in one window, the full count is assumed.
    """
    if not timestamps:
        return total
    ts = sorted(timestamps)
    best = 1
    left = 0
    for right, value in enumerate(ts):
        while value - ts[left] > window_seconds:
            left += 1
        best = max(best, right - left + 1)
    if best == len(ts) and total > len(ts):
        return total
    return best


class GroupBuilder:
    def __init__(self, network: NetworkClassifier, max_groups: int = 200_000):
        self.network = network
        self.max_groups = max_groups
        self.groups: dict[str, AlertGroup] = {}
        self._next_id = 1

    def key_for(self, alert: NormalizedAlert) -> str:
        coarse = len(self.groups) >= self.max_groups
        if coarse:
            return f"{alert.rule_id}|{alert.agent_name}|*"
        if alert.category in _SOURCE_KEYED and alert.src_ip:
            return f"{alert.rule_id}|{alert.agent_name}|{alert.src_ip}"
        if alert.category == Category.VULNERABILITY.value:
            return f"{alert.rule_id}|{alert.agent_name}|{alert.primary_cve}|{alert.package}"
        return "|".join((alert.rule_id, alert.agent_name, alert.src_ip, alert.user, alert.primary_cve,
                         alert.primary_hash, alert.command_line[:200] if alert.category == Category.EXECUTION.value
                         else ""))

    def add(self, alert: NormalizedAlert) -> int:
        key = self.key_for(alert)
        group = self.groups.get(key)
        if group is None:
            if len(self.groups) >= self.max_groups and key not in self.groups:
                key = f"{alert.rule_id}|{alert.agent_name}|*"
                group = self.groups.get(key)
        if group is None:
            group = AlertGroup(
                id=self._next_id,
                key=key,
                rule_id=alert.rule_id,
                rule_level=alert.rule_level,
                rule_description=alert.rule_description,
                category=alert.category,
                rule_groups=list(alert.rule_groups)[:20],
                agent_name=alert.agent_name,
                agent_ip=alert.agent_ip,
                src_ip=alert.src_ip,
                src_external=self.network.is_external(alert.src_ip),
                user=alert.user,
                cve=alert.primary_cve,
                file_hash=alert.primary_hash,
                representative=alert.context_dict(),
                vendor=alert.vendor,
                parser=alert.parser,
            )
            self._next_id += 1
            self.groups[key] = group
        self._update(group, alert)
        return group.id

    @staticmethod
    def _update(group: AlertGroup, alert: NormalizedAlert) -> None:
        group.count += 1
        if alert.rule_level > group.rule_level:
            group.rule_level = alert.rule_level
        ts = alert.timestamp
        if ts is not None:
            if group.first_ts is None or ts < group.first_ts:
                group.first_ts = ts
            if group.last_ts is None or ts > group.last_ts:
                group.last_ts = ts
            if len(group.timestamps) < MAX_TIMESTAMPS:
                group.timestamps.append(ts)
        _add_unique(group.users, alert.user)
        _add_unique(group.src_ips, alert.src_ip)
        _add_unique(group.dst_ips, alert.dst_ip)
        _add_unique(group.processes, alert.process, 20)
        _add_unique(group.command_lines, alert.command_line[:1000], 10)
        _add_unique(group.file_paths, alert.file_path, 20)
        _add_unique(group.packages, alert.package, 10)
        _add_unique(group.source_files, alert.source_file, 20)
        for cve in alert.cves:
            _add_unique(group.cves, cve, 20)
        for tid in alert.rule_mitre_ids:
            _add_unique(group.rule_mitre_ids, tid, 20)
        if alert.cvss is not None and (group.cvss is None or alert.cvss > group.cvss):
            group.cvss = alert.cvss
            group.vuln_severity = alert.vuln_severity
        if alert.vt_positives is not None and (group.vt_positives is None or alert.vt_positives > group.vt_positives):
            group.vt_positives = alert.vt_positives
            group.vt_total = alert.vt_total
        if len(group.sample_uids) < MAX_SAMPLES:
            group.sample_uids.append(alert.uid)
        if len(group.sample_logs) < 3 and alert.full_log and alert.full_log not in group.sample_logs:
            group.sample_logs.append(alert.full_log[:1000])
        iocs = group.iocs
        for ioc_type, value in alert.iocs:
            key = f"{ioc_type}|{value}"
            if key in iocs:
                iocs[key] += 1
            elif len(iocs) < MAX_IOCS:
                iocs[key] = 1
