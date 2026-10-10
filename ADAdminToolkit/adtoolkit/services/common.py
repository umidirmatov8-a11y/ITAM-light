"""Shared helpers for services: query results, membership resolution and optimistic-concurrency modifications."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from ..core.cancel import CancelToken
from ..core.errors import ConflictError, ObjectNotFoundError, ValidationError
from ..ldap.adtypes import utcnow
from ..ldap.dn import DNSyntaxError, normalize_dn, rdn_value, validate_dn
from ..ldap.filters import Equals, Or
from ..ldap.gateway import Changes, DirectoryGateway, Entry, ModOp, Scope, SearchStats


@dataclass
class QueryResult:
    items: list
    truncated: bool = False
    notes: list[str] = field(default_factory=list)
    criteria: dict[str, Any] = field(default_factory=dict)
    filter_text: str = ""
    base_dn: str = ""
    generated_at: datetime = field(default_factory=utcnow)
    errors: list[str] = field(default_factory=list)


@dataclass
class MemberRow:
    dn: str
    name: str
    object_type: str          # user | computer | group | contact | foreignSecurityPrincipal | other
    sam: str = ""
    via: str = ""             # "прямое" or nesting path
    enabled: bool | None = None
    depth: int = 0


def object_type_of(entry: Entry) -> str:
    classes = entry.object_classes
    if "computer" in classes:
        return "computer"
    if "group" in classes:
        return "group"
    if "user" in classes:
        return "user"
    if "contact" in classes:
        return "contact"
    if "foreignsecurityprincipal" in classes:
        return "foreignSecurityPrincipal"
    if "organizationalunit" in classes:
        return "organizationalUnit"
    if "container" in classes:
        return "container"
    return "other"


TYPE_LABELS = {"user": "Пользователь", "computer": "Компьютер", "group": "Группа", "contact": "Контакт",
               "foreignSecurityPrincipal": "Внешний субъект", "organizationalUnit": "OU", "container": "Контейнер",
               "other": "Другое"}


def resolve_dns(gw: DirectoryGateway, dns: Iterable[str], attributes: list[str], *, chunk: int = 40,
                cancel: CancelToken | None = None) -> dict[str, Entry]:
    """Fetch many objects by DN with few queries (OR of distinguishedName equality)."""
    dns = list(dict.fromkeys(dns))
    out: dict[str, Entry] = {}
    base = gw.info.base_dn
    for i in range(0, len(dns), chunk):
        if cancel:
            cancel.raise_if_cancelled()
        part = dns[i:i + chunk]
        flt = Or(*[Equals("distinguishedName", d) for d in part])
        for e in gw.search(base, flt, attributes, cancel=cancel):
            out[normalize_dn(e.dn)] = e
    # objects outside the base (e.g. CN=Builtin is inside; ForeignSecurityPrincipals too) — fall back to base reads
    for d in dns:
        nd = normalize_dn(d)
        if nd not in out:
            try:
                e = gw.get(d, attributes)
            except Exception:
                e = None
            if e is not None:
                out[nd] = e
    return out


def require_dn(dn: str, what: str = "DN") -> str:
    try:
        return validate_dn(dn)
    except (DNSyntaxError, AttributeError) as exc:
        raise ValidationError(f"Некорректный {what}: {dn}", details=str(exc)) from None


def get_or_fail(gw: DirectoryGateway, dn: str, attributes: list[str]) -> Entry:
    e = gw.get(require_dn(dn), attributes)
    if e is None:
        raise ObjectNotFoundError(f"Объект не найден: {dn}")
    return e


def optimistic_value_change(attr: str, old, new) -> Changes:
    """Delete-old + add-new in one modify: fails with a conflict if someone changed the value meanwhile."""
    old_empty = old in (None, "", [])
    new_empty = new in (None, "", [])
    if old_empty and new_empty:
        return {}
    if old_empty:
        return {attr: [(ModOp.ADD, [new])]}
    if new_empty:
        return {attr: [(ModOp.DELETE, [old])]}
    if str(old) == str(new):
        return {}
    return {attr: [(ModOp.DELETE, [old]), (ModOp.ADD, [new])]}


def membership_paths(gw: DirectoryGateway, start_dn: str, *, cancel: CancelToken | None = None,
                     max_groups: int = 5000) -> list[dict]:
    """Breadth-first walk over memberOf: every group reached with the chain that leads to it.

    Returns dicts {dn, name, depth, path (list of group names from the start object), cycle(bool)}.
    Primary group (primaryGroupID) is added separately as depth-1 membership.
    """
    start = gw.get(start_dn, ["memberOf", "primaryGroupID", "objectSid"])
    if start is None:
        raise ObjectNotFoundError(f"Объект не найден: {start_dn}")
    results: dict[str, dict] = {}
    queue: deque[tuple[str, list[str], int]] = deque((g, [], 1) for g in start.values("memberOf"))
    cycles: set[str] = set()
    while queue:
        if cancel:
            cancel.raise_if_cancelled()
        gdn, path, depth = queue.popleft()
        nd = normalize_dn(gdn)
        name = rdn_value(gdn)
        if nd in results:
            if any(normalize_dn(p) == nd for p in path):
                cycles.add(nd)
            continue
        results[nd] = {"dn": gdn, "name": name, "depth": depth, "path": [rdn_value(p) for p in path], "cycle": False}
        if len(results) >= max_groups:
            break
        ge = gw.get(gdn, ["memberOf"])
        if ge is None:
            continue
        for parent in ge.values("memberOf"):
            np_ = normalize_dn(parent)
            if np_ == normalize_dn(start_dn) or any(normalize_dn(p) == np_ for p in path + [gdn]):
                cycles.add(np_)
                continue
            queue.append((parent, path + [gdn], depth + 1))
    for nd in cycles:
        if nd in results:
            results[nd]["cycle"] = True
    pgid = start.int("primaryGroupID")
    sid = start.first("objectSid")
    if pgid and sid is not None:
        from ..ldap.adtypes import sid_domain_part, sid_to_str, str_to_sid
        domain_sid = sid_domain_part(sid_to_str(sid))
        pg = gw.search_list(gw.info.base_dn, Equals("objectSid", str_to_sid(f"{domain_sid}-{pgid}")), ["cn"])
        if pg and normalize_dn(pg[0].dn) not in results:
            results[normalize_dn(pg[0].dn)] = {"dn": pg[0].dn, "name": pg[0].str("cn") or rdn_value(pg[0].dn), "depth": 1,
                                               "path": [], "cycle": False, "primary": True}
    return sorted(results.values(), key=lambda r: (r["depth"], r["name"].casefold()))


def search_records(gw: DirectoryGateway, base: str, flt, attributes: list[str], factory, *, limit: int = 0,
                   cancel: CancelToken | None = None, scope: Scope = Scope.SUBTREE, sd_flags: int | None = None
                   ) -> tuple[list, SearchStats]:
    stats = SearchStats()
    items = []
    for e in gw.search(base, flt, attributes, scope, cancel=cancel, stats=stats, sd_flags=sd_flags):
        items.append(factory(e))
        if limit and len(items) >= limit:
            stats.truncated = True
            break
    return items, stats


def ensure_conflict_free(gw: DirectoryGateway, target_parent: str, rdn: str) -> None:
    candidate = f"{rdn},{target_parent}"
    if gw.get(candidate, ["distinguishedName"]) is not None:
        raise ConflictError(f"В целевом контейнере уже существует объект «{rdn}»")
