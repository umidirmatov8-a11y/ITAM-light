import pytest

from adtoolkit.core import errors as E
from adtoolkit.core.cancel import CancelToken
from adtoolkit.services.bulk_service import (STATUS_ERROR, STATUS_READY, STATUS_SKIP, BulkOperation, BulkService,
                                             guess_identity_column, parse_csv)
from adtoolkit.services.user_service import UserQuery, UserService, UserView

from .conftest import find_user


def test_parse_csv_variants(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("﻿sAMAccountName;Комментарий\nsvc_sql;x\n# comment\nsvc_web;y\n".encode("utf-8"))
    headers, rows = parse_csv(p)
    assert headers == ["sAMAccountName", "Комментарий"] and [r["sAMAccountName"] for r in rows] == ["svc_sql", "svc_web"]
    p2 = tmp_path / "b.csv"
    p2.write_bytes("Логин,Имя\nivanov,Иван\n".encode("cp1251"))
    headers, rows = parse_csv(p2)
    assert guess_identity_column(headers) == "Логин" and rows[0]["Имя"] == "Иван"
    headers, rows = parse_csv(b"svc_sql\nsvc_web\n")
    assert headers == ["identity"] and len(rows) == 2
    with pytest.raises(E.ValidationError):
        parse_csv(b"")


def test_resolve_identities(ctx):
    bs = BulkService(ctx)
    items = bs.resolve(["svc_sql", "svc_sql@demo.local", "nobody", "", "*"], "user")
    assert items[0].status == STATUS_READY
    assert items[1].status == STATUS_SKIP and "Дубликат" in items[1].reason
    assert items[2].status == STATUS_ERROR and items[3].status == STATUS_ERROR
    assert items[4].status == STATUS_ERROR     # '*' is escaped, matches nothing
    comp = bs.resolve(["WS-0001", "ws-0002.demo.local"], "computer")
    assert all(i.status == STATUS_READY for i in comp)
    wrong = bs.resolve(["WS-0001"], "user")
    assert wrong[0].status == STATUS_ERROR


def stale_users(ctx):
    return [u.sam for u in UserService(ctx).search(UserQuery(view=UserView.STALE)).items]


def test_plan_shows_changes_skips_and_privileged(ctx):
    bs = BulkService(ctx)
    ids = stale_users(ctx) + ["Guest", "adm.petrov", "adm.sidorov"]
    plan = bs.plan(BulkOperation.DISABLE, bs.resolve(ids, "user"))
    by = {i.sam: i for i in plan.items}
    assert by["Guest"].status == STATUS_SKIP                      # already disabled / builtin
    assert by["adm.petrov"].status == STATUS_SKIP and "Привилегированная" in by["adm.petrov"].reason
    assert by["adm.sidorov"].status == STATUS_SKIP                # nested privileged (via GG-IT-Admins)
    ready = plan.ready
    assert ready and all("ACCOUNTDISABLE" in i.planned for i in ready)


def test_dry_run_changes_nothing(ctx, db):
    bs = BulkService(ctx)
    sams = stale_users(ctx)
    plan = bs.plan(BulkOperation.DISABLE, bs.resolve(sams, "user"))
    bs.execute(plan, dry_run=True, rate_per_second=50)
    us = UserService(ctx)
    assert all(us.get(find_user(ctx, s)).enabled for s in sams)
    ops = db.operations()
    assert sum(1 for o in ops if o["operation"] == "bulk.disable" and o["result"] == "dry-run") == len(plan.ready)
    assert all(i.result.startswith("Dry Run") for i in plan.ready)


def test_read_only_blocks_real_execution(ro_ctx):
    bs = BulkService(ro_ctx)
    plan = bs.plan(BulkOperation.DISABLE, bs.resolve(stale_users(ro_ctx), "user"))
    with pytest.raises(E.ReadOnlyModeError):
        bs.execute(plan, dry_run=False)
    bs.execute(plan, dry_run=True)      # simulation is allowed in read-only mode


def test_execution_isolates_per_object_errors(ctx):
    bs = BulkService(ctx)
    sams = stale_users(ctx)[:4]
    plan = bs.plan(BulkOperation.DISABLE, bs.resolve(sams, "user"))
    # the second object will fail on the DC side (injected insufficientAccessRights on modify)
    from adtoolkit.ldap import error_mapping as EM
    calls = {"n": 0}
    real_modify = ctx.gateway.modify

    def flaky(dn, changes):
        calls["n"] += 1
        if calls["n"] == 2:
            from adtoolkit.ldap.error_mapping import map_result
            raise map_result({"result": EM.INSUFFICIENT_ACCESS_RIGHTS, "message": "00000005: SecErr"}, "modify", dn)
        return real_modify(dn, changes)
    ctx.gateway.modify = flaky
    bs.execute(plan, dry_run=False, rate_per_second=50)
    results = [i.result for i in plan.ready]
    assert results.count("Ошибка") == 1 and results.count("Выполнено") == len(results) - 1
    assert "Недостаточно прав" in [i for i in plan.ready if i.result == "Ошибка"][0].error


def test_privileged_target_group_blocked_until_confirmed(ctx):
    bs = BulkService(ctx)
    params = {"group_dn": "CN=Domain Admins,CN=Users,DC=demo,DC=local"}
    plan = bs.plan(BulkOperation.ADD_TO_GROUP, bs.resolve(["svc_sql"], "user"), params)
    assert plan.blocked_reason and plan.target_privileged
    with pytest.raises(E.ValidationError):
        bs.execute(plan, dry_run=False)
    plan2 = bs.plan(BulkOperation.ADD_TO_GROUP, bs.resolve(["svc_sql"], "user"), params, privileged_target_confirmed=True)
    assert not plan2.blocked_reason
    bs.execute(plan2, dry_run=False, rate_per_second=50)
    assert plan2.ready[0].result == "Выполнено"


def test_limit_and_move_and_unlock(ctx, settings):
    bs = BulkService(ctx)
    settings.bulk_max_items = 2
    plan = bs.plan(BulkOperation.DISABLE, bs.resolve(stale_users(ctx), "user"))
    assert plan.blocked_reason and not plan.ready
    settings.bulk_max_items = 500
    locked = [u.sam for u in UserService(ctx).search(UserQuery(view=UserView.LOCKED)).items]
    plan = bs.plan(BulkOperation.UNLOCK, bs.resolve(locked + ["svc_sql"], "user"))
    assert len(plan.ready) == 3 and plan.items[-1].status == STATUS_SKIP
    bs.execute(plan, dry_run=False, rate_per_second=50)
    assert not UserService(ctx).search(UserQuery(view=UserView.LOCKED)).items
    target = "OU=Disabled Users,OU=Company,DC=demo,DC=local"
    plan = bs.plan(BulkOperation.MOVE_TO_OU, bs.resolve(["svc_sql", "svc_web"], "user"), {"target_ou": target})
    bs.execute(plan, dry_run=False, rate_per_second=50)
    assert all(i.result == "Выполнено" for i in plan.ready)
    assert find_user(ctx, "svc_sql").endswith(target)


def test_cancel_stops_batch(ctx):
    bs = BulkService(ctx)
    plan = bs.plan(BulkOperation.DISABLE, bs.resolve(stale_users(ctx), "user"))
    token = CancelToken()
    token.cancel()
    bs.execute(plan, dry_run=False, cancel=token)
    assert all(i.result == "Отменено" for i in plan.ready)


def test_prepare_password_reset_never_modifies(ctx):
    bs = BulkService(ctx)
    plan = bs.plan(BulkOperation.PREPARE_PASSWORD_RESET, bs.resolve(["svc_sql"], "user"))
    bs.execute(plan, dry_run=False)
    assert plan.dry_run and plan.ready[0].result.startswith("Dry Run")
    rep = bs.report(plan)
    assert rep.rows[0]["result"].startswith("Dry Run") and rep.criteria["Режим"].startswith("Dry Run")
