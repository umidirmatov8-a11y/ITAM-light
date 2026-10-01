from app.models.analysis import AlertGroup, MitreMapping


def group(**kw) -> AlertGroup:
    base = dict(id=1, key="k", rule_id="5710", rule_level=5, rule_description="sshd: invalid user",
                category="auth_failure", agent_name="web-01", agent_ip="10.0.0.5", src_ip="203.0.113.5",
                src_external=True, count=1, peak_count=1, first_ts=1790762400.0, last_ts=1790762400.0)
    base.update(kw)
    return AlertGroup(**base)


def mitre(tid="T1110", tactics=("credential-access",), confidence="medium"):
    return MitreMapping(tid, "x", list(tactics), confidence, "rule_kb", "e")
