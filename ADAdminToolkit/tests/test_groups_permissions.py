import pytest

from adtoolkit.core import errors as E
from adtoolkit.ldap.dn import normalize_dn
from adtoolkit.ldap.gateway import ModOp
from adtoolkit.security.permissions import PrivilegedGroupRegistry
from adtoolkit.services.group_service import GroupQuery, GroupService

from .conftest import find_user

DA = "CN=Domain Admins,CN=Users,DC=demo,DC=local"
VPN = "CN=GG-VPN-Users,OU=Groups,OU=Company,DC=demo,DC=local"


def test_privileged_groups_detected_by_sid_even_if_renamed(ctx):
    # rename Domain Admins to a localized name: detection must still work (SID based)
    new_dn = ctx.gateway.move(DA, "CN=Users,DC=demo,DC=local", "CN=Администраторы домена")
    reg = PrivilegedGroupRegistry(ctx.gateway)
    g = reg.get(new_dn)
    assert g is not None and g.critical and g.well_known == "Domain Admins"


def test_nested_privilege(ctx):
    privileged, reason, critical = ctx.privileged.classify_group("CN=GG-IT-Admins,OU=Groups,OU=Company,DC=demo,DC=local")
    assert privileged and "Domain Admins" in reason and critical
    assert ctx.privileged.classify_group(VPN)[0] is False


def test_search_filters_and_marks(ctx):
    gs = GroupService(ctx)
    res = gs.search(GroupQuery(only_privileged=True))
    names = {g.name for g in res.items}
    assert {"Domain Admins", "Enterprise Admins", "Schema Admins", "Administrators", "GG-IT-Admins"} <= names
    dist = gs.search(GroupQuery(category="distribution")).items
    assert all(not g.is_security for g in dist) and dist
    builtin = gs.search(GroupQuery(scope="builtin")).items
    assert {g.name for g in builtin} >= {"Administrators", "Backup Operators"}


def test_transitive_members_and_cycles(ctx):
    gs = GroupService(ctx)
    rows = {r.name: r for r in gs.transitive_members(DA)}
    assert rows["Сидоров (админ) Павел"].via == "через GG-IT-Admins"
    assert rows["GG-IT-Admins"].via == "прямое"
    loop = gs.transitive_members("CN=GG-Loop-A,OU=Groups,OU=Company,DC=demo,DC=local")
    assert [r.name for r in loop] == ["GG-Loop-B"]
    tree = gs.nested_tree("CN=GG-Loop-A,OU=Groups,OU=Company,DC=demo,DC=local")
    assert tree["children"][0]["children"][0]["cycle"] is True


def test_empty_groups_consider_primary_group(ctx):
    names = {g.name for g in GroupService(ctx).empty_groups()}
    assert "GG-Project-Alpha" in names and "GG-Old-Temp" in names
    assert "Domain Users" not in names        # members via primaryGroupID
    assert "Domain Computers" not in names


def test_membership_checks(ctx):
    gs = GroupService(ctx)
    sid = find_user(ctx, "adm.sidorov")
    assert gs.is_member(sid, DA) == (True, "косвенное членство через вложенные группы")
    assert gs.is_member(sid, "CN=Domain Users,CN=Users,DC=demo,DC=local")[0]
    assert gs.is_member(sid, VPN, transitive=True)[0] is False


def test_add_remove_member_with_privileged_guard(ctx, db):
    gs = GroupService(ctx)
    user = find_user(ctx, "svc_sql")
    assert gs.add_member(VPN, user) is True
    assert gs.add_member(VPN, user) is False                 # already member -> skipped
    assert gs.remove_member(VPN, user) is True
    with pytest.raises(E.ProtectedObjectError):
        gs.add_member(DA, user)
    with pytest.raises(E.ProtectedObjectError):
        gs.add_member("CN=GG-IT-Admins,OU=Groups,OU=Company,DC=demo,DC=local", user)   # nested privileged
    assert gs.add_member(DA, user, privileged_confirmed=True)
    with pytest.raises(E.ConstraintViolationError):
        gs.remove_member("CN=Domain Users,CN=Users,DC=demo,DC=local", user)   # primary group
    results = [o["result"] for o in db.operations()]
    assert "failed" in results and "success" in results and "skipped" in results


def test_group_write_permission_denied(ctx):
    gs = GroupService(ctx)
    ctx.gateway.store.denied_write.add(normalize_dn(VPN))
    with pytest.raises(E.PermissionDeniedError):
        gs.add_member(VPN, find_user(ctx, "svc_sql"))


def test_create_group(ctx):
    gs = GroupService(ctx)
    dn = gs.create_group("OU=Groups,OU=Company,DC=demo,DC=local", "GG-New (тест)", scope="universal", security=True)
    g = gs.get(dn)
    assert g.scope == "Универсальная" and g.is_security
    with pytest.raises(E.ConflictError):
        gs.create_group("OU=Groups,OU=Company,DC=demo,DC=local", "GG-New (тест)")
    with pytest.raises(E.ValidationError):
        gs.create_group("OU=Groups,OU=Company,DC=demo,DC=local", "bad|name")


def test_compare_groups(ctx):
    gs = GroupService(ctx)
    res = gs.compare("CN=GG-IT,OU=Groups,OU=Company,DC=demo,DC=local", "CN=GG-Helpdesk,OU=Groups,OU=Company,DC=demo,DC=local")
    assert res.both and res.only_left and not res.only_right


def test_rights_summary(ctx):
    s = ctx.permissions.rights_summary(ctx.privileged)
    assert s.can_read_directory and "Domain Admins" in s.privileged_groups and s.create_user_in_default


def test_conflict_on_concurrent_member_change(ctx):
    # delete of a value that is no longer present -> conflict, never silent success
    with pytest.raises(E.ConflictError):
        ctx.gateway.modify(VPN, {"member": [(ModOp.DELETE, ["CN=Nobody,DC=demo,DC=local"])]})
