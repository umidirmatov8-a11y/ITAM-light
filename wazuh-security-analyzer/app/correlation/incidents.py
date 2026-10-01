"""Incident building: turns correlated alert groups into analyst-facing incidents.

Incident kinds:

* ``attack_chain``     - multi-stage chain on one host (from :mod:`chains`)
* ``brute_force``      - authentication attack campaign from one source IP
* ``web_attack`` / ``scan`` - campaigns from one source IP
* ``malware``          - malicious files on one host
* ``vulnerability``    - high/critical or actively exploited CVE across hosts
* ``single``           - any other significant finding

Incident status (NEW, INVESTIGATING, ...) is persisted by fingerprint in the state DB, so
reloading the same logs keeps the analyst's triage decisions.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone

from app.core.severity import Severity
from app.models.analysis import AlertGroup, AttackChain, Incident, IncidentStatus, MitreMapping
from app.models.categories import Category
from app.utils.text import plural, truncate_list

C = Category

_AUTH = {C.AUTH_FAILURE.value, C.BRUTE_FORCE.value}
_CAMPAIGN_KINDS = {
    "brute_force": _AUTH,
    "web_attack": {C.WEB_ATTACK.value},
    "scan": {C.SCAN.value},
}
_NOTABLE_MEDIUM = {C.EXECUTION.value, C.CREDENTIAL_ACCESS.value, C.IMPACT.value, C.PERSISTENCE.value,
                   C.DEFENSE_EVASION.value, C.NETWORK_C2.value, C.ACCOUNT_CHANGE.value, C.LATERAL_MOVEMENT.value,
                   C.MALWARE.value}
_CONF_RANK = {"high": 3, "medium": 2, "low": 1}


def _fingerprint(kind: str, key: str) -> str:
    return hashlib.sha1(f"{kind}|{key}".encode("utf-8")).hexdigest()[:20]


def mark_campaigns(groups: list[AlertGroup], min_events: int) -> None:
    """Flag groups whose source IP targets several hosts (used by the risk engine)."""
    by_src: dict[tuple[str, str], list[AlertGroup]] = defaultdict(list)
    for g in groups:
        if not g.src_ip:
            continue
        for kind, cats in _CAMPAIGN_KINDS.items():
            if g.category in cats:
                by_src[(kind, g.src_ip)].append(g)
    for members in by_src.values():
        hosts = {g.agent_name for g in members}
        if len(hosts) >= 2 and sum(g.count for g in members) >= min_events:
            for g in members:
                g.campaign = True


class IncidentBuilder:
    def __init__(self, config, risk_engine, recommendation_engine, status_lookup=None):
        self.config = config
        self.risk_engine = risk_engine
        self.recs = recommendation_engine
        self.status_lookup = status_lookup or (lambda fp: None)
        self.threshold = config.correlation.bruteforce_threshold

    def build(self, groups: list[AlertGroup], chains: list[AttackChain]) -> list[Incident]:
        by_id = {g.id: g for g in groups}
        drafts: list[tuple[str, str, list[AlertGroup], AttackChain | None]] = []

        for chain in chains:
            members = [by_id[gid] for gid in chain.group_ids if gid in by_id]
            if members:
                drafts.append(("attack_chain", f"{chain.entity}|{int((chain.first_ts or 0) // 3600)}", members, chain))

        # Source campaigns
        campaigns: dict[tuple[str, str], list[AlertGroup]] = defaultdict(list)
        for g in groups:
            if not g.src_ip:
                continue
            for kind, cats in _CAMPAIGN_KINDS.items():
                if g.category in cats:
                    campaigns[(kind, g.src_ip)].append(g)
        success_by_src: dict[str, list[AlertGroup]] = defaultdict(list)
        for g in groups:
            if g.category == C.AUTH_SUCCESS.value and g.success_after_failures and g.src_ip:
                success_by_src[g.src_ip].append(g)
        for (kind, src), members in campaigns.items():
            total = sum(g.count for g in members)
            if kind == "brute_force":
                if total < self.threshold:
                    continue
                members = members + success_by_src.get(src, [])
            else:
                if total < self.config.correlation.campaign_min_events and \
                        max(g.risk_score for g in members) < self.config.risk_thresholds.high:
                    continue
            drafts.append((kind, src, members, None))

        # Malware per host
        malware: dict[str, list[AlertGroup]] = defaultdict(list)
        for g in groups:
            if g.category == C.MALWARE.value and Severity.parse(g.severity).rank >= Severity.MEDIUM.rank:
                malware[g.agent_name].append(g)
        for host, members in malware.items():
            drafts.append(("malware", host, members, None))

        # Vulnerabilities per CVE
        vulns: dict[str, list[AlertGroup]] = defaultdict(list)
        for g in groups:
            if g.category == C.VULNERABILITY.value and g.cve and ((g.cvss or 0) >= 7.0 or g.kev):
                vulns[g.cve].append(g)
        for cve, members in vulns.items():
            drafts.append(("vulnerability", cve, members, None))

        covered = {g.id for _, _, members, _ in drafts for g in members}
        for g in groups:
            if g.id in covered:
                continue
            rank = Severity.parse(g.severity).rank
            if rank >= Severity.HIGH.rank or (rank >= Severity.MEDIUM.rank and g.category in _NOTABLE_MEDIUM):
                drafts.append(("single", str(g.id) + "|" + g.key, [g], None))

        incidents = [self._make(kind, key, members, chain) for kind, key, members, chain in drafts]
        incidents.sort(key=lambda i: (-i.risk_score, i.first_ts or 0))
        incidents = incidents[: self.config.correlation.max_incidents]

        seq_by_year: dict[str, int] = defaultdict(int)
        for inc in sorted(incidents, key=lambda i: (i.first_ts or 0)):
            year = datetime.fromtimestamp(inc.first_ts, tz=timezone.utc).strftime("%Y") if inc.first_ts else \
                datetime.now(timezone.utc).strftime("%Y")
            seq_by_year[year] += 1
            inc.id = f"INC-{year}-{seq_by_year[year]:04d}"

        best: dict[int, Incident] = {}
        for inc in incidents:
            for gid in inc.group_ids:
                if gid not in best or inc.risk_score > best[gid].risk_score:
                    best[gid] = inc
        for gid, inc in best.items():
            if gid in by_id:
                by_id[gid].incident_id = inc.id
        return incidents

    # ------------------------------------------------------------------
    def _make(self, kind: str, key: str, members: list[AlertGroup], chain: AttackChain | None) -> Incident:
        members = sorted({g.id: g for g in members}.values(), key=lambda g: (g.first_ts or 0))
        top = max(members, key=lambda g: g.risk_score)
        hosts = sorted({g.agent_name for g in members if g.agent_name})
        users = sorted({u for g in members for u in g.users if u})
        srcs = sorted({ip for g in members for ip in g.src_ips if ip})
        count = sum(g.count for g in members)
        first = min((g.first_ts for g in members if g.first_ts is not None), default=None)
        last = max((g.last_ts for g in members if g.last_ts is not None), default=None)
        success = any(g.success_after_failures and g.category == C.AUTH_SUCCESS.value for g in members)

        risk = top.risk_score
        reasoning = [f"Highest-risk finding: {top.display_id} \"{top.title}\" scored {top.risk_score:.0f}/100."]
        if chain is not None:
            bonus = 3 * max(0, chain.distinct_stages - 2) + (10 if chain.success_after_failures else 0)
            risk += bonus
            reasoning.append(f"Correlated chain with {chain.distinct_stages} kill-chain stages: {chain.scenario}.")
        elif kind in _CAMPAIGN_KINDS and len(hosts) >= 2 and top.fp_probability < 0.6:
            risk += min(10, 2 * len(hosts))
            reasoning.append(f"The same source targeted {len(hosts)} hosts.")
        if success:
            risk += 5
            reasoning.append("A successful authentication followed repeated failures.")
        risk = round(min(100.0, risk), 1)
        severity = self.risk_engine.severity_for(risk).value

        title, assessment, summary = self._describe(kind, key, members, chain, hosts, users, srcs, count, success)
        mitre: dict[str, MitreMapping] = {}
        for g in members:
            for m in g.mitre:
                if m.technique_id not in mitre or _CONF_RANK[m.confidence] > _CONF_RANK[mitre[m.technique_id].confidence]:
                    mitre[m.technique_id] = m
        iocs: list[str] = []
        for g in members:
            for t, v, _ in g.ioc_items():
                if t in ("ip", "domain", "url", "sha256", "sha1", "md5"):
                    entry = f"{t}:{v}"
                    if entry not in iocs and (t != "ip" or g.src_external or v != g.agent_ip):
                        iocs.append(entry)
        cves = sorted({c for g in members for c in g.cves})
        weights = [max(g.risk_score, 1.0) for g in members]
        fp = sum(g.fp_probability * w for g, w in zip(members, weights)) / sum(weights)
        if chain is not None or success:
            fp = min(fp, 0.15)
        fp_reasons = []
        for g in members:
            for r in g.fp_reasons:
                if r not in fp_reasons:
                    fp_reasons.append(r)
        evidence = []
        for g in sorted(members, key=lambda g: -g.risk_score)[:6]:
            evidence.append(g.evidence[0] if g.evidence else g.rule_description)
        timeline = self._timeline(members, chain)
        fingerprint = _fingerprint(kind, key)
        status = self.status_lookup(fingerprint) or IncidentStatus.NEW.value
        confidence = round(min(0.98, max(g.confidence for g in members) + (0.05 if chain else 0.0)), 2)

        incident = Incident(
            id="",
            fingerprint=fingerprint,
            kind=kind,
            title=title,
            severity=severity,
            risk_score=risk,
            confidence=confidence,
            assessment=assessment,
            summary=summary,
            status=status,
            affected_hosts=hosts[:200],
            affected_users=users[:200],
            source_ips=srcs[:200],
            event_count=count,
            first_ts=first,
            last_ts=last,
            timeline=timeline,
            chain=[s.label for s in chain.stages] if chain else [],
            scenario=chain.scenario if chain else "",
            mitre=sorted(mitre.values(), key=lambda m: (-_CONF_RANK[m.confidence], m.technique_id)),
            iocs=iocs[:50],
            cves=cves[:50],
            group_ids=[g.id for g in members][:1000],
            fp_probability=round(fp, 2),
            fp_reasons=fp_reasons[:6],
            evidence=evidence,
            reasoning=reasoning,
        )
        incident.recommendations = self.recs.for_incident(incident, members)
        return incident

    @staticmethod
    def _timeline(members: list[AlertGroup], chain: AttackChain | None) -> list[dict]:
        if chain is not None:
            return [{"ts": s.first_ts, "end": s.last_ts, "text": f"{s.label}: {s.description}", "count": s.count,
                     "severity": "", "group_ids": s.group_ids[:20], "stage": s.stage} for s in chain.stages]
        items = []
        for g in sorted(members, key=lambda g: (g.first_ts or 0))[:40]:
            items.append({"ts": g.first_ts, "end": g.last_ts, "text": f"[{g.rule_id}] {g.rule_description}",
                          "count": g.count, "severity": g.severity, "group_ids": [g.id], "stage": g.category})
        return items

    def _describe(self, kind, key, members, chain, hosts, users, srcs, count, success):
        host_txt = truncate_list(hosts, 3)
        if kind == "attack_chain":
            title = f"Possible attack chain on {chain.entity}"
            assessment = "Potential compromise" if chain.success_after_failures else "Possible attack chain"
            summary = (f"{plural(count, 'event')} on {chain.entity} form a sequence of {chain.distinct_stages} attack "
                       f"stages: {chain.scenario}." + (" A successful login followed repeated failures."
                                                        if chain.success_after_failures else "") +
                       " The individual alerts should be investigated together as one incident.")
        elif kind == "brute_force":
            burst = any(g.peak_count >= self.threshold or g.category == C.BRUTE_FORCE.value for g in members)
            if burst or success:
                title = f"Possible brute-force attack from {key}"
                assessment = "Potential compromise" if success else "Likely brute-force activity"
            else:
                title = f"Repeated authentication failures from {key}"
                top = max(members, key=lambda g: g.risk_score)
                assessment = top.assessment or "Suspicious activity"
            summary = (f"{plural(count, 'authentication event')} from {key} against {plural(len(hosts), 'host')} "
                       f"({host_txt}) and {plural(len(users), 'account')}." +
                       (" At least one login from this source succeeded afterwards." if success else
                        " No successful login from this source was found in the analyzed logs."))
        elif kind == "web_attack":
            title = f"Web attack campaign from {key}"
            assessment = "Possible attack"
            summary = f"{plural(count, 'malicious web request')} from {key} against {host_txt}."
        elif kind == "scan":
            title = f"Scanning from {key}"
            assessment = "Suspicious activity"
            summary = f"{plural(count, 'scan event')} from {key} against {plural(len(hosts), 'host')} ({host_txt})."
        elif kind == "malware":
            title = f"Malware detected on {key or 'unknown host'}"
            top = max(members, key=lambda g: g.risk_score)
            assessment = top.assessment or "Suspicious activity"
            files = truncate_list([p for g in members for p in g.file_paths], 3)
            summary = f"{plural(len(members), 'malware finding')} on {key}: {files}."
        elif kind == "vulnerability":
            g0 = members[0]
            title = f"{key} on {plural(len(hosts), 'host')}"
            assessment = "Exposure (actively exploited vulnerability)" if any(g.kev for g in members) else \
                "Exposure (vulnerable software)"
            summary = (f"{key}" + (f" (CVSS {g0.cvss:.1f})" if g0.cvss is not None else "") +
                       f" affects {truncate_list(sorted({p for g in members for p in g.packages}), 3)} on {host_txt}. "
                       "No exploitation was observed in the analyzed logs.")
        else:
            g = members[0]
            title = g.title or g.rule_description
            assessment = g.assessment
            summary = g.what_happened
        return title, assessment, summary
