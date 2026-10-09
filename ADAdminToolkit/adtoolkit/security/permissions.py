"""Permission checks before changes and protection of privileged groups / accounts.

* Effective write rights are read from the constructed attributes ``allowedAttributesEffective`` and
  ``allowedChildClassesEffective`` that Active Directory computes for the bound account. This is a pre-check only:
  the domain controller always enforces its ACL and the error is reported if the pre-check could not see a deny.
* Privileged groups are identified by SID (works with localized group names), not by display name.
* The application never tries to bypass ACLs or elevate privileges.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.errors import PermissionDeniedError, ProtectedObjectError
from ..ldap.adtypes import sid_rid, sid_to_str, str_to_sid
from ..ldap.dn import normalize_dn, rdn_value
from ..ldap.filters import And, Equals, Or, in_chain
from ..ldap.gateway import DirectoryGateway

# RID -> (default English name, critical)
PRIVILEGED_DOMAIN_RIDS = {
    512: ("Domain Admins", True),
    518: ("Schema Admins", True),
    519: ("Enterprise Admins", True),
    520: ("Group Policy Creator Owners", False),
    526: ("Key Admins", False),
    527: ("Enterprise Key Admins", False),
    516: ("Domain Controllers", False),
    498: ("Enterprise Read-only Domain Controllers", False),
    521: ("Read-only Domain Controllers", False),
}
PRIVILEGED_BUILTIN_SIDS = {
    "S-1-5-32-544": ("Administrators", True),
    "S-1-5-32-548": ("Account Operators", False),
    "S-1-5-32-549": ("Server Operators", False),
    "S-1-5-32-550": ("Print Operators", False),
    "S-1-5-32-551": ("Backup Operators", False),
    "S-1-5-32-552": ("Replicator", False),
}
DEFAULT_EXTRA_PRIVILEGED_NAMES = ["DnsAdmins", "Cert Publishers"]


@dataclass
class PrivilegedGroup:
    dn: str
    name: str
    sid: str
    well_known: str
    critical: bool


@dataclass
class RightsSummary:
    identity: str = ""
    user_dn: str = ""
    groups: list[str] = field(default_factory=list)
    privileged_groups: list[str] = field(default_factory=list)
    can_read_directory: bool = False
    create_user_in_default: bool | None = None
    create_group_in_default: bool | None = None
    notes: list[str] = field(default_factory=list)


class PrivilegedGroupRegistry:
    def __init__(self, gateway: DirectoryGateway, extra_names: list[str] | None = None):
        self.gw = gateway
        self.extra_names = list(extra_names if extra_names is not None else DEFAULT_EXTRA_PRIVILEGED_NAMES)
        self._groups: dict[str, PrivilegedGroup] | None = None

    def load(self) -> dict[str, PrivilegedGroup]:
        if self._groups is not None:
            return self._groups
        groups: dict[str, PrivilegedGroup] = {}
        base = self.gw.info.base_dn
        domain_sid = self.gw.info.domain_sid
        sids: dict[str, tuple[str, bool]] = dict(PRIVILEGED_BUILTIN_SIDS)
        if domain_sid:
            for rid, meta in PRIVILEGED_DOMAIN_RIDS.items():
                sids[f"{domain_sid}-{rid}"] = meta
        clauses = [Equals("objectSid", str_to_sid(s)) for s in sids]
        clauses += [Equals("sAMAccountName", n) for n in self.extra_names if n]
        if base and clauses:
            for e in self.gw.search(base, And(Equals("objectCategory", "group"), Or(*clauses)),
                                    ["cn", "objectSid", "sAMAccountName"]):
                sid = sid_to_str(e.first("objectSid")) if e.first("objectSid") else ""
                meta = sids.get(sid)
                if meta is None:
                    meta = (e.str("sAMAccountName"), False)
                groups[normalize_dn(e.dn)] = PrivilegedGroup(e.dn, e.str("cn") or rdn_value(e.dn), sid, meta[0], meta[1])
        self._groups = groups
        return groups

    def invalidate(self):
        self._groups = None

    def get(self, group_dn: str) -> PrivilegedGroup | None:
        return self.load().get(normalize_dn(group_dn))

    def is_privileged(self, group_dn: str) -> bool:
        return self.get(group_dn) is not None

    def nested_into_privileged(self, group_dn: str) -> list[PrivilegedGroup]:
        """Privileged groups that *group_dn* belongs to transitively (members inherit their rights)."""
        priv = self.load()
        if not priv:
            return []
        out = []
        for e in self.gw.search(self.gw.info.base_dn, And(Equals("objectCategory", "group"), in_chain("member", group_dn)),
                                ["cn"]):
            g = priv.get(normalize_dn(e.dn))
            if g:
                out.append(g)
        return out

    def privileged_memberships(self, member_dn: str) -> list[PrivilegedGroup]:
        """Privileged groups that *member_dn* is a (direct or nested) member of."""
        return self.nested_into_privileged(member_dn)

    def classify_group(self, group_dn: str) -> tuple[bool, str, bool]:
        """(privileged, reason, critical)."""
        g = self.get(group_dn)
        if g:
            return True, f"Привилегированная группа ({g.well_known})", g.critical
        nested = self.nested_into_privileged(group_dn)
        if nested:
            names = ", ".join(sorted({n.name for n in nested}))
            return True, f"Вложена в привилегированные группы: {names}", any(n.critical for n in nested)
        return False, "", False


class PermissionChecker:
    def __init__(self, gateway: DirectoryGateway):
        self.gw = gateway

    def effective_attributes(self, dn: str) -> set[str]:
        e = self.gw.get(dn, ["allowedAttributesEffective"])
        if e is None:
            from ..core.errors import ObjectNotFoundError
            raise ObjectNotFoundError(f"Объект не найден: {dn}")
        return {str(v).lower() for v in e.values("allowedAttributesEffective")}

    def effective_child_classes(self, dn: str) -> set[str]:
        e = self.gw.get(dn, ["allowedChildClassesEffective"])
        if e is None:
            from ..core.errors import ObjectNotFoundError
            raise ObjectNotFoundError(f"Контейнер не найден: {dn}")
        return {str(v).lower() for v in e.values("allowedChildClassesEffective")}

    def missing_attributes(self, dn: str, attributes: list[str]) -> list[str]:
        allowed = self.effective_attributes(dn)
        return [a for a in attributes if a.lower() not in allowed]

    def require_write(self, dn: str, attributes: list[str], action: str) -> None:
        missing = self.missing_attributes(dn, attributes)
        if missing:
            raise PermissionDeniedError(
                f"Нет прав на «{action}»: запись атрибутов {', '.join(missing)} не разрешена для текущей учётной записи",
                details=f"Объект: {dn}. Проверено по allowedAttributesEffective.",
                hint="Запросите делегирование прав на OU у администратора домена.")

    def require_create(self, parent_dn: str, object_class: str, action: str) -> None:
        if object_class.lower() not in self.effective_child_classes(parent_dn):
            raise PermissionDeniedError(
                f"Нет прав на «{action}»: создание объектов класса {object_class} в {parent_dn} не разрешено",
                details="Проверено по allowedChildClassesEffective.",
                hint="Выберите другой контейнер или запросите делегирование прав.")

    def can_write(self, dn: str, attributes: list[str]) -> bool:
        try:
            return not self.missing_attributes(dn, attributes)
        except Exception:
            return False

    def rights_summary(self, registry: PrivilegedGroupRegistry | None = None) -> RightsSummary:
        info = self.gw.info
        summary = RightsSummary(identity=info.bound_identity)
        try:
            self.gw.root_dse()
            summary.can_read_directory = bool(info.base_dn and self.gw.get(info.base_dn, ["distinguishedName"]))
        except Exception as exc:  # noqa: BLE001 - report, don't fail
            summary.notes.append(f"Чтение каталога: ошибка ({exc})")
        user_dn = info.bound_user_dn or self._resolve_identity_dn(info.bound_identity)
        summary.user_dn = user_dn
        if user_dn:
            try:
                e = self.gw.get(user_dn, ["tokenGroups"])
                sids = [sid_to_str(s) for s in (e.values("tokenGroups") if e else [])]
                summary.groups = self._resolve_sids(sids)
                if registry is not None:
                    priv = registry.load()
                    priv_by_sid = {g.sid: g for g in priv.values()}
                    summary.privileged_groups = sorted({priv_by_sid[s].name for s in sids if s in priv_by_sid})
            except Exception as exc:  # noqa: BLE001
                summary.notes.append(f"Членство в группах (tokenGroups) не прочитано: {exc}")
        else:
            summary.notes.append("Не удалось определить DN учётной записи подключения (Kerberos/WhoAmI)")
        base = info.base_dn
        if base:
            users_container = f"CN=Users,{base}"
            try:
                classes = self.effective_child_classes(users_container)
                summary.create_user_in_default = "user" in classes
                summary.create_group_in_default = "group" in classes
            except Exception:
                summary.notes.append("Права на создание объектов в CN=Users не определены")
        summary.notes.append("Права на изменение конкретных объектов проверяются перед каждой операцией "
                             "(allowedAttributesEffective); итоговое решение принимает контроллер домена.")
        return summary

    def _resolve_identity_dn(self, identity: str) -> str:
        ident = (identity or "").strip()
        if ident.lower().startswith("dn:"):
            return ident[3:]
        if ident.lower().startswith("u:"):
            ident = ident[2:]
        sam = ident.split("\\", 1)[1] if "\\" in ident else ident
        if "@" in sam:
            flt = Equals("userPrincipalName", sam)
        else:
            flt = Equals("sAMAccountName", sam)
        if not sam or not self.gw.info.base_dn:
            return ""
        items = self.gw.search_list(self.gw.info.base_dn, And(Equals("objectClass", "user"), flt), ["cn"], size_limit=2)
        return items[0].dn if len(items) == 1 else ""

    def _resolve_sids(self, sids: list[str]) -> list[str]:
        names = []
        base = self.gw.info.base_dn
        chunk = 50
        for i in range(0, len(sids), chunk):
            part = sids[i:i + chunk]
            if not part:
                continue
            flt = Or(*[Equals("objectSid", str_to_sid(s)) for s in part])
            for e in self.gw.search(base, flt, ["cn"]):
                names.append(e.str("cn") or rdn_value(e.dn))
        resolved = len(names)
        if resolved < len(sids):
            names.append(f"(+{len(sids) - resolved} SID вне домена/встроенных)")
        return sorted(names)


def ensure_not_privileged(registry: PrivilegedGroupRegistry, group_dn: str, confirmed: bool, action: str) -> None:
    """Raise unless the caller obtained the separate confirmation required for privileged groups."""
    privileged, reason, _critical = registry.classify_group(group_dn)
    if privileged and not confirmed:
        raise ProtectedObjectError(
            f"«{action}»: изменение состава привилегированной группы требует отдельного подтверждения",
            details=reason, hint="Подтвердите операцию в отдельном диалоге с вводом имени группы.")


def rid_of(sid: str) -> int | None:
    return sid_rid(sid)
