from app.core.config import AppConfig
from app.correlation.chains import ChainDetector
from app.correlation.grouping import GroupBuilder, peak_in_window
from app.correlation.incidents import IncidentBuilder, mark_campaigns
from app.analyzers.risk_engine import RiskEngine
from app.analyzers.normalizer import Normalizer
from app.recommendations.engine import RecommendationEngine
from app.utils.net import NetworkClassifier
from tests.unit.helpers import group

T0 = 1790762400.0


def rows(*items):
    """(agent, ts_offset_s, category, group_id, src, user)"""
    return [(a, T0 + off, cat, gid, src, user) for a, off, cat, gid, src, user in items]


def test_attack_chain_detected():
    groups = {i: group(id=i) for i in range(1, 6)}
    data = rows(*[("h1", i * 5, "auth_failure", 1, "203.0.113.5", "bob") for i in range(10)],
                ("h1", 60, "auth_success", 2, "203.0.113.5", "bob"),
                ("h1", 120, "execution", 3, "", "bob"),
                ("h1", 180, "credential_access", 4, "", ""),
                ("h1", 240, "network_c2", 5, "", ""))
    det = ChainDetector(60, 3, 5, 60, is_external=lambda ip: ip.startswith("203."))
    chains = det.run(data, groups)
    assert len(chains) == 1
    chain = chains[0]
    assert [s.stage for s in chain.stages] == ["credential_attack", "initial_access", "execution",
                                               "credential_access", "command_and_control"]
    assert chain.success_after_failures
    assert groups[2].success_after_failures and groups[2].failures_before_success == 10
    assert groups[1].success_after_failures
    assert all(1 in groups[i].chain_ids for i in range(1, 6))
    assert "Execution" in chain.scenario and "Command & Control" in chain.scenario


def test_isolated_events_do_not_form_chain():
    groups = {i: group(id=i) for i in range(1, 4)}
    data = rows(("h1", 0, "auth_failure", 1, "10.0.0.9", "x"),
                ("h1", 30, "auth_success", 2, "10.0.0.9", "x"),
                ("h1", 60, "privilege_escalation", 3, "", "x"))
    assert ChainDetector().run(data, groups) == []
    assert not groups[2].success_after_failures


def test_slow_periodic_failures_are_not_brute_force():
    groups = {1: group(id=1), 2: group(id=2)}
    data = rows(*[("h1", i * 3600, "auth_failure", 1, "10.10.5.5", "probe") for i in range(10)],
                ("h1", 9 * 3600 + 60, "auth_success", 2, "10.10.5.5", "probe"))
    det = ChainDetector(60, 3, 5, 60)
    assert det.run(data, groups) == []
    assert not groups[2].success_after_failures


def test_events_outside_window_split():
    groups = {i: group(id=i) for i in range(1, 4)}
    data = rows(("h1", 0, "execution", 1, "", ""), ("h1", 5 * 3600, "credential_access", 2, "", ""),
                ("h1", 10 * 3600, "network_c2", 3, "", ""))
    assert ChainDetector(60, 3).run(data, groups) == []


def test_chains_are_per_host():
    groups = {i: group(id=i) for i in range(1, 4)}
    data = rows(("a", 0, "execution", 1, "", ""), ("b", 10, "credential_access", 2, "", ""),
                ("c", 20, "network_c2", 3, "", ""))
    assert ChainDetector(60, 3).run(sorted(data), groups) == []


def test_peak_in_window():
    ts = [0, 10, 20, 30, 4000, 4010]
    assert peak_in_window(ts, 60, 6) == 4
    assert peak_in_window([0, 3600, 7200], 60, 3) == 1
    assert peak_in_window([0] * 400, 60, 5000) == 5000


def test_group_builder_source_keyed_auth_failures(alert_factory):
    norm = Normalizer()
    gb = GroupBuilder(NetworkClassifier())
    for user in ("admin", "root", "oracle"):
        a = norm.normalize(alert_factory(data={"srcip": "203.0.113.7", "dstuser": user}))
        a.category = "auth_failure"
        gb.add(a)
    assert len(gb.groups) == 1
    g = next(iter(gb.groups.values()))
    assert g.count == 3 and sorted(g.users) == ["admin", "oracle", "root"] and g.src_external


def test_group_builder_respects_max_groups(alert_factory):
    norm = Normalizer()
    gb = GroupBuilder(NetworkClassifier(), max_groups=2)
    for i in range(10):
        a = norm.normalize(alert_factory(rule_id="1", data={"dstuser": f"u{i}"}))
        a.category = "other"
        gb.add(a)
    assert len(gb.groups) <= 3
    assert sum(g.count for g in gb.groups.values()) == 10


def test_campaign_marking_and_incidents():
    config = AppConfig()
    g1 = group(id=1, agent_name="h1", count=30, peak_count=30)
    g2 = group(id=2, agent_name="h2", count=30, peak_count=30)
    g3 = group(id=3, agent_name="h3", category="vulnerability", cve="CVE-2021-44228", cvss=10.0, src_ip="",
               src_external=False, cves=["CVE-2021-44228"])
    g4 = group(id=4, agent_name="h3", category="malware", rule_level=12, src_ip="", src_external=False)
    groups = [g1, g2, g3, g4]
    mark_campaigns(groups, 10)
    assert g1.campaign and g2.campaign
    engine = RiskEngine(config)
    for g in groups:
        engine.score(g)
        g.title = g.rule_description
    incidents = IncidentBuilder(config, engine, RecommendationEngine()).build(groups, [])
    kinds = {i.kind for i in incidents}
    assert {"brute_force", "vulnerability", "malware"} <= kinds
    bf = next(i for i in incidents if i.kind == "brute_force")
    assert bf.affected_hosts == ["h1", "h2"] and bf.event_count == 60
    assert bf.id.startswith("INC-2026-")
    assert g1.incident_id == bf.id
    assert all(i.recommendations for i in incidents)


def test_incident_status_restored_by_fingerprint():
    config = AppConfig()
    g = group(id=1, count=30, peak_count=30)
    RiskEngine(config).score(g)
    statuses = {}
    first = IncidentBuilder(config, RiskEngine(config), RecommendationEngine(),
                            statuses.get).build([g], [])[0]
    statuses[first.fingerprint] = "INVESTIGATING"
    again = IncidentBuilder(config, RiskEngine(config), RecommendationEngine(), statuses.get).build([g], [])[0]
    assert again.status == "INVESTIGATING"
