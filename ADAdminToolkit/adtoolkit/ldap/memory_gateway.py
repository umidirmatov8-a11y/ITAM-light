"""In-memory directory that behaves like Active Directory for the purposes of this application.

Used by the demo mode (UI without a domain controller) and by the automated tests. It evaluates the same LDAP
filters the services send to a real DC (including the AD matching rules 803/804/1941), simulates paged results,
constructed attributes (memberOf, msDS-User-Account-Control-Computed, msDS-UserPasswordExpiryTimeComputed,
tokenGroups, allowedAttributesEffective, allowedChildClassesEffective) and returns LDAP result codes / AD diagnostic
messages that go through the same error mapping as real ldap3 results.

No password is stored: a password "set" only validates the domain policy and updates pwdLastSet.
"""
from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Iterator

from ..core.cancel import CancelToken
from ..core import errors as E
from ..models.connection import DirectoryInfo
from . import error_mapping as EM
from .adtypes import (FILETIME_NEVER, UAC, attribute_kind, datetime_to_filetime, filetime_to_datetime,
                      interval_to_timedelta, parse_generalized_time, sid_rid, str_to_sid, utcnow)
from .dn import build_dn, dn_to_dns_domain, first_rdn, is_descendant, normalize_dn, parent_dn, parse_dn, rdn_value
from .filters import (MATCH_BIT_AND, MATCH_BIT_OR, MATCH_IN_CHAIN, And, Approx, Equals, Extensible, FilterNode,
                      GreaterOrEqual, LessOrEqual, Not, Or, Present, Substring, parse_filter)
from .gateway import CaseInsensitiveDict, Changes, DirectoryGateway, Entry, ModOp, Scope, SearchStats

DN_ATTRIBUTES = {"member", "memberof", "manager", "directreports", "distinguishedname", "managedby", "objectcategory",
                 "msds-psoapplied", "msds-resultantpso"}
SINGLE_VALUED = {"useraccountcontrol", "samaccountname", "userprincipalname", "displayname", "givenname", "sn",
                 "mail", "title", "department", "company", "manager", "telephonenumber", "mobile", "description",
                 "physicaldeliveryofficename", "employeeid", "accountexpires", "pwdlastset", "lockouttime", "grouptype",
                 "cn", "name", "l", "st", "streetaddress", "postalcode", "operatingsystem", "operatingsystemversion",
                 "dnshostname", "lastlogontimestamp", "info", "admincount", "primarygroupid"}
CONSTRUCTED = {"memberof", "msds-user-account-control-computed", "msds-userpasswordexpirytimecomputed",
               "tokengroups", "allowedattributeseffective", "allowedchildclasseseffective", "primarygrouptoken",
               "distinguishedname", "canonicalname"}
BASE_ONLY = {"tokengroups", "primarygrouptoken"}

USER_WRITABLE = ["givenName", "sn", "displayName", "description", "title", "department", "company", "mail",
                 "telephoneNumber", "mobile", "physicalDeliveryOfficeName", "manager", "employeeID", "streetAddress",
                 "l", "st", "postalCode", "userAccountControl", "lockoutTime", "pwdLastSet", "accountExpires", "info",
                 "userPrincipalName", "sAMAccountName", "cn", "name"]
GROUP_WRITABLE = ["member", "description", "info", "managedBy", "groupType", "mail"]
COMPUTER_WRITABLE = ["userAccountControl", "description", "location", "managedBy"]
OU_CHILD_CLASSES = ["user", "computer", "group", "organizationalUnit", "contact", "inetOrgPerson"]


def _result(code: int, message: str = "", description: str = "") -> dict:
    return {"result": code, "message": message, "description": description or str(code)}


class _Fail(Exception):
    def __init__(self, result: dict):
        self.result = result
        super().__init__(result.get("message"))


@dataclass
class MemoryStore:
    """Shared object storage (multiple gateway views — e.g. per-DC clones — share one store)."""
    objects: dict[str, Entry] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)
    version: int = 0
    next_rid: int = 5000
    domain_dn: str = ""
    domain_sid: str = ""
    denied_write: set[str] = field(default_factory=set)        # normalized DNs where writes are denied
    protected_deletion: set[str] = field(default_factory=set)  # normalized DNs protected from accidental deletion
    dc_last_logon: dict[str, dict[str, int]] = field(default_factory=dict)   # host -> normdn -> lastLogon
    fail_next: list[tuple[str, dict]] = field(default_factory=list)          # (operation, result) injections
    domain_controllers: list[str] = field(default_factory=list)
    _member_of_cache: tuple[int, dict] | None = None

    def bump(self):
        self.version += 1
        self._member_of_cache = None


class MemoryGateway(DirectoryGateway):
    is_demo = True

    def __init__(self, store: MemoryStore | None = None, *, bound_user_dn: str = "", dc_host: str = "",
                 encrypted: bool = True, max_page_size: int = 1000, read_only: bool = True):
        super().__init__()
        self.store = store or MemoryStore()
        self.bound_user_dn = bound_user_dn
        self.dc_host = dc_host or (self.store.domain_controllers[0] if self.store.domain_controllers else "dc01.demo.local")
        self.max_page_size = max_page_size
        self.read_only = read_only
        self._connected = True
        self.last_page_sizes: list[int] = []
        self.info = self._build_info(encrypted)

    # ------------------------------------------------------------------------------------------------------------
    def _build_info(self, encrypted: bool) -> DirectoryInfo:
        from .ldap3_gateway import policy_from_entry
        dn = self.store.domain_dn
        info = DirectoryInfo(
            domain_dns=dn_to_dns_domain(dn), netbios_name=(dn_to_dns_domain(dn).split(".")[0] or "").upper(),
            base_dn=dn, default_naming_context=dn, configuration_nc=f"CN=Configuration,{dn}",
            schema_nc=f"CN=Schema,CN=Configuration,{dn}", root_domain_nc=dn, dc_host=self.dc_host,
            domain_sid=self.store.domain_sid, domain_functionality=7, forest_functionality=7, dc_functionality=7,
            bound_identity=f"u:{(dn_to_dns_domain(dn).split('.')[0] or 'DEMO').upper()}\\{rdn_value(self.bound_user_dn) if self.bound_user_dn else 'demo'}",
            bound_user_dn=self.bound_user_dn, connected_at=utcnow(), last_success_at=utcnow(),
            security_label="Демо-режим (каталог в памяти, контроллер домена не используется)", encrypted=encrypted,
            supported_controls=["1.2.840.113556.1.4.319", "1.2.840.113556.1.4.801", "1.2.840.113556.1.4.1941"],
            domain_controllers=list(self.store.domain_controllers), is_demo=True,
        )
        dom = self.store.objects.get(normalize_dn(dn)) if dn else None
        if dom is not None:
            info.policy = policy_from_entry(dom)
        return info

    @property
    def connected(self) -> bool:
        return self._connected

    def close(self) -> None:
        self._connected = False
        self._notify("disconnected", "Отключено")

    def reconnect(self) -> None:
        self._connected = True
        self._notify("connected", "Соединение восстановлено")

    def clone_for_host(self, host: str) -> "MemoryGateway":
        if host not in self.store.domain_controllers:
            raise E.ConnectionFailedError(f"Контроллер {host} недоступен")
        return MemoryGateway(self.store, bound_user_dn=self.bound_user_dn, dc_host=host,
                             encrypted=self.info.encrypted, read_only=True)

    def _check_injected(self, operation: str):
        with self.store.lock:
            for i, (op, res) in enumerate(self.store.fail_next):
                if op == operation or op == "*":
                    del self.store.fail_next[i]
                    if res.get("exception"):
                        raise res["exception"]
                    raise _Fail(res)

    def _ensure(self):
        if not self._connected:
            raise E.NotConnectedError()

    # ------------------------------------------------------------------------------------------------------------
    # Constructed attributes
    # ------------------------------------------------------------------------------------------------------------
    def _member_of_map(self) -> dict[str, list[str]]:
        cache = self.store._member_of_cache
        if cache and cache[0] == self.store.version:
            return cache[1]
        mapping: dict[str, list[str]] = {}
        for ndn, obj in self.store.objects.items():
            for m in obj.values("member"):
                mapping.setdefault(normalize_dn(m), []).append(obj.dn)
        self.store._member_of_cache = (self.store.version, mapping)
        return mapping

    def _transitive_groups(self, ndn: str) -> list[str]:
        mof = self._member_of_map()
        seen: dict[str, str] = {}
        stack = list(mof.get(ndn, []))
        while stack:
            g = stack.pop()
            ng = normalize_dn(g)
            if ng in seen:
                continue
            seen[ng] = g
            stack.extend(mof.get(ng, []))
        return list(seen.values())

    def _transitive_members(self, group_ndn: str) -> set[str]:
        out: set[str] = set()
        stack = [group_ndn]
        while stack:
            g = self.store.objects.get(stack.pop())
            if g is None:
                continue
            for m in g.values("member"):
                nm = normalize_dn(m)
                if nm not in out:
                    out.add(nm)
                    stack.append(nm)
        return out

    def _domain_policy(self):
        dom = self.store.objects.get(normalize_dn(self.store.domain_dn))
        if dom is None:
            return None, None, 0
        return (interval_to_timedelta(dom.first("maxPwdAge")), interval_to_timedelta(dom.first("lockoutDuration")),
                dom.int("minPwdLength", 0))

    def _computed_uac(self, obj: Entry) -> int:
        flags = 0
        max_age, lockout_duration, _ = self._domain_policy()
        now = utcnow()
        lt = obj.int("lockoutTime", 0) or 0
        if lt > 0:
            locked_at = filetime_to_datetime(lt)
            if lockout_duration is None or (locked_at and locked_at + lockout_duration > now):
                flags |= UAC.LOCKOUT
        uac = obj.int("userAccountControl", 0) or 0
        pls = obj.first("pwdLastSet")
        if pls is not None and int(pls) == 0 and not uac & UAC.DONT_EXPIRE_PASSWORD:
            flags |= UAC.PASSWORD_EXPIRED
        elif pls and max_age and not uac & UAC.DONT_EXPIRE_PASSWORD:
            set_at = filetime_to_datetime(pls)
            if set_at and set_at + max_age < now:
                flags |= UAC.PASSWORD_EXPIRED
        return flags

    def _expiry_computed(self, obj: Entry) -> int:
        max_age, _, _ = self._domain_policy()
        uac = obj.int("userAccountControl", 0) or 0
        if uac & UAC.DONT_EXPIRE_PASSWORD or not max_age:
            return FILETIME_NEVER
        pls = obj.int("pwdLastSet", 0) or 0
        if pls == 0:
            return 0
        set_at = filetime_to_datetime(pls)
        return datetime_to_filetime(set_at + max_age) if set_at else 0

    def _rights_for(self, obj: Entry) -> tuple[list[str], list[str]]:
        ndn = normalize_dn(obj.dn)
        if ndn in self.store.denied_write or any(is_descendant(ndn, d) for d in self.store.denied_write):
            return [], []
        classes = obj.object_classes
        if "computer" in classes:
            return list(COMPUTER_WRITABLE), []
        if "user" in classes:
            return list(USER_WRITABLE), []
        if "group" in classes:
            return list(GROUP_WRITABLE), []
        if "organizationalunit" in classes or "container" in classes or "domaindns" in classes or "builtindomain" in classes:
            return ["description", "managedBy"], list(OU_CHILD_CLASSES)
        return [], []

    def _attr_values(self, obj: Entry, name: str, *, base: bool = False) -> list:
        n = name.lower()
        if n == "distinguishedname":
            return [obj.dn]
        if n == "memberof":
            return list(self._member_of_map().get(normalize_dn(obj.dn), []))
        if n == "msds-user-account-control-computed":
            return [self._computed_uac(obj)] if "user" in obj.object_classes else []
        if n == "msds-userpasswordexpirytimecomputed":
            return [self._expiry_computed(obj)] if "user" in obj.object_classes and "computer" not in obj.object_classes else []
        if n == "allowedattributeseffective":
            return self._rights_for(obj)[0]
        if n == "allowedchildclasseseffective":
            return self._rights_for(obj)[1]
        if n == "canonicalname":
            from .dn import canonical_name
            return [canonical_name(obj.dn)]
        if n == "tokengroups":
            if not base:
                return []
            sids = []
            for g in self._transitive_groups(normalize_dn(obj.dn)):
                go = self.store.objects.get(normalize_dn(g))
                if go is not None and go.first("objectSid"):
                    sids.append(go.first("objectSid"))
            pg = obj.int("primaryGroupID")
            if pg and self.store.domain_sid:
                sids.append(str_to_sid(f"{self.store.domain_sid}-{pg}"))
            return sids
        if n == "primarygrouptoken":
            if not base or "group" not in obj.object_classes:
                return []
            rid = sid_rid(obj.first("objectSid")) if obj.first("objectSid") else None
            return [rid] if rid is not None else []
        if n == "lastlogon" and self.dc_host in self.store.dc_last_logon:
            v = self.store.dc_last_logon[self.dc_host].get(normalize_dn(obj.dn))
            return [v] if v is not None else []
        return obj.values(name)

    # ------------------------------------------------------------------------------------------------------------
    # Filter evaluation
    # ------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _cmp_values(name: str, stored, asserted: str):
        """Return (stored_key, asserted_key) comparable values for the attribute syntax."""
        n = name.lower()
        if isinstance(stored, bool):
            return stored, asserted.upper() == "TRUE"
        if isinstance(stored, int):
            try:
                return stored, int(asserted)
            except ValueError:
                return str(stored), asserted
        if isinstance(stored, datetime):
            parsed = parse_generalized_time(asserted)
            return stored, parsed if parsed else asserted
        if isinstance(stored, (bytes, bytearray)):
            try:
                return bytes(stored), asserted.encode("latin-1")
            except UnicodeEncodeError:
                return bytes(stored), asserted.encode("utf-8")
        if n in DN_ATTRIBUTES:
            return normalize_dn(str(stored)), normalize_dn(asserted)
        return str(stored).casefold(), asserted.casefold()

    def _match(self, node: FilterNode, obj: Entry) -> bool:
        if isinstance(node, And):
            return all(self._match(c, obj) for c in node.children)
        if isinstance(node, Or):
            return any(self._match(c, obj) for c in node.children)
        if isinstance(node, Not):
            return not self._match(node.child, obj)
        if isinstance(node, Present):
            if node.attr.lower() == "objectclass":
                return True
            return bool(self._attr_values(obj, node.attr))
        if isinstance(node, Equals):
            n = node.attr.lower()
            value = str(node.value)
            if n == "objectcategory":
                target = value.casefold()
                for v in obj.values("objectCategory"):
                    if str(v).casefold() == target or rdn_value(str(v)).casefold() == target:
                        return True
                return False
            for v in self._attr_values(obj, node.attr):
                if isinstance(v, (bytes, bytearray)):
                    candidates = []
                    for enc in ("utf-8", "latin-1"):
                        try:
                            candidates.append(value.encode(enc))
                        except UnicodeEncodeError:
                            pass
                    if bytes(v) in candidates:
                        return True
                    continue
                a, b = self._cmp_values(node.attr, v, value)
                if a == b:
                    return True
            return False
        if isinstance(node, Approx):
            return self._match(Equals(node.attr, node.value), obj)
        if isinstance(node, (GreaterOrEqual, LessOrEqual)):
            for v in self._attr_values(obj, node.attr):
                a, b = self._cmp_values(node.attr, v, str(node.value))
                try:
                    if (a >= b) if isinstance(node, GreaterOrEqual) else (a <= b):
                        return True
                except TypeError:
                    continue
            return False
        if isinstance(node, Substring):
            for v in self._attr_values(obj, node.attr):
                s = str(v).casefold()
                pos = 0
                if node.initial:
                    if not s.startswith(node.initial.casefold()):
                        continue
                    pos = len(node.initial)
                ok = True
                for part in node.any:
                    idx = s.find(part.casefold(), pos)
                    if idx < 0:
                        ok = False
                        break
                    pos = idx + len(part)
                if not ok:
                    continue
                if node.final and not (s.endswith(node.final.casefold()) and len(s) - len(node.final) >= pos):
                    continue
                return True
            return False
        if isinstance(node, Extensible):
            rule = node.rule
            attr = node.attr or ""
            if rule in (MATCH_BIT_AND, MATCH_BIT_OR):
                try:
                    mask = int(str(node.value))
                except ValueError:
                    return False
                for v in self._attr_values(obj, attr):
                    try:
                        iv = int(v) & 0xFFFFFFFF if attr.lower() == "grouptype" else int(v)
                    except (TypeError, ValueError):
                        continue
                    m = mask & 0xFFFFFFFF if attr.lower() == "grouptype" else mask
                    if (rule == MATCH_BIT_AND and iv & m == m) or (rule == MATCH_BIT_OR and iv & m):
                        return True
                return False
            if rule == MATCH_IN_CHAIN:
                target = normalize_dn(str(node.value))
                if attr.lower() == "member":
                    return target in self._transitive_members(normalize_dn(obj.dn))
                if attr.lower() == "memberof":
                    return any(normalize_dn(g) == target for g in self._transitive_groups(normalize_dn(obj.dn)))
                return False
            if rule is None and attr:
                return self._match(Equals(attr, node.value), obj)
            return False
        return False

    # ------------------------------------------------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------------------------------------------------
    def _project(self, obj: Entry, attributes: list[str] | None, base: bool) -> Entry:
        attrs = CaseInsensitiveDict()
        wanted = [a for a in (attributes or ["*"])]
        if "1.1" in wanted and len(wanted) == 1:
            return Entry(obj.dn, attrs)
        names: list[str] = []
        if "*" in wanted:
            names.extend(obj.attributes.keys())
        names.extend(a for a in wanted if a not in ("*", "+", "1.1"))
        for name in names:
            vals = self._attr_values(obj, name, base=base)
            if vals:
                attrs[name] = copy.copy(list(vals))
        return Entry(obj.dn, attrs)

    def root_dse(self) -> Entry:
        info = self.info
        return Entry("", CaseInsensitiveDict({
            "defaultNamingContext": [info.default_naming_context],
            "configurationNamingContext": [info.configuration_nc],
            "schemaNamingContext": [info.schema_nc],
            "rootDomainNamingContext": [info.root_domain_nc],
            "dnsHostName": [self.dc_host],
            "domainFunctionality": [7], "forestFunctionality": [7], "domainControllerFunctionality": [7],
            "supportedControl": list(info.supported_controls),
            "currentTime": [utcnow()], "isSynchronized": [True],
        }))

    def search(self, base: str, flt: FilterNode | str, attributes: Iterable[str] | None = None,
               scope: Scope = Scope.SUBTREE, *, page_size: int | None = None, size_limit: int = 0,
               cancel: CancelToken | None = None, stats: SearchStats | None = None,
               sd_flags: int | None = None) -> Iterator[Entry]:
        self._ensure()
        # render + re-parse: the in-memory directory sees exactly the escaped text a real DC would receive
        node = parse_filter(self.filter_text(flt))
        attributes = list(attributes) if attributes else None
        stats = stats if stats is not None else SearchStats()
        try:
            self._check_injected("search")
        except _Fail as f:
            raise EM.map_result(f.result, "search", base) from None
        if base == "" and scope is Scope.BASE:
            stats.pages += 1
            stats.entries += 1
            yield self._project(self.root_dse(), attributes, True)
            return
        with self.store.lock:
            nbase = normalize_dn(base)
            if nbase not in self.store.objects:
                raise EM.map_result(_result(EM.NO_SUCH_OBJECT, "0000208D: NameErr: DSID-03100241, problem 2001 (NO_OBJECT)",
                                            "noSuchObject"), "search", base)
            matches: list[Entry] = []
            for ndn, obj in self.store.objects.items():
                if scope is Scope.BASE and ndn != nbase:
                    continue
                if scope is Scope.ONELEVEL and normalize_dn(parent_dn(obj.dn)) != nbase:
                    continue
                if scope is Scope.SUBTREE and not is_descendant(ndn, nbase, include_self=True):
                    continue
                if self._match(node, obj):
                    matches.append(self._project(obj, attributes, scope is Scope.BASE))
        matches.sort(key=lambda e: normalize_dn(e.dn)[::-1])
        if size_limit and len(matches) > size_limit:
            matches = matches[:size_limit]
            stats.truncated = True
        if page_size is None:
            page_size = self.default_page_size
        effective = min(page_size, self.max_page_size) if page_size else len(matches) or 1
        self.last_page_sizes = []
        for start in range(0, max(len(matches), 1), effective):
            if cancel:
                cancel.raise_if_cancelled()
            page = matches[start:start + effective]
            stats.pages += 1
            self.last_page_sizes.append(len(page))
            for entry in page:
                stats.entries += 1
                yield entry
            if not page:
                break

    def who_am_i(self) -> str:
        return self.info.bound_identity

    def ping(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------------------------------------------------
    def _deny_check(self, ndn: str):
        for d in self.store.denied_write:
            if ndn == d or is_descendant(ndn, d):
                raise _Fail(_result(EM.INSUFFICIENT_ACCESS_RIGHTS,
                                    "00000005: SecErr: DSID-03152870, problem 4003 (INSUFF_ACCESS_RIGHTS), data 0",
                                    "insufficientAccessRights"))

    def _wrap(self, operation: str, target: str, fn):
        self._ensure()
        self._guard_write()
        try:
            self._check_injected(operation)
            with self.store.lock:
                result = fn()
                self.store.bump()
                return result
        except _Fail as f:
            raise EM.map_result(f.result, operation, target) from None

    def modify(self, dn: str, changes: Changes) -> None:
        if any(a.lower() == "unicodepwd" for a in changes):
            raise E.ValidationError("Изменение пароля выполняется только через функцию сброса пароля")

        def do():
            ndn = normalize_dn(dn)
            obj = self.store.objects.get(ndn)
            if obj is None:
                raise _Fail(_result(EM.NO_SUCH_OBJECT, "0000208D: NameErr: problem 2001 (NO_OBJECT)", "noSuchObject"))
            self._deny_check(ndn)
            new_attrs = obj.attributes.copy()
            for attr, ops in changes.items():
                for op, values in ops:
                    op = ModOp(op)
                    values = list(values)
                    current = list(new_attrs.get(attr) or [])
                    if attr.lower() == "member":
                        for v in values:
                            if normalize_dn(str(v)) not in self.store.objects and op is not ModOp.DELETE:
                                raise _Fail(_result(EM.NO_SUCH_OBJECT, "0000208D: NameErr: problem 2001 (NO_OBJECT)"))
                    if op is ModOp.REPLACE:
                        if values:
                            new_attrs[attr] = [self._coerce(attr, v) for v in values]
                        elif attr in new_attrs:
                            del new_attrs[attr]
                    elif op is ModOp.ADD:
                        for v in values:
                            cv = self._coerce(attr, v)
                            if any(self._same(attr, cv, c) for c in current):
                                raise _Fail(_result(EM.ATTRIBUTE_OR_VALUE_EXISTS,
                                                    "00002083: AtrErr: DSID-03151904, problem 1006 (ATT_OR_VALUE_EXISTS)"))
                            if attr.lower() in SINGLE_VALUED and current:
                                raise _Fail(_result(EM.CONSTRAINT_VIOLATION,
                                                    "00002082: AtrErr: problem 1005 (CONSTRAINT_ATT_TYPE)"))
                            current.append(cv)
                        new_attrs[attr] = current
                    elif op is ModOp.DELETE:
                        if not values:
                            if attr not in new_attrs:
                                raise _Fail(_result(EM.NO_SUCH_ATTRIBUTE, "00002080: AtrErr: problem 16 (NO_ATTRIBUTE_OR_VAL)"))
                            del new_attrs[attr]
                            continue
                        for v in values:
                            cv = self._coerce(attr, v)
                            idx = next((i for i, c in enumerate(current) if self._same(attr, cv, c)), None)
                            if idx is None:
                                raise _Fail(_result(EM.NO_SUCH_ATTRIBUTE,
                                                    "00002080: AtrErr: DSID-03152B1A, problem 1001 (NO_ATTRIBUTE_OR_VAL)"))
                            current.pop(idx)
                        if current:
                            new_attrs[attr] = current
                        elif attr in new_attrs:
                            del new_attrs[attr]
            new_attrs["whenChanged"] = [utcnow()]
            obj.attributes = new_attrs
        self._wrap("modify", dn, do)

    @staticmethod
    def _coerce(attr: str, value):
        kind = attribute_kind(attr)
        if kind == "int":
            try:
                if attr.lower() == "pwdlastset" and int(value) == -1:
                    return datetime_to_filetime(utcnow())   # AD semantics: -1 sets pwdLastSet to "now"
                return int(value)
            except (TypeError, ValueError):
                raise _Fail(_result(EM.INVALID_ATTRIBUTE_SYNTAX, "0000200B: AtrErr: problem 1001 (INVALID_SYNTAX)")) from None
        return value

    @staticmethod
    def _same(attr: str, a, b) -> bool:
        if attr.lower() in DN_ATTRIBUTES:
            return normalize_dn(str(a)) == normalize_dn(str(b))
        if isinstance(a, str) and isinstance(b, str):
            return a.casefold() == b.casefold()
        return a == b

    def add(self, dn: str, object_classes: list[str], attributes: dict) -> None:
        def do():
            ndn = normalize_dn(dn)
            parent = parent_dn(dn)
            nparent = normalize_dn(parent)
            if nparent not in self.store.objects:
                raise _Fail(_result(EM.NO_SUCH_OBJECT, "0000208D: NameErr: problem 2001 (NO_OBJECT)"))
            self._deny_check(nparent)
            pobj = self.store.objects[nparent]
            allowed_children = [c.lower() for c in self._rights_for(pobj)[1]]
            primary = object_classes[-1].lower()
            if primary not in allowed_children:
                raise _Fail(_result(EM.INSUFFICIENT_ACCESS_RIGHTS, "00000005: SecErr: problem 4003 (INSUFF_ACCESS_RIGHTS)"))
            if ndn in self.store.objects:
                raise _Fail(_result(EM.ENTRY_ALREADY_EXISTS, "00002071: UpdErr: DSID-031B0D16, problem 6005 (ENTRY_EXISTS)"))
            sam = attributes.get("sAMAccountName")
            if sam:
                for obj in self.store.objects.values():
                    if obj.str("sAMAccountName").casefold() == str(sam).casefold():
                        raise _Fail(_result(EM.CONSTRAINT_VIOLATION, "00000524: UpdErr: DSID-031A11E2, problem 6005 (ENTRY_EXISTS)"))
            attrs = CaseInsensitiveDict()
            for k, v in attributes.items():
                if v in (None, "", []):
                    continue
                attrs[k] = [self._coerce(k, x) for x in (v if isinstance(v, list) else [v])]
            attrs["objectClass"] = list(object_classes)
            if "cn" not in attrs and first_rdn(dn).lower().startswith("cn="):
                attrs["cn"] = [rdn_value(dn)]
            attrs["name"] = [rdn_value(dn)]
            now = utcnow()
            attrs["whenCreated"] = [now]
            attrs["whenChanged"] = [now]
            attrs["objectGUID"] = [uuid.uuid4().bytes_le]
            category = {"user": "Person", "computer": "Computer", "group": "Group",
                        "organizationalunit": "Organizational-Unit", "contact": "Person"}.get(primary, "Top")
            attrs["objectCategory"] = [f"CN={category},CN=Schema,CN=Configuration,{self.store.domain_dn}"]
            if primary in ("user", "computer", "group"):
                self.store.next_rid += 1
                attrs["objectSid"] = [str_to_sid(f"{self.store.domain_sid}-{self.store.next_rid}")]
            if primary == "user":
                attrs.setdefault("userAccountControl", [0x202])
                attrs.setdefault("primaryGroupID", [513])
                attrs.setdefault("pwdLastSet", [0])
                attrs.setdefault("accountExpires", [FILETIME_NEVER])
            if primary == "computer":
                attrs.setdefault("userAccountControl", [0x1000])
                attrs.setdefault("primaryGroupID", [515])
            self.store.objects[ndn] = Entry(dn, attrs)
        self._wrap("add", dn, do)

    def delete(self, dn: str) -> None:
        def do():
            ndn = normalize_dn(dn)
            if ndn not in self.store.objects:
                raise _Fail(_result(EM.NO_SUCH_OBJECT, "0000208D: NameErr: problem 2001 (NO_OBJECT)"))
            self._deny_check(ndn)
            if ndn in self.store.protected_deletion:
                raise _Fail(_result(EM.INSUFFICIENT_ACCESS_RIGHTS, "00000005: SecErr: DSID-03152857, problem 4003 (INSUFF_ACCESS_RIGHTS)"))
            if any(is_descendant(other, ndn) for other in self.store.objects if other != ndn):
                raise _Fail(_result(EM.NOT_ALLOWED_ON_NON_LEAF, "00002015: SvcErr: problem 5003 (WILL_NOT_PERFORM)"))
            del self.store.objects[ndn]
            for obj in self.store.objects.values():
                members = obj.values("member")
                if members:
                    kept = [m for m in members if normalize_dn(m) != ndn]
                    if len(kept) != len(members):
                        obj.attributes["member"] = kept
        self._wrap("delete", dn, do)

    def move(self, dn: str, new_parent: str, new_rdn: str | None = None) -> str:
        holder = {}

        def do():
            ndn = normalize_dn(dn)
            obj = self.store.objects.get(ndn)
            if obj is None:
                raise _Fail(_result(EM.NO_SUCH_OBJECT, "0000208D: NameErr: problem 2001 (NO_OBJECT)"))
            nparent = normalize_dn(new_parent)
            target = self.store.objects.get(nparent)
            if target is None:
                raise _Fail(_result(EM.NO_SUCH_OBJECT, "0000208D: NameErr: problem 2001 (NO_OBJECT)"))
            self._deny_check(ndn)
            self._deny_check(nparent)
            if ndn in self.store.protected_deletion:
                raise _Fail(_result(EM.INSUFFICIENT_ACCESS_RIGHTS, "00000005: SecErr: problem 4003 (INSUFF_ACCESS_RIGHTS)"))
            if is_descendant(nparent, ndn, include_self=True):
                raise _Fail(_result(EM.UNWILLING_TO_PERFORM, "00002093: problem 5003 (WILL_NOT_PERFORM): cannot move under itself"))
            rdn = new_rdn or first_rdn(dn)
            new_dn = f"{rdn},{new_parent}"
            nnew = normalize_dn(new_dn)
            if nnew in self.store.objects:
                raise _Fail(_result(EM.ENTRY_ALREADY_EXISTS, "00002071: UpdErr: problem 6005 (ENTRY_EXISTS)"))
            # rename the object and all descendants, then fix DN references (AD maintains linked attributes)
            renames: dict[str, str] = {}
            for other_ndn, other in list(self.store.objects.items()):
                if other_ndn == ndn or is_descendant(other_ndn, ndn):
                    suffix_len = len(parse_dn(other.dn)) - len(parse_dn(dn))
                    head = build_dn(parse_dn(other.dn)[:suffix_len]) if suffix_len else ""
                    moved = f"{head},{new_dn}" if head else new_dn
                    renames[other_ndn] = moved
            for old_ndn, moved in renames.items():
                ent = self.store.objects.pop(old_ndn)
                ent.dn = moved
                self.store.objects[normalize_dn(moved)] = ent
            for ent in self.store.objects.values():
                for attr in ("member", "manager", "managedBy"):
                    vals = ent.values(attr)
                    if vals:
                        ent.attributes[attr] = [renames.get(normalize_dn(v), v) for v in vals]
            for host_map in self.store.dc_last_logon.values():
                for old_ndn, moved in renames.items():
                    if old_ndn in host_map:
                        host_map[normalize_dn(moved)] = host_map.pop(old_ndn)
            holder["dn"] = new_dn
        self._wrap("move", dn, do)
        return holder["dn"]

    def set_password(self, dn: str, new_password: str) -> None:
        self._guard_write()
        self._require_encryption("Установка пароля")

        def do():
            ndn = normalize_dn(dn)
            obj = self.store.objects.get(ndn)
            if obj is None:
                raise _Fail(_result(EM.NO_SUCH_OBJECT, "0000208D: NameErr: problem 2001 (NO_OBJECT)"))
            self._deny_check(ndn)
            dom = self.store.objects.get(normalize_dn(self.store.domain_dn))
            min_len = dom.int("minPwdLength", 0) if dom else 0
            complexity = bool((dom.int("pwdProperties", 0) or 0) & 1) if dom else False
            from ..services.password_service import check_complexity
            ok = len(new_password) >= (min_len or 0)
            if ok and complexity:
                ok = not check_complexity(new_password, obj.str("sAMAccountName"), obj.str("displayName"))
            if not ok:
                raise _Fail(_result(EM.CONSTRAINT_VIOLATION,
                                    "0000052D: Constraint violation - check_password_restrictions: the password does not meet the complexity criteria!"))
            obj.attributes["pwdLastSet"] = [datetime_to_filetime(utcnow())]
            obj.attributes["whenChanged"] = [utcnow()]
        self._wrap("set_password", dn, do)


def make_entry(dn: str, **attrs) -> Entry:
    data = CaseInsensitiveDict()
    for k, v in attrs.items():
        key = k.replace("__", "-")
        data[key] = v if isinstance(v, list) else [v]
    return Entry(dn, data)
