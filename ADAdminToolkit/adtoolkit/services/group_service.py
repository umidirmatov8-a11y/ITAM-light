"""Groups: search, membership (direct / nested / primary group), privileged-group protection, creation, comparison."""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import ConflictError, ConstraintViolationError, ProtectedObjectError, ValidationError
from ..ldap.adtypes import (GROUP_TYPE_DOMAIN_LOCAL, GROUP_TYPE_GLOBAL, GROUP_TYPE_SYSTEM, GROUP_TYPE_UNIVERSAL,
                            make_group_type, sid_rid, sid_to_str, UAC)
from ..ldap.dn import child_dn, first_rdn, normalize_dn, rdn_value
from ..ldap.filters import And, Equals, Not, Or, Present, Substring, bit_and, in_chain
from ..ldap.gateway import ModOp, Scope
from ..models.records import GroupRecord
from ..security.audit_log import RESULT_SKIPPED
from . import ad_queries as Q
from .common import (MemberRow, QueryResult, ensure_conflict_free, get_or_fail, object_type_of, require_dn,
                     resolve_dns, search_records)
from .context import ServiceContext

MEMBER_ATTRS = ["cn", "sAMAccountName", "objectClass", "userAccountControl", "displayName"]
GROUP_NAME_INVALID = re.compile(r'["/\\\[\]:;|=,+*?<>]')


@dataclass
class GroupQuery:
    text: str = ""
    scope: str = ""            # "" | global | domainlocal | universal | builtin
    category: str = ""         # "" | security | distribution
    ou_dn: str = ""
    only_privileged: bool = False
    limit: int = 5000


@dataclass
class ComparisonResult:
    left: str
    right: str
    only_left: list[MemberRow] = field(default_factory=list)
    only_right: list[MemberRow] = field(default_factory=list)
    both: list[MemberRow] = field(default_factory=list)
    transitive: bool = False


class GroupService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.gw = ctx.gateway

    # ---------------------------------------------------------------------------------------------------------
    def search(self, q: GroupQuery, cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> QueryResult:
        base = q.ou_dn.strip() or self.ctx.base_dn
        require_dn(base, "контейнер поиска")
        parts = [Q.IS_GROUP]
        if q.text.strip():
            t = q.text.strip()
            parts.append(Or(Substring("cn", any=(t,)), Substring("sAMAccountName", any=(t,)),
                            Substring("description", any=(t,))))
        scope_masks = {"global": GROUP_TYPE_GLOBAL, "domainlocal": GROUP_TYPE_DOMAIN_LOCAL,
                       "universal": GROUP_TYPE_UNIVERSAL}
        if q.scope == "builtin":
            parts.append(bit_and("groupType", GROUP_TYPE_SYSTEM))
        elif q.scope in scope_masks:
            parts.append(bit_and("groupType", scope_masks[q.scope]))
            if q.scope == "domainlocal":
                parts.append(Not(bit_and("groupType", GROUP_TYPE_SYSTEM)))
        if q.category == "security":
            parts.append(Q.SECURITY_GROUP)
        elif q.category == "distribution":
            parts.append(Not(Q.SECURITY_GROUP))
        flt = And(*parts)
        progress(None, "Поиск групп…")
        items, stats = search_records(self.gw, base, flt, Q.GROUP_ATTRIBUTES, GroupRecord.from_entry, limit=q.limit,
                                      cancel=cancel)
        self._mark_privileged(items)
        if q.only_privileged:
            items = [g for g in items if g.privileged]
        notes = []
        if stats.truncated:
            notes.append(f"Показаны первые {len(items)} групп — уточните поиск.")
        notes.append("Количество участников — прямые члены (атрибут member); участники через основную группу "
                     "(primaryGroupID) учитываются при просмотре состава.")
        return QueryResult(items=items, truncated=stats.truncated, notes=notes, filter_text=flt.to_ldap(), base_dn=base,
                           criteria={"Текст": q.text, "Область": q.scope or "любая", "Тип": q.category or "любой", "OU": base})

    def _mark_privileged(self, groups: list[GroupRecord]) -> None:
        priv = self.ctx.privileged.load()
        priv_dns = set(priv)
        for g in groups:
            info = priv.get(normalize_dn(g.dn))
            if info:
                g.privileged, g.privileged_reason = True, f"Привилегированная ({info.well_known})"
        # nested privilege: groups that are members of privileged groups (one transitive query per privileged group)
        index = {normalize_dn(g.dn): g for g in groups}
        for pdn, pg in priv.items():
            for e in self.gw.search(self.ctx.base_dn, And(Q.IS_GROUP, in_chain("memberOf", pg.dn)), ["1.1"]):
                nd = normalize_dn(e.dn)
                if nd in index and nd not in priv_dns:
                    g = index[nd]
                    g.privileged = True
                    g.privileged_reason = (g.privileged_reason + "; " if g.privileged_reason else "") + f"вложена в {pg.name}"

    def get(self, dn: str) -> GroupRecord:
        g = GroupRecord.from_entry(get_or_fail(self.gw, dn, Q.GROUP_ATTRIBUTES))
        privileged, reason, _ = self.ctx.privileged.classify_group(dn)
        g.privileged, g.privileged_reason = privileged, reason
        return g

    def find_by_name(self, name: str) -> list[GroupRecord]:
        name = name.strip()
        if not name:
            return []
        if "=" in name and "," in name:
            e = self.gw.get(name, Q.GROUP_ATTRIBUTES)
            return [GroupRecord.from_entry(e)] if e is not None and "group" in e.object_classes else []
        flt = And(Q.IS_GROUP, Or(Equals("sAMAccountName", name), Equals("cn", name)))
        return [GroupRecord.from_entry(e) for e in self.gw.search(self.ctx.base_dn, flt, Q.GROUP_ATTRIBUTES, size_limit=5)]

    # ---------------------------------------------------------------------------------------------------------
    # Membership
    # ---------------------------------------------------------------------------------------------------------
    def _row(self, e, via: str = "прямое", depth: int = 0) -> MemberRow:
        t = object_type_of(e)
        enabled = None
        if t in ("user", "computer"):
            enabled = not bool((e.int("userAccountControl", 0) or 0) & UAC.ACCOUNTDISABLE)
        return MemberRow(dn=e.dn, name=e.str("displayName") or e.str("cn") or rdn_value(e.dn), object_type=t,
                         sam=e.str("sAMAccountName"), via=via, enabled=enabled, depth=depth)

    def primary_group_members(self, group_dn: str, cancel: CancelToken | None = None) -> list[MemberRow]:
        g = get_or_fail(self.gw, group_dn, ["objectSid"])
        rid = sid_rid(g.first("objectSid")) if g.first("objectSid") else None
        if rid is None:
            return []
        return [self._row(e, "основная группа (primaryGroupID)")
                for e in self.gw.search(self.ctx.base_dn, Equals("primaryGroupID", rid), MEMBER_ATTRS, cancel=cancel)]

    def direct_members(self, group_dn: str, cancel: CancelToken | None = None, include_primary: bool = True) -> list[MemberRow]:
        g = get_or_fail(self.gw, group_dn, ["member"])
        members = [str(m) for m in g.values("member")]
        resolved = resolve_dns(self.gw, members, MEMBER_ATTRS, cancel=cancel)
        rows = []
        for m in members:
            e = resolved.get(normalize_dn(m))
            rows.append(self._row(e) if e is not None else MemberRow(dn=m, name=rdn_value(m), object_type="other", via="прямое"))
        if include_primary:
            rows += self.primary_group_members(group_dn, cancel)
        return sorted(rows, key=lambda r: (r.object_type != "group", r.name.casefold()))

    def transitive_members(self, group_dn: str, cancel: CancelToken | None = None,
                           progress: Progress = NULL_PROGRESS) -> list[MemberRow]:
        """All members including those of nested groups, with the nesting path (BFS, cycle-safe)."""
        out: dict[str, MemberRow] = {}
        queue: deque[tuple[str, list[str]]] = deque([(group_dn, [])])
        visited_groups = {normalize_dn(group_dn)}
        while queue:
            if cancel:
                cancel.raise_if_cancelled()
            gdn, path = queue.popleft()          # path: nested groups from the root down to gdn (root excluded)
            progress(None, f"Разбор группы {rdn_value(gdn)}…")
            for row in self.direct_members(gdn, cancel, include_primary=True):
                nd = normalize_dn(row.dn)
                if nd in out or nd == normalize_dn(group_dn):
                    continue
                row.depth = len(path)
                if path:
                    chain = " → ".join(rdn_value(p) for p in path)
                    row.via = f"через {chain}" + (" (основная группа)" if row.via.startswith("основная") else "")
                out[nd] = row
                if row.object_type == "group" and nd not in visited_groups:
                    visited_groups.add(nd)
                    queue.append((row.dn, path + [row.dn]))
        return sorted(out.values(), key=lambda r: (r.depth, r.object_type != "group", r.name.casefold()))

    def nested_tree(self, group_dn: str, cancel: CancelToken | None = None, max_depth: int = 25) -> dict:
        """Tree of nested groups: {dn, name, children, cycle}."""
        def build(dn: str, stack: list[str], depth: int) -> dict:
            if cancel:
                cancel.raise_if_cancelled()
            node = {"dn": dn, "name": rdn_value(dn), "children": [], "cycle": False}
            if normalize_dn(dn) in stack:
                node["cycle"] = True
                return node
            if depth >= max_depth:
                return node
            e = self.gw.get(dn, ["member"])
            if e is None:
                return node
            members = resolve_dns(self.gw, [str(m) for m in e.values("member")], ["objectClass", "cn"], cancel=cancel)
            for m in members.values():
                if object_type_of(m) == "group":
                    node["children"].append(build(m.dn, stack + [normalize_dn(dn)], depth + 1))
            node["children"].sort(key=lambda c: c["name"].casefold())
            return node
        return build(group_dn, [], 0)

    def parent_groups(self, dn: str) -> list[GroupRecord]:
        e = get_or_fail(self.gw, dn, ["memberOf"])
        resolved = resolve_dns(self.gw, [str(v) for v in e.values("memberOf")], Q.GROUP_ATTRIBUTES)
        return sorted((GroupRecord.from_entry(x) for x in resolved.values()), key=lambda g: g.name.casefold())

    def transitive_groups_of(self, member_dn: str, cancel: CancelToken | None = None) -> list[GroupRecord]:
        """Groups the object belongs to, directly or via nesting (LDAP_MATCHING_RULE_IN_CHAIN)."""
        items, _ = search_records(self.gw, self.ctx.base_dn, Q.groups_of_member_transitive(member_dn), Q.GROUP_ATTRIBUTES,
                                  GroupRecord.from_entry, cancel=cancel)
        return sorted(items, key=lambda g: g.name.casefold())

    def is_member(self, member_dn: str, group_dn: str, transitive: bool = True) -> tuple[bool, str]:
        g = get_or_fail(self.gw, group_dn, ["member", "objectSid"])
        if any(normalize_dn(m) == normalize_dn(member_dn) for m in g.values("member")):
            return True, "прямое членство"
        m = get_or_fail(self.gw, member_dn, ["primaryGroupID"])
        rid = sid_rid(g.first("objectSid")) if g.first("objectSid") else None
        if rid is not None and m.int("primaryGroupID") == rid:
            return True, "основная группа (primaryGroupID)"
        if transitive:
            hits = self.gw.search_list(group_dn, in_chain("member", member_dn), ["1.1"], scope=Scope.BASE)
            if hits:
                return True, "косвенное членство через вложенные группы"
        return False, "не является членом"

    # ---------------------------------------------------------------------------------------------------------
    # Analysis
    # ---------------------------------------------------------------------------------------------------------
    def empty_groups(self, cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> list[GroupRecord]:
        """Groups without members, taking primary-group membership (primaryGroupID) into account."""
        progress(None, "Поиск групп без атрибута member…")
        candidates, _ = search_records(self.gw, self.ctx.base_dn, And(Q.IS_GROUP, Not(Present("member"))),
                                       Q.GROUP_ATTRIBUTES, GroupRecord.from_entry, cancel=cancel)
        out = []
        for i, g in enumerate(candidates):
            if cancel:
                cancel.raise_if_cancelled()
            progress(int(i * 100 / max(1, len(candidates))), f"Проверка основной группы: {g.name}")
            rid = g.rid
            if rid is not None and self.gw.search_list(self.ctx.base_dn, Equals("primaryGroupID", rid), ["1.1"], size_limit=1):
                continue
            out.append(g)
        self._mark_privileged(out)
        return out

    def users_missing_standard_groups(self, group_names: list[str], cancel: CancelToken | None = None) -> list[dict]:
        """Enabled users that are not (even transitively) in each organisation-defined standard group."""
        if not group_names:
            raise ValidationError("Правила стандартных групп не заданы (Настройки → Стандартные группы)")
        groups = []
        for name in group_names:
            found = self.find_by_name(name)
            if not found:
                raise ValidationError(f"Стандартная группа не найдена: {name}")
            groups.append(found[0])
        users = {normalize_dn(e.dn): e for e in self.gw.search(self.ctx.base_dn, And(Q.IS_USER, Q.ENABLED),
                                                                  ["displayName", "sAMAccountName", "department"], cancel=cancel)}
        missing: dict[str, list[str]] = {}
        for g in groups:
            members = {normalize_dn(e.dn) for e in self.gw.search(self.ctx.base_dn, And(Q.IS_USER, in_chain("memberOf", g.dn)),
                                                                   ["1.1"], cancel=cancel)}
            rid = g.rid
            if rid is not None:
                members |= {normalize_dn(e.dn) for e in self.gw.search(self.ctx.base_dn, Equals("primaryGroupID", rid), ["1.1"])}
            for nd in users:
                if nd not in members:
                    missing.setdefault(nd, []).append(g.name)
        return [{"dn": users[nd].dn, "name": users[nd].str("displayName") or rdn_value(users[nd].dn),
                 "sam": users[nd].str("sAMAccountName"), "department": users[nd].str("department"),
                 "missing": ", ".join(gs)} for nd, gs in sorted(missing.items())]

    def compare(self, left_dn: str, right_dn: str, transitive: bool = False, cancel: CancelToken | None = None) -> ComparisonResult:
        get = self.transitive_members if transitive else self.direct_members
        left = {normalize_dn(r.dn): r for r in get(left_dn, cancel)}
        right = {normalize_dn(r.dn): r for r in get(right_dn, cancel)}
        res = ComparisonResult(left_dn, right_dn, transitive=transitive)
        res.only_left = [left[k] for k in left if k not in right]
        res.only_right = [right[k] for k in right if k not in left]
        res.both = [left[k] for k in left if k in right]
        return res

    # ---------------------------------------------------------------------------------------------------------
    # Changes
    # ---------------------------------------------------------------------------------------------------------
    def _privileged_guard(self, group_dn: str, confirmed: bool, action: str) -> str:
        privileged, reason, _ = self.ctx.privileged.classify_group(group_dn)
        if privileged and not confirmed:
            raise ProtectedObjectError(f"«{action}»: группа {rdn_value(group_dn)} привилегированная — нужно отдельное подтверждение",
                                       details=reason)
        return reason

    def add_member(self, group_dn: str, member_dn: str, *, privileged_confirmed: bool = False) -> bool:
        group_dn, member_dn = require_dn(group_dn), require_dn(member_dn)
        self.gw._guard_write()
        g = get_or_fail(self.gw, group_dn, ["member", "groupType"])
        if any(normalize_dn(m) == normalize_dn(member_dn) for m in g.values("member")):
            self.ctx.journal.record("group.add_member", group_dn, RESULT_SKIPPED,
                                    details={"member": member_dn, "reason": "уже является членом"})
            return False
        if normalize_dn(group_dn) == normalize_dn(member_dn):
            raise ValidationError("Группа не может быть членом самой себя")
        with self.ctx.journal.track("group.add_member", group_dn, details={"member": member_dn}):
            reason = self._privileged_guard(group_dn, privileged_confirmed, "Добавление участника")
            get_or_fail(self.gw, member_dn, ["objectClass"])
            self.ctx.permissions.require_write(group_dn, ["member"], "Изменение состава группы")
            self.gw.modify(group_dn, {"member": [(ModOp.ADD, [member_dn])]})
            if reason:
                self.ctx.privileged.invalidate()
        return True

    def remove_member(self, group_dn: str, member_dn: str, *, privileged_confirmed: bool = False) -> bool:
        group_dn, member_dn = require_dn(group_dn), require_dn(member_dn)
        self.gw._guard_write()
        g = get_or_fail(self.gw, group_dn, ["member", "objectSid"])
        if not any(normalize_dn(m) == normalize_dn(member_dn) for m in g.values("member")):
            m = self.gw.get(member_dn, ["primaryGroupID"])
            rid = sid_rid(g.first("objectSid")) if g.first("objectSid") else None
            if m is not None and rid is not None and m.int("primaryGroupID") == rid:
                raise ConstraintViolationError("Нельзя удалить объект из его основной группы (primaryGroupID). "
                                               "Сначала назначьте другую основную группу.")
            self.ctx.journal.record("group.remove_member", group_dn, RESULT_SKIPPED,
                                    details={"member": member_dn, "reason": "не является прямым членом"})
            return False
        with self.ctx.journal.track("group.remove_member", group_dn, details={"member": member_dn}):
            self._privileged_guard(group_dn, privileged_confirmed, "Удаление участника")
            self.ctx.permissions.require_write(group_dn, ["member"], "Изменение состава группы")
            self.gw.modify(group_dn, {"member": [(ModOp.DELETE, [member_dn])]})
        return True

    def create_group(self, ou_dn: str, name: str, *, sam: str = "", scope: str = "global", security: bool = True,
                     description: str = "") -> str:
        name = (name or "").strip()
        sam = (sam or name).strip()
        if not name:
            raise ValidationError("Не задано имя группы")
        if GROUP_NAME_INVALID.search(sam) or len(sam) > 256:
            raise ValidationError("Имя группы (sAMAccountName) содержит недопустимые символы")
        ou_dn = require_dn(ou_dn, "OU")
        dn = child_dn(ou_dn, "CN", name)
        with self.ctx.journal.track("group.create", dn, details={"scope": scope, "security": security}):
            self.gw._guard_write()
            if self.gw.search_list(self.ctx.base_dn, And(Q.IS_GROUP, Equals("sAMAccountName", sam)), ["1.1"], size_limit=1):
                raise ConflictError(f"Группа с именем {sam} уже существует")
            ensure_conflict_free(self.gw, ou_dn, first_rdn(dn))
            self.ctx.permissions.require_create(ou_dn, "group", "Создание группы")
            self.gw.add(dn, ["top", "group"], {"sAMAccountName": sam, "groupType": make_group_type(scope, security),
                                               "description": description.strip() or None})
        return dn

    def privileged_composition(self, cancel: CancelToken | None = None) -> list[dict]:
        rows = []
        for pg in sorted(self.ctx.privileged.load().values(), key=lambda g: (not g.critical, g.name)):
            for r in self.transitive_members(pg.dn, cancel):
                rows.append({"group": pg.name, "critical": pg.critical, "member": r.name, "sam": r.sam,
                             "type": r.object_type, "via": r.via, "enabled": r.enabled, "dn": r.dn})
        return rows

    def group_sid(self, dn: str) -> str:
        e = get_or_fail(self.gw, dn, ["objectSid"])
        return sid_to_str(e.first("objectSid")) if e.first("objectSid") else ""
