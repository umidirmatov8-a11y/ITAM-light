from datetime import date

import pytest

from adtoolkit.core import errors as E
from adtoolkit.ldap.gateway import ModOp
from adtoolkit.services.user_service import NewUserSpec, UserQuery, UserService, UserView, expiry_to_filetime, make_sam

from .conftest import find_user


def test_disabled_and_locked_views(ctx):
    us = UserService(ctx)
    disabled = us.search(UserQuery(view=UserView.DISABLED)).items
    assert disabled and all(not u.enabled for u in disabled)
    locked = us.search(UserQuery(view=UserView.LOCKED)).items
    assert len(locked) == 3 and all(u.locked and u.locked_exact for u in locked)
    # one demo user has an old lockoutTime that already expired by lockoutDuration: candidate but not locked
    candidates = ctx.gateway.count(ctx.base_dn, "(&(objectCategory=person)(objectClass=user)(lockoutTime>=1))")
    assert candidates == 4


def test_views_return_consistent_results(ctx):
    us = UserService(ctx)
    for v in UserView:
        res = us.search(UserQuery(view=v))
        assert res.filter_text.startswith("(&(objectCategory=person)")
    assert all(u.pwd_never_expires for u in us.search(UserQuery(view=UserView.PNE)).items)
    stale = us.search(UserQuery(view=UserView.STALE, stale_days=90)).items
    assert stale and all(u.enabled for u in stale)
    assert any("lastLogonTimestamp" in n for n in us.search(UserQuery(view=UserView.STALE)).notes)
    ccp = us.search(UserQuery(view=UserView.CANNOT_CHANGE)).items
    assert {u.sam for u in ccp} == {"svc_sql", "svc_web"}


def test_text_search_with_special_characters_is_safe(ctx):
    us = UserService(ctx)
    assert us.search(UserQuery(text="*)(objectClass=*")).items == []
    assert us.search(UserQuery(text="Иван")).items


def test_enable_disable_with_journal(ctx, db):
    us = UserService(ctx)
    dn = find_user(ctx, "Guest")
    assert us.set_enabled(dn, False) is False          # already disabled -> skipped
    stale = us.search(UserQuery(view=UserView.STALE)).items[0]
    assert us.set_enabled(stale.dn, False) is True
    assert not us.get(stale.dn).enabled
    ops = db.operations()
    assert ops[0]["operation"] == "user.disable" and ops[0]["result"] == "success"
    assert any(o["result"] == "skipped" for o in ops)


def test_privileged_account_requires_confirmation(ctx):
    us = UserService(ctx)
    dn = find_user(ctx, "adm.petrov")
    with pytest.raises(E.ProtectedObjectError):
        us.set_enabled(dn, False)
    assert us.set_enabled(dn, False, privileged_confirmed=True)


def test_krbtgt_protected(ctx):
    with pytest.raises(E.ProtectedObjectError):
        UserService(ctx).set_enabled(find_user(ctx, "krbtgt"), True)


def test_unlock(ctx):
    us = UserService(ctx)
    u = us.search(UserQuery(view=UserView.LOCKED)).items[0]
    assert us.unlock(u.dn)
    assert not us.get(u.dn).locked


def test_reset_password_policy_and_encryption(ctx, db):
    us = UserService(ctx)
    dn = find_user(ctx, "svc_sql")
    with pytest.raises(E.PasswordPolicyError):
        us.reset_password(dn, "short")
    us.reset_password(dn, "Corr3ct-Horse-Battery!", must_change=True)
    assert us.get(dn).must_change_password
    assert all("Corr3ct-Horse-Battery!" not in str(o) for o in db.operations())
    ctx.gateway.info.encrypted = False
    with pytest.raises(E.InsecureConnectionError):
        us.reset_password(dn, "Corr3ct-Horse-Battery!")


def test_read_only_mode(ro_ctx):
    us = UserService(ro_ctx)
    dn = us.search(UserQuery(view=UserView.ENABLED)).items[0].dn
    with pytest.raises(E.ReadOnlyModeError):
        us.set_enabled(dn, False)


def test_permission_precheck(ctx):
    us = UserService(ctx)
    u = us.search(UserQuery(view=UserView.STALE)).items[0]
    from adtoolkit.ldap.dn import normalize_dn
    ctx.gateway.store.denied_write.add(normalize_dn(u.dn))
    with pytest.raises(E.PermissionDeniedError) as e:
        us.set_enabled(u.dn, False)
    assert "allowedAttributesEffective" in (e.value.details or "")


def test_optimistic_concurrency_conflict(ctx):
    us = UserService(ctx)
    u = us.search(UserQuery(view=UserView.ENABLED, text="Иван")).items[0]
    # someone else changes the title after we read it
    ctx.gateway.modify(u.dn, {"title": [(ModOp.REPLACE, ["Changed elsewhere"])]})
    with pytest.raises(E.ConflictError):
        us.update_attributes(u.dn, {"title": "New title"}, {"title": u.title})


def test_update_attributes_validation(ctx):
    us = UserService(ctx)
    u = us.search(UserQuery(view=UserView.ENABLED)).items[0]
    with pytest.raises(E.ValidationError):
        us.update_attributes(u.dn, {"userAccountControl": "0"}, {})
    with pytest.raises(E.ValidationError):
        us.update_attributes(u.dn, {"mail": "not-an-email"}, {"mail": u.mail})
    changed = us.update_attributes(u.dn, {"title": "Тест-инженер"}, {"title": u.title})
    assert changed == ["title"] and us.get(u.dn).title == "Тест-инженер"


def test_account_expiry(ctx):
    us = UserService(ctx)
    u = us.search(UserQuery(view=UserView.ENABLED)).items[0]
    us.set_account_expiry(u.dn, date(2030, 1, 31))
    assert us.get(u.dn).account_expires is not None
    us.set_account_expiry(u.dn, None)
    assert us.get(u.dn).account_expires is None
    assert expiry_to_filetime(None) == 0


def test_move_validation(ctx):
    us = UserService(ctx)
    u = us.search(UserQuery(view=UserView.ENABLED, text="Иван")).items[0]
    with pytest.raises(E.ValidationError):
        us.move(u.dn, "OU=Nope,DC=demo,DC=local")
    target = "OU=Disabled Users,OU=Company,DC=demo,DC=local"
    new_dn = us.move(u.dn, target)
    assert new_dn.endswith(target)
    with pytest.raises(E.ValidationError):
        us.move(new_dn, target)


def test_create_user_and_conflicts(ctx):
    us = UserService(ctx)
    spec = NewUserSpec(ou_dn="OU=IT,OU=Users,OU=Company,DC=demo,DC=local", given_name="Тест", surname="Новиков",
                       sam=make_sam("{g_lat}.{sn_lat}", "Тест", "Новиков"), upn="t.novikov.new@demo.local",
                       password="Str0ng-Passw0rd!x", groups=["CN=GG-VPN-Users,OU=Groups,OU=Company,DC=demo,DC=local"],
                       attributes={"department": "ИТ-отдел"})
    assert spec.sam == "t.novikov"
    res = us.create_user(spec)
    rec = us.get(res.dn)
    assert rec.enabled and rec.must_change_password and res.enabled and not res.warnings
    assert any("GG-VPN-Users" in g for g in rec.member_of)
    with pytest.raises(E.ConflictError):
        us.create_user(spec)
    bad = NewUserSpec(ou_dn=spec.ou_dn, given_name="A", surname="B", sam="bad/name", password="x")
    with pytest.raises(E.ValidationError):
        us.create_user(bad)


def test_create_user_privileged_group_needs_confirmation(ctx):
    us = UserService(ctx)
    spec = NewUserSpec(ou_dn="OU=IT,OU=Users,OU=Company,DC=demo,DC=local", given_name="Анна", surname="Админова",
                       sam="a.adminova", password="Str0ng-Passw0rd!x", groups=["CN=Domain Admins,CN=Users,DC=demo,DC=local"])
    with pytest.raises(E.ProtectedObjectError):
        us.create_user(spec)


def test_copy_from_user_excludes_privileged_groups(ctx):
    us = UserService(ctx)
    spec, notes = us.spec_copy_from(find_user(ctx, "adm.petrov"), "Новый", "Сотрудник")
    assert not any("Domain Admins" in g for g in spec.groups)
    assert any("привилегированная" in n for n in notes)


def test_group_paths_and_precise_logon(ctx):
    us = UserService(ctx)
    dn = find_user(ctx, "adm.sidorov")
    paths = {p["name"]: p for p in us.group_paths(dn)}
    assert paths["Domain Admins"]["path"] == ["GG-IT-Admins"]
    assert paths["Domain Users"].get("primary")
    rows = us.precise_last_logon(dn)
    assert len(rows) == 2 and all(r["last_logon"] for r in rows)
