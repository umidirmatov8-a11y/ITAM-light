from app.analyzers.rule_knowledge import default_rule_kb
from app.recommendations.engine import SECTIONS, RecommendationEngine
from tests.unit.helpers import group


def test_brute_force_recommendations_are_concrete():
    g = group(count=147, peak_count=147, users=["admin"], user="admin", category="auth_failure",
              rule_groups=["sshd"], risk_score=65, severity="high", first_ts=1790762400.0)
    recs = RecommendationEngine(default_rule_kb()).for_group(g)
    assert set(recs) == set(SECTIONS)
    text = " ".join(s for steps in recs.values() for s in steps)
    assert "203.0.113.5" in text and "admin" in text and "web-01" in text
    assert "Investigate this alert" not in text
    assert all("{" not in s for steps in recs.values() for s in steps)  # no unrendered placeholders
    assert any("SSH" in s for s in recs["remediation"])  # 'ssh' condition


def test_user_not_named_when_many_accounts():
    g = group(count=50, peak_count=50, users=["a", "b", "c"], user="a", severity="high")
    recs = RecommendationEngine().for_group(g)
    joined = " ".join(recs["investigation"])
    assert "account 'a'" not in joined
    assert "a, b, c" in joined


def test_conditions_and_unless():
    engine = RecommendationEngine()
    plain = engine.for_group(group(count=20, peak_count=20, severity="high", risk_score=60))
    malicious = engine.for_group(group(count=20, peak_count=20, severity="high", risk_score=60,
                                       ioc_verdict="malicious"))
    assert any("once malicious activity is confirmed" in s for s in plain["immediate"])
    assert not any("once malicious activity is confirmed" in s for s in malicious["immediate"])
    assert any("confirmed malicious indicator" in s for s in malicious["immediate"])


def test_success_after_failures_adds_credential_reset():
    g = group(rule_id="5715", category="auth_success", users=["deploy"], user="deploy",
              success_after_failures=True, severity="critical", risk_score=90)
    recs = RecommendationEngine().for_group(g)
    assert any("deploy" in s and ("Reset" in s or "reset" in s) for s in recs["remediation"] + recs["immediate"])


def test_steps_with_missing_data_are_skipped():
    g = group(category="malware", src_ip="", src_external=False, file_paths=[], file_hash="", severity="high",
              risk_score=70)
    recs = RecommendationEngine().for_group(g)
    text = " ".join(s for steps in recs.values() for s in steps)
    assert "{file_path}" not in text and "{hash}" not in text


def test_informational_has_no_immediate_actions():
    g = group(category="system", rule_id="503", severity="informational", src_ip="")
    assert RecommendationEngine().for_group(g)["immediate"] == []
