from app.analyzers.false_positive import FalsePositiveAnalyzer
from app.analyzers.rule_knowledge import default_rule_kb
from app.utils.net import NetworkClassifier
from tests.unit.helpers import group

T0 = 1790762400.0


def analyzer(scanners=()):
    return FalsePositiveAnalyzer(NetworkClassifier(known_scanners=list(scanners)), default_rule_kb())


def test_known_scanner_is_likely_false_positive():
    g = group(src_ip="10.10.5.5", src_ips=["10.10.5.5"], src_external=False, count=40, peak_count=40)
    prob, benign, malicious = analyzer(["10.10.5.0/24"]).analyze(g)
    assert prob >= 0.6
    assert any("scanner" in r for r in benign)


def test_periodic_activity_detected():
    ts = [T0 + i * 3600 for i in range(12)]
    g = group(src_ip="10.0.0.9", src_external=False, timestamps=ts, count=12, peak_count=1)
    prob, benign, _ = analyzer().analyze(g)
    assert any("regular interval" in r for r in benign)
    assert any("spread out" in r for r in benign)
    assert prob >= 0.5


def test_weekly_recurrence():
    ts = [T0 + i * 7 * 86400 for i in range(4)]
    g = group(timestamps=ts, count=4)
    _, benign, _ = analyzer().analyze(g)
    assert any("every" in r and "day" in r for r in benign)


def test_malicious_context_lowers_probability():
    benign_g = group(count=10, peak_count=10)
    bad_g = group(count=10, peak_count=10, ioc_verdict="malicious", ioc_verdict_sources=["VirusTotal"],
                  success_after_failures=True, failures_before_success=10, chain_ids=[1])
    p_benign, _, _ = analyzer().analyze(benign_g)
    p_bad, _, reasons = analyzer().analyze(bad_g)
    assert p_bad < p_benign and p_bad <= 0.05
    assert any("malicious" in r for r in reasons)


def test_probability_bounds():
    g = group(rule_level=1, category="system", src_ip="10.0.0.1", src_external=False)
    p, _, _ = analyzer(["10.0.0.0/8"]).analyze(g)
    assert 0.02 <= p <= 0.95
