import json
import threading
import zipfile

import pytest

from app.core.config import AppConfig
from app.core.errors import AnalysisCancelled
from app.database.store import GroupFilter
from app.services.pipeline import AnalysisPipeline


def run(paths, tmp_path, config=None, **kw):
    return AnalysisPipeline(config or AppConfig(), workspace=tmp_path / "ws", **kw).run(paths)


# ---------------------------------------------------------------- demo dataset expectations
def test_demo_summary(demo_session):
    s = demo_session.summary
    assert s.files == 9 and s.events > 2000 and s.parse_errors == 0
    assert set(s.parsers_used) == {"wazuh_jsonl", "wazuh_json", "wazuh_csv", "wazuh_xml", "wazuh_alerts_log", "cef"}
    assert s.severity_counts["critical"] > 0 and s.chains == 2
    assert "No confirmed compromise" not in s.executive_summary  # there IS a potential compromise
    assert "Potential compromise" in s.executive_summary
    assert "hacked" not in s.executive_summary.lower()


def test_demo_attack_chains(demo_session):
    chains = {c.entity: c for c in demo_session.store.chains()}
    assert set(chains) == {"web-01", "ws-fin-07"}
    web = [s.stage for s in chains["web-01"].stages]
    assert web == ["credential_attack", "initial_access", "execution", "persistence", "command_and_control"]
    win = [s.stage for s in chains["ws-fin-07"].stages]
    assert "credential_access" in win and "execution" in win and "command_and_control" in win
    incidents = [i for i in demo_session.incidents() if i.kind == "attack_chain"]
    assert all(i.severity == "critical" and i.assessment == "Potential compromise" for i in incidents)


def test_demo_bruteforce_card(demo_session):
    g = demo_session.groups(GroupFilter(src_ip="203.0.113.66", rule_id="5710"))[0]
    assert g.count == 147 and g.peak_count == 147
    assert g.ioc_verdict == "malicious" and g.success_after_failures
    assert "T1110" in g.mitre_ids or "T1110.001" in g.mitre_ids
    assert g.what_happened and g.why_it_matters and g.evidence and g.risk_factors
    assert g.recommendations["immediate"] and g.recommendations["investigation"]


def test_demo_internal_scanner_is_likely_benign(demo_session):
    groups = demo_session.groups(GroupFilter(src_ip="10.10.5.5"))
    assert groups and all(g.fp_probability >= 0.6 for g in groups)
    assert all(g.severity in ("low", "informational") for g in groups)
    assert all(not g.chain_ids for g in groups)
    inc = next(i for i in demo_session.incidents() if "10.10.5.5" in i.source_ips)
    assert inc.assessment == "Likely benign / possible false positive"


def test_demo_normal_activity_stays_low(demo_session):
    elevated = []
    for rule_id in ("5501", "5502", "503", "5402"):
        for g in demo_session.groups(GroupFilter(rule_id=rule_id), limit=1000):
            if g.chain_ids:
                elevated.append(g)  # e.g. the attacker's own session after the successful brute force
                continue
            assert g.severity in ("informational", "low"), (rule_id, g.agent_name, g.severity)
    assert elevated and all(g.agent_name == "web-01" for g in elevated)


def test_demo_cves_and_mitre(demo_session):
    cves = {c.cve: c for c in demo_session.store.cves()}
    assert cves["CVE-2021-44228"].cvss == 10.0 and len(cves["CVE-2021-44228"].hosts) == 2
    mitre = {m["technique_id"] for m in demo_session.mitre_stats()}
    assert {"T1110", "T1059.001", "T1003.001", "T1053.005"} <= mitre


def test_search(demo_session):
    res = demo_session.search("203.0.113.66")
    assert res.kind == "ip" and res.alerts >= 147 and res.hosts == ["web-01"] and res.incidents
    assert demo_session.search("CVE-2021-44228").alerts == 2
    assert demo_session.search("5710").kind == "rule"
    assert demo_session.search("T1003.001").alerts >= 1
    assert demo_session.search("deploy").users
    assert demo_session.search("9f2b5c0e1d4a7b3c6e8f0a1b2c3d4e5f60718293a4b5c6d7e8f9012345678abc").alerts >= 1
    assert demo_session.search("no-such-thing-xyz").empty


def test_pagination(demo_session):
    store = demo_session.store
    total = store.count_groups()
    page1 = store.group_rows(None, 0, 50)
    page2 = store.group_rows(None, 50, 50)
    assert len(page1) == 50 and not {r["id"] for r in page1} & {r["id"] for r in page2}
    assert total == demo_session.summary.groups
    assert store.count_alerts() == demo_session.summary.events
    assert len(store.query_alerts(None, None, "", 0, 100)) == 100


# ---------------------------------------------------------------- robustness
def test_offline_mode_never_uses_network(tmp_path, sample_dir, monkeypatch):
    import httpx

    def boom(*a, **k):
        raise AssertionError("network used in offline mode")

    monkeypatch.setattr(httpx.AsyncClient, "send", boom)
    s = run([sample_dir / "sample_bruteforce.json"], tmp_path, online=False)
    assert s.summary.mode == "offline" and s.summary.events > 0
    s.close()


def test_online_mode_without_internet_completes(tmp_path, sample_dir):
    import httpx

    def down(request):
        raise httpx.ConnectError("no route", request=request)

    cfg = AppConfig.model_validate({"network": {"mode": "online"}, "threat_intel": {"max_cve_lookups": 2}})
    s = run([sample_dir / "sample_cve.json"], tmp_path, cfg, http_transport=httpx.MockTransport(down))
    assert s.summary.enrichment_status == "Internet enrichment unavailable. Offline analysis completed."
    assert s.summary.events > 0 and s.incidents()
    s.close()


def test_corrupted_json_partial_results(tmp_path, alert_factory):
    good = json.dumps(alert_factory())
    path = tmp_path / "broken.json"
    path.write_text("[" + good + ",\n{\"rule\": {oops},\n" + json.dumps(alert_factory(full_log="2")) + "\n")
    s = run([path], tmp_path)
    assert s.summary.events == 2 and s.summary.parse_errors >= 1
    s.close()


def test_invalid_csv(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"rule.id,rule.level,agent.name\n5710,5,web\n\x00\x00garbage\"unterminated\n5715,3,web\n")
    s = run([path], tmp_path)
    assert s.summary.events >= 2
    s.close()


def test_missing_fields_and_unknown_rule(tmp_path, jsonl_writer):
    path = jsonl_writer(tmp_path / "odd.jsonl", [
        {"rule": {"id": "987654", "level": 9, "description": "Custom detection: something odd"}},
        {"agent": {"name": "x"}},
        {"rule": {"id": "100001"}, "full_log": "free text only"},
        {"completely": "different", "schema": True},
    ])
    s = run([path], tmp_path)
    assert s.summary.events == 4 and s.summary.parse_errors == 0
    g = s.groups(GroupFilter(rule_id="987654"))[0]
    assert g.category == "other" and g.title and g.recommendations is not None
    assert g.mitre == []  # no evidence -> no mapping
    s.close()


def test_empty_and_binary_input(tmp_path):
    (tmp_path / "empty.json").write_text("")
    (tmp_path / "bin.log").write_bytes(bytes(range(256)) * 10)
    s = run([tmp_path / "empty.json", tmp_path / "bin.log"], tmp_path)
    assert s.summary.files == 2  # nothing crashed
    s.close()


def test_huge_zip_rejected_other_files_analyzed(tmp_path, sample_dir):
    zpath = tmp_path / "bomb.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("alerts.json", b" " * (50 * 1024 * 1024))
    cfg = AppConfig.model_validate({"limits": {"max_compression_ratio": 100}})
    s = run([zpath, sample_dir / "sample_malware.json"], tmp_path, cfg)
    assert s.summary.rejected_inputs and s.summary.events > 0
    s.close()


def test_zip_input_analyzed(tmp_path, sample_dir):
    zpath = tmp_path / "logs.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(sample_dir / "sample_powershell.json", "export/sample_powershell.json")
    s = run([zpath], tmp_path)
    assert s.summary.events > 20 and s.summary.chains == 1
    s.close()


def test_duplicates_removed(tmp_path, sample_dir):
    f = sample_dir / "sample_malware.json"
    s = run([f, f], tmp_path)
    single = run([f], tmp_path)
    assert s.summary.events == single.summary.events and s.summary.duplicates == single.summary.events
    s.close()
    single.close()


def test_cancellation(tmp_path, sample_dir):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(AnalysisCancelled):
        AnalysisPipeline(AppConfig(), workspace=tmp_path / "ws", cancel=cancel).run([sample_dir])
    assert not list((tmp_path / "ws").glob("*.db"))


def test_progress_reported(tmp_path, sample_dir):
    seen = []
    s = AnalysisPipeline(AppConfig(), workspace=tmp_path / "ws", progress=seen.append).run(
        [sample_dir / "sample_normal_activity.json"])
    stages = {p.stage for p in seen}
    assert {"parse", "correlate", "enrich", "score", "finalize"} <= stages
    assert seen[-1].percent == 100.0
    assert all(0 <= p.percent <= 100 for p in seen)
    s.close()


def test_incident_status_persisted_across_runs(tmp_path, sample_dir):
    from app.database.state import StateStore

    state = StateStore(f"sqlite:///{tmp_path / 'state.db'}")
    s1 = AnalysisPipeline(AppConfig(), state=state, workspace=tmp_path / "ws").run([sample_dir / "sample_malware.json"])
    inc = s1.incidents()[0]
    s1.set_incident_status(inc.id, "CONFIRMED", state)
    s1.close()
    s2 = AnalysisPipeline(AppConfig(), state=state, workspace=tmp_path / "ws").run([sample_dir / "sample_malware.json"])
    again = next(i for i in s2.incidents() if i.fingerprint == inc.fingerprint)
    assert again.status == "CONFIRMED"
    s2.close()
    state.dispose()


def test_pathological_record_does_not_abort_file(tmp_path, alert_factory):
    deep = "[" * 900 + "]" * 900
    lines = [json.dumps(alert_factory(full_log="a")), '{"rule": {"id": "1"}, "x": ' + deep + "}",
             json.dumps(alert_factory(full_log="b"))]
    path = tmp_path / "deep.jsonl"
    path.write_text("\n".join(lines) + "\n")
    s = run([path], tmp_path)
    assert s.summary.events >= 2 and not s.summary.rejected_inputs
    s.close()
