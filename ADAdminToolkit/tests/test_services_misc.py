from pathlib import Path

import pytest

from adtoolkit.core import errors as E
from adtoolkit.models.records import Evidence, Severity
from adtoolkit.services import network_service as N
from adtoolkit.services.audit_service import AuditService
from adtoolkit.services.compare_service import CompareService
from adtoolkit.services.computer_service import ComputerQuery, ComputerService, ComputerView
from adtoolkit.services.dashboard_service import DashboardService
from adtoolkit.services.events_service import EventQuery, EventsService, build_xpath, lockout_summary, parse_events_xml
from adtoolkit.services.explorer_service import Condition, ExplorerService, build_filter, validate_attributes
from adtoolkit.services.offboarding_service import DEFAULT_TEMPLATE, OffboardingService
from adtoolkit.services.ou_service import OUService
from adtoolkit.services.password_service import (PasswordOptions, check_complexity, entropy_bits, generate_password,
                                                 validate_against_policy)
from adtoolkit.services.report_service import ReportService

from .conftest import find_user


def test_dashboard_exact_counts(ctx):
    s = DashboardService(ctx).collect()
    m = s.metrics
    assert m["users_total"].value == m["users_enabled"].value + m["users_disabled"].value
    assert m["users_locked"].value == 3 and m["users_locked"].exact
    assert not m["users_stale"].exact and s.collected_at is not None and not s.errors


def test_dashboard_reports_errors(ctx):
    from adtoolkit.ldap import error_mapping as EM
    ctx.gateway.store.fail_next.append(("search", {"result": EM.BUSY, "message": "busy"}))
    s = DashboardService(ctx).collect()
    assert s.metrics["users_total"].error and s.errors
    assert s.metrics["computers_total"].value       # other sections still collected


def test_audit_runs_all_checks(ctx):
    a = AuditService(ctx)
    results = a.run()
    assert not [r for r in results if r.error]
    summary = a.summary(results)
    assert summary["total"] > 0 and summary["by_evidence"][Evidence.REVIEW] > 0
    titles = {f.title for r in results for f in r.findings}
    assert "Флаг PASSWD_NOTREQD (пароль не требуется)" in titles
    assert "Вложенная группа в критичной группе" in titles
    assert "Циклическое вложение групп" in titles
    stale = next(r for r in results if r.check_id == "stale_users")
    assert stale.limitations and all(f.evidence in (Evidence.REVIEW, Evidence.LIMITED) for f in stale.findings)
    assert all(f.severity is not Severity.CRITICAL for f in stale.findings)


def test_reports_have_metadata(ctx):
    rs = ReportService(ctx)
    for d in rs.reports:
        tables = rs.build(d.report_id, {"days": 90})
        assert tables
        for t in tables:
            assert t.domain == "demo.local" and t.dc and t.generated_at


def test_computers(ctx):
    cs = ComputerService(ctx)
    outdated = cs.search(ComputerQuery(view=ComputerView.OUTDATED_OS)).items
    assert any("Windows XP" in c.os for c in outdated) and all(c.os_support.value == "outdated" for c in outdated)
    dcs = cs.search(ComputerQuery(view=ComputerView.DOMAIN_CONTROLLERS)).items
    assert len(dcs) == 2
    with pytest.raises(E.ProtectedObjectError):
        cs.set_enabled(dcs[0].dn, False)
    ws = cs.search(ComputerQuery(text="WS-0005")).items[0]
    assert cs.set_enabled(ws.dn, False) and not cs.get(ws.dn).enabled
    assert any("LDAP НЕ показывает" in n for n in cs.search(ComputerQuery()).notes)


def test_ou_service(ctx, tmp_path):
    ou = OUService(ctx)
    root = ou.tree()
    names = {n.name for n in root.walk()}
    assert {"Company", "Users", "IT", "Workstations"} <= names
    empty = {n.name for n in ou.empty_ous()}
    assert empty == {"Archive", "Old Project"}
    assert ou.is_protected("OU=Company,DC=demo,DC=local") is True
    with pytest.raises(E.ValidationError):
        ou.delete_empty_ou("OU=Archive,OU=Company,DC=demo,DC=local", confirmed_name="wrong")
    with pytest.raises(E.ConstraintViolationError):
        ou.delete_empty_ou("OU=IT,OU=Users,OU=Company,DC=demo,DC=local", confirmed_name="IT")
    before = ou.snapshot()
    ou.delete_empty_ou("OU=Archive,OU=Company,DC=demo,DC=local", confirmed_name="Archive")
    ou.create_ou("OU=Company,DC=demo,DC=local", "New OU")
    for ext in ("json", "csv"):
        path = tmp_path / f"s.{ext}"
        ou.save_snapshot(before, path)
        loaded = ou.load_snapshot(path)
        diff = ou.compare_snapshots(loaded, ou.snapshot())
        assert diff.added == ["demo.local/Company/New OU"] and diff.removed == ["demo.local/Company/Archive"]


def test_password_generation_and_policy(ctx):
    pwd = generate_password(PasswordOptions(length=20))
    assert len(pwd) == 20 and any(c.isdigit() for c in pwd) and any(c.isupper() for c in pwd)
    assert len({generate_password() for _ in range(50)}) == 50
    assert entropy_bits(PasswordOptions(length=16)) > 90
    with pytest.raises(ValueError):
        generate_password(PasswordOptions(lower=False, upper=False, digits=False, symbols=False))
    assert check_complexity("ivanovPass1!", "ivanov")
    assert validate_against_policy("Aa1!", ctx.policy)            # too short for minPwdLength=10
    assert not validate_against_policy("Str0ng-Passw0rd!", ctx.policy)


def test_explorer_read_only_and_builder(ctx, db):
    ex = ExplorerService(ctx, db)
    assert not any(hasattr(ex, n) for n in ("modify", "add", "delete", "move", "set_password"))
    flt = build_filter("Пользователь", [Condition("cn", "contains", "a*b)"), Condition("mail", "absent")])
    assert flt.to_ldap() == r"(&(objectCategory=person)(objectClass=user)(cn=*a\2ab\29*)(!(mail=*)))"
    res = ex.run("", "subtree", flt.to_ldap(), ["cn"], limit=5)
    assert len(res.entries) <= 5
    with pytest.raises(E.ValidationError):
        ex.run("", "subtree", "(cn=", ["cn"])
    with pytest.raises(E.ValidationError):
        validate_attributes("cn, bad attr")
    assert db.query_history()[0]["filter"] == flt.to_ldap()
    assert set(ex.examples()) and ex.object_attributes(find_user(ctx, "svc_sql")).dn


def test_compare_users(ctx):
    res = CompareService(ctx).compare_users(find_user(ctx, "adm.petrov"), find_user(ctx, "adm.sidorov"), transitive=True)
    assert "DnsAdmins" in res.groups_only_left and "Domain Admins" in res.groups_both
    assert any(not a["same"] for a in res.attributes)


def test_offboarding_plan_and_execute(ctx):
    ob = OffboardingService(ctx)
    cands = ob.find_candidates("уволен")
    assert len(cands) == 2
    tpl = dict(DEFAULT_TEMPLATE, move_to_ou="OU=Disabled Users,OU=Company,DC=demo,DC=local", keep_groups=["UG-All-Staff"])
    rows = ob.plan(cands + ["adm.petrov"], tpl, ticket="INC-1")
    assert rows[-1].item.status == "skip"       # privileged account is excluded
    ob.execute(rows, tpl, "INC-1", dry_run=True)
    assert all(r.item.result.startswith("Dry Run") for r in rows[:2])
    ob.execute(rows, tpl, "INC-1", dry_run=False)
    from adtoolkit.services.user_service import UserService
    for r in rows[:2]:
        assert r.item.result == "Выполнено", r.item.error
        u = UserService(ctx).get(r.item.dn)
        assert not u.enabled and "INC-1" in u.description and u.account_expired and "Disabled Users" in u.dn
        assert not [g for g in u.member_of if "GG-" in g]


EVENTS_XML = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><Provider Name='Microsoft-Windows-Security-Auditing'/>
<EventID>4740</EventID><TimeCreated SystemTime='2026-10-08T10:15:30.1234567Z'/><Computer>dc01.corp.local</Computer></System>
<EventData><Data Name='TargetUserName'>ivanov</Data><Data Name='TargetDomainName'>WS-0042</Data><Data Name='SubjectUserName'>DC01$</Data>
<Data Name='SubjectDomainName'>CORP</Data></EventData></Event>
<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><EventID>4728</EventID><TimeCreated SystemTime='2026-10-08T09:00:00.0000000Z'/></System>
<EventData><Data Name='MemberName'>CN=x,DC=corp</Data><Data Name='TargetUserName'>Domain Admins</Data><Data Name='TargetDomainName'>CORP</Data></EventData></Event>"""


def test_events_parsing_and_xpath():
    events = parse_events_xml("dc01", EVENTS_XML)
    assert events[0].event_id == 4740 and events[0].source == "WS-0042" and events[0].target_user == "ivanov"
    assert events[1].severity == "medium" and "Domain Admins" in events[1].message
    assert lockout_summary(events)[0]["count"] == 1
    assert "EventID=4740" in build_xpath([4740], 24) and "86400000" in build_xpath([4740], 24)
    assert "TargetUserName']='ivanov'" in build_xpath([4740], 1, "CORP\\ivanov")
    for bad in ("x' or '1'='1", "a]b", "a\"b"):
        with pytest.raises(E.ValidationError):
            build_xpath([4740], 1, bad)
    with pytest.raises(E.ValidationError):
        build_xpath([], 1)


def test_events_query_with_fake_runner():
    def runner(dc, xpath, count, timeout):
        if dc == "dc02.corp.local":
            raise E.ExternalToolError("Access is denied", hint="Event Log Readers")
        return EVENTS_XML
    res = EventsService(runner).query(EventQuery(dcs=["dc01.corp.local", "dc02.corp.local"], event_ids=[4740, 4728],
                                                 min_severity="medium"), check_availability=False)
    assert len(res.events) == 2 and "dc02.corp.local" in res.errors
    res = EventsService(runner).query(EventQuery(dcs=["dc01.corp.local"], event_ids=[4740], min_severity="high"),
                                      check_availability=False)
    assert [e.event_id for e in res.events] == [4740]


def test_events_unavailable_is_reported_not_simulated(monkeypatch):
    import adtoolkit.services.events_service as ev
    monkeypatch.setattr(ev, "availability", lambda: (False, "только Windows"))
    with pytest.raises(E.UnsupportedFeatureError):
        EventsService().query(EventQuery(dcs=["dc01"], event_ids=[4740]))


def test_network_checks_real_and_validated():
    import socket
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert N.tcp_check("127.0.0.1", port, 2).ok is True
    finally:
        srv.close()
    assert N.tcp_check("127.0.0.1", port, 1).ok is False
    assert N.resolve("localhost", 3).ok is True
    for bad in ("host; rm -rf /", "-c 1 x", "a b", ""):
        with pytest.raises(E.ValidationError):
            N.validate_host(bad)


def test_settings_layering(db, tmp_path, monkeypatch):
    from adtoolkit.core.app_config import SettingsManager
    cfg = tmp_path / "settings.json"
    cfg.write_text('{"settings": {"stale_user_days": 120, "bulk_max_items": 99999}, '
                   '"profiles": [{"name": "Corp", "server": "dc01.corp.local", "password": "leak"}]}', encoding="utf-8")
    monkeypatch.setenv("ADTOOLKIT_CONFIG", str(cfg))
    sm = SettingsManager(db)
    assert sm.settings.stale_user_days == 120 and sm.settings.bulk_max_items == 10000
    assert "password" not in sm.org_profiles()[0]
    sm.settings.stale_user_days = 30
    sm.save()
    assert SettingsManager(db).settings.stale_user_days == 30


def test_example_config_is_valid():
    import json
    from adtoolkit.models.connection import ConnectionProfile
    data = json.loads((Path(__file__).resolve().parents[1] / "config" / "settings.example.json").read_text(encoding="utf-8"))
    for p in data["profiles"]:
        assert not any("password" in k.lower() for k in p)
        ConnectionProfile.from_dict(p)
