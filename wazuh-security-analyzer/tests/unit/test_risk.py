import pytest
from pydantic import ValidationError

from app.analyzers.risk_engine import AssetResolver, RiskEngine
from app.core.config import AppConfig, AssetRule, RiskThresholds
from app.core.severity import Severity, severity_from_score
from tests.unit.helpers import group, mitre


def test_severity_bucketing_default_thresholds():
    t = RiskThresholds()
    assert severity_from_score(0, t) == Severity.INFORMATIONAL
    assert severity_from_score(19.9, t) == Severity.INFORMATIONAL
    assert severity_from_score(20, t) == Severity.LOW
    assert severity_from_score(40, t) == Severity.MEDIUM
    assert severity_from_score(60, t) == Severity.HIGH
    assert severity_from_score(80, t) == Severity.CRITICAL
    assert severity_from_score(100, t) == Severity.CRITICAL


def test_invalid_thresholds_rejected():
    with pytest.raises(ValidationError):
        RiskThresholds(critical=50, high=60)


def test_high_wazuh_level_alone_is_not_critical(config):
    g = group(rule_level=12, category="other", src_ip="", src_external=False)
    RiskEngine(config).score(g)
    assert g.severity not in ("critical", "high")
    assert any(f.name == "wazuh_level" for f in g.risk_factors)


def test_brute_force_example_is_high(config):
    # The specification example: rule 5710 at level 10, 147 attempts from an external IP -> HIGH
    g = group(rule_level=10, count=147, peak_count=147, users=["admin", "root"], mitre=[mitre()])
    RiskEngine(config).score(g)
    assert g.severity == "high"
    names = {f.name for f in g.risk_factors}
    assert {"wazuh_level", "frequency", "external_source", "bruteforce_pattern", "mitre_technique"} <= names


def test_successful_login_after_brute_force_and_malicious_ioc_is_critical(config):
    g = group(rule_id="5715", category="auth_success", rule_level=3, success_after_failures=True,
              failures_before_success=150, ioc_verdict="malicious", ioc_verdict_sources=["list"], chain_ids=[1],
              mitre=[mitre("T1078", ("initial-access",))])
    RiskEngine(config).score(g, {1: 5})
    assert g.severity == "critical"


def test_weights_are_configurable(config):
    g1 = group(count=50, peak_count=50)
    RiskEngine(config).score(g1)
    custom = AppConfig.model_validate({"risk_weights": {"bruteforce_pattern": 40, "external_source": 0}})
    g2 = group(count=50, peak_count=50)
    RiskEngine(custom).score(g2)
    assert g2.risk_score > g1.risk_score
    assert not any(f.name == "external_source" and f.points for f in g2.risk_factors)


def test_false_positive_dampening(config):
    g1 = group(count=20, peak_count=20)
    g2 = group(count=20, peak_count=20, fp_probability=0.8)
    engine = RiskEngine(config)
    engine.score(g1)
    engine.score(g2)
    assert g2.risk_score < g1.risk_score
    assert any(f.name == "false_positive_likelihood" for f in g2.risk_factors)


def test_cve_and_kev_factors(config):
    g = group(category="vulnerability", rule_id="23506", rule_level=13, cve="CVE-2021-44228", cvss=10.0, kev=True,
              src_ip="", src_external=False)
    RiskEngine(config).score(g)
    names = {f.name for f in g.risk_factors}
    assert {"cve_severity", "cve_known_exploited"} <= names


def test_score_is_clamped(config):
    g = group(rule_level=15, count=10000, peak_count=10000, success_after_failures=True, ioc_verdict="malicious",
              cvss=10.0, kev=True, chain_ids=[1], category="impact", mitre=[mitre("T1486", ("impact",), "high")])
    RiskEngine(config).score(g, {1: 8})
    assert g.risk_score == 100.0


def test_asset_criticality_glob():
    resolver = AssetResolver([AssetRule(pattern="dc*", criticality="critical"),
                              AssetRule(pattern="*db*", criticality="high")], "low")
    assert resolver.criticality("DC-01") == "critical"
    assert resolver.criticality("prod-db-2") == "high"
    assert resolver.criticality("ws-1") == "low"


def test_confidence_lower_for_generic_events(config):
    wazuh = group(count=10)
    generic = group(count=10, vendor="generic", rule_id="generic:event")
    engine = RiskEngine(config)
    engine.score(wazuh)
    engine.score(generic)
    assert generic.confidence < wazuh.confidence
