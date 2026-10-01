"""Configurable, explainable risk scoring.

``risk = Σ factors`` where every factor is weighted by :class:`RiskWeights`
(``config.yaml -> risk_weights``).  The Wazuh rule level is only one input.  Each factor is
recorded with its reason so the GUI and reports can show *why* a score was given.
"""

from __future__ import annotations

import fnmatch
import math

from app.i18n import num, tr
from app.core.config import AppConfig, AssetRule
from app.core.severity import Severity, severity_from_score
from app.models.analysis import AlertGroup, RiskFactor
from app.models.categories import Category

C = Category
_AUTH_FAIL = {C.AUTH_FAILURE.value, C.BRUTE_FORCE.value}


class AssetResolver:
    def __init__(self, rules: list[AssetRule], default: str = "medium"):
        self.rules = rules
        self.default = default
        self._cache: dict[str, str] = {}

    def criticality(self, host: str) -> str:
        if host in self._cache:
            return self._cache[host]
        result = self.default
        lowered = (host or "").lower()
        for rule in self.rules:
            if fnmatch.fnmatch(lowered, rule.pattern.lower()):
                result = rule.criticality
                break
        self._cache[host] = result
        return result


class RiskEngine:
    def __init__(self, config: AppConfig):
        self.config = config
        self.weights = config.risk_weights
        self.thresholds = config.risk_thresholds
        self.assets = AssetResolver(config.wazuh.asset_criticality, config.wazuh.default_asset_criticality)
        self.bruteforce_threshold = config.correlation.bruteforce_threshold

    def score(self, group: AlertGroup, chain_stage_counts: dict[int, int] | None = None) -> None:
        w = self.weights
        factors: list[RiskFactor] = []

        level_points = group.rule_level / 15.0 * w.wazuh_level_max
        factors.append(RiskFactor("wazuh_level", level_points, tr("Wazuh rule level {level}/15", level=group.rule_level)))

        crit = self.assets.criticality(group.agent_name)
        group.asset_criticality = crit
        asset_points = w.asset_criticality.get(crit, 0.0)
        if asset_points:
            factors.append(RiskFactor("asset_criticality", asset_points,
                                      tr("Asset {host} criticality: {criticality}",
                                         host=group.agent_name or tr("unknown"), criticality=tr(crit))))

        if group.count > 1 and w.frequency_max:
            sat = max(w.frequency_saturation, 2)
            freq = w.frequency_max * min(1.0, math.log10(group.count) / math.log10(sat))
            factors.append(RiskFactor("frequency", freq, tr("{count} occurrences", count=num(group.count))))

        if group.src_external and group.category not in (C.VULNERABILITY.value, C.POLICY.value, C.SYSTEM.value):
            factors.append(RiskFactor("external_source", w.external_source,
                                      tr("Source {ip} is an external IP address", ip=group.src_ip)))

        if group.category in _AUTH_FAIL and group.peak_count >= self.bruteforce_threshold:
            factors.append(RiskFactor("bruteforce_pattern", w.bruteforce_pattern,
                                      tr("Burst of {count} failed authentications within {minutes} minutes "
                                         "(threshold {threshold})", count=num(group.peak_count),
                                         minutes=self.config.correlation.chain_window_minutes,
                                         threshold=self.bruteforce_threshold)))

        if group.success_after_failures:
            factors.append(RiskFactor("successful_auth", w.successful_auth_after_failures,
                                      tr("Successful authentication after {count} failures",
                                         count=group.failures_before_success)))
        elif group.category == C.AUTH_SUCCESS.value and group.src_external:
            factors.append(RiskFactor("successful_auth", w.successful_auth_external,
                                      tr("Successful authentication from an external IP")))

        if group.ioc_verdict == "malicious" or (group.vt_positives or 0) >= 3:
            reason = tr("Malicious indicator: {sources}", sources=", ".join(group.ioc_verdict_sources[:3])) if \
                group.ioc_verdict == "malicious" else tr("VirusTotal: {count} engines detected the file",
                                                         count=group.vt_positives)
            factors.append(RiskFactor("ioc_reputation", w.ioc_malicious, reason))
        elif group.ioc_verdict == "suspicious" or (group.vt_positives or 0) > 0:
            factors.append(RiskFactor("ioc_reputation", w.ioc_suspicious, tr("Indicator with suspicious reputation")))

        if group.cvss is not None:
            factors.append(RiskFactor("cve_severity", group.cvss / 10.0 * w.cve_max,
                                      tr("{cve} CVSS {cvss}", cve=group.cve or "CVE", cvss=f"{group.cvss:.1f}")))
        if group.kev:
            factors.append(RiskFactor("cve_known_exploited", w.cve_known_exploited,
                                      tr("{cve} is in CISA Known Exploited Vulnerabilities", cve=group.cve)))

        if group.mitre:
            best = 0.0
            best_reason = ""
            for m in group.mitre:
                tactic_w = max((w.mitre_tactic_weight.get(t, 0.3) for t in m.tactics), default=0.3)
                conf = w.mitre_confidence_factor.get(m.confidence, 0.4)
                pts = w.mitre_max * tactic_w * conf
                if pts > best:
                    best = pts
                    best_reason = tr("MITRE {technique} {name} ({confidence} confidence)", technique=m.technique_id,
                                     name=m.name, confidence=tr(m.confidence))
            if best:
                factors.append(RiskFactor("mitre_technique", best, best_reason))

        if group.chain_ids:
            stages = max((chain_stage_counts or {}).get(cid, 3) for cid in group.chain_ids)
            pts = w.correlation_chain + w.correlation_chain_per_extra_stage * max(0, stages - 3)
            factors.append(RiskFactor("correlation", pts, tr("Part of a correlated attack chain ({stages} stages)",
                                                             stages=stages)))
        elif group.campaign:
            factors.append(RiskFactor("correlation", w.correlation_campaign,
                                      tr("Same source targets several hosts (campaign)")))

        bonus = w.category_bonus.get(group.category, 0.0)
        if bonus:
            factors.append(RiskFactor("category", bonus, tr("Behaviour: {category}",
                                                            category=C.parse(group.category).label)))

        raw = sum(f.points for f in factors)
        if group.fp_probability and w.false_positive_dampening:
            reduction = raw * group.fp_probability * w.false_positive_dampening
            if reduction >= 0.5:
                factors.append(RiskFactor("false_positive_likelihood", -reduction,
                                          tr("False positive probability {probability}",
                                             probability=f"{group.fp_probability:.0%}")))
                raw -= reduction
        group.risk_factors = [RiskFactor(f.name, round(f.points, 1), f.reason) for f in factors]
        group.risk_score = round(max(0.0, min(100.0, raw)), 1)
        group.severity = severity_from_score(group.risk_score, self.thresholds).value
        group.confidence = self.confidence(group)

    @staticmethod
    def confidence(group: AlertGroup) -> float:
        """How well the evidence supports the assessment (not how dangerous it is)."""
        conf = 0.5
        if group.vendor == "wazuh" and group.rule_id not in ("unknown",):
            conf += 0.1
        if group.rule_mitre_ids:
            conf += 0.05
        if group.count >= 5 or group.chain_ids:
            conf += 0.1
        if group.ioc_verdict in ("malicious", "clean") or group.vt_positives is not None:
            conf += 0.1
        if group.agent_name and (group.src_ip or group.user or group.file_paths or group.cve):
            conf += 0.05
        if group.success_after_failures or group.kev:
            conf += 0.05
        if group.vendor == "generic":
            conf -= 0.15
        if group.rule_id == "unknown":
            conf -= 0.1
        return round(min(max(conf, 0.2), 0.98), 2)

    def severity_for(self, score: float) -> Severity:
        return severity_from_score(score, self.thresholds)
