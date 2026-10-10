"""LDAP Explorer: read-only custom queries, attribute viewer, filter builder, history and favourites."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.cancel import CancelToken
from ..core.errors import ValidationError
from ..ldap.dn import DNSyntaxError, validate_dn
from ..ldap.filters import (And, Equals, FilterNode, FilterSyntaxError, GreaterOrEqual, LessOrEqual, Not, Or, Present,
                            Substring, bit_and, bit_or, in_chain, parse_filter, validate_attribute_name)
from ..ldap.gateway import Entry, Scope, SearchStats
from . import ad_queries as Q
from .context import ServiceContext

OBJECT_TYPES = {
    "Любой": None,
    "Пользователь": Q.IS_USER,
    "Компьютер": Q.IS_COMPUTER,
    "Группа": Q.IS_GROUP,
    "OU": Q.IS_OU,
    "Контакт": Equals("objectClass", "contact"),
}

OPERATORS = {
    "равно": "eq", "содержит": "contains", "начинается с": "starts", "заканчивается на": "ends",
    "присутствует": "present", "отсутствует": "absent", "≥": "ge", "≤": "le",
    "битовое И (803)": "bitand", "битовое ИЛИ (804)": "bitor", "член группы (рекурсивно, 1941)": "inchain",
    "не равно": "ne",
}

CONSTRUCTED_EXTRA = ["msDS-User-Account-Control-Computed", "msDS-UserPasswordExpiryTimeComputed", "allowedAttributesEffective",
                     "allowedChildClassesEffective", "canonicalName", "createTimeStamp", "modifyTimeStamp", "memberOf"]


@dataclass
class Condition:
    attribute: str
    operator: str          # key from OPERATORS values
    value: str = ""


@dataclass
class ExplorerResult:
    entries: list[Entry]
    stats: SearchStats
    filter_text: str
    base_dn: str
    scope: str
    attributes: list[str] = field(default_factory=list)


def condition_node(c: Condition) -> FilterNode:
    attr = validate_attribute_name(c.attribute)
    v = c.value
    op = c.operator
    if op in ("eq", "ne", "contains", "starts", "ends", "ge", "le", "bitand", "bitor", "inchain") and v == "":
        raise ValidationError(f"Для условия «{attr}» требуется значение")
    if op == "eq":
        return Equals(attr, v)
    if op == "ne":
        return Not(Equals(attr, v))
    if op == "contains":
        return Substring(attr, any=(v,))
    if op == "starts":
        return Substring(attr, initial=v)
    if op == "ends":
        return Substring(attr, final=v)
    if op == "present":
        return Present(attr)
    if op == "absent":
        return Not(Present(attr))
    if op == "ge":
        return GreaterOrEqual(attr, v)
    if op == "le":
        return LessOrEqual(attr, v)
    if op in ("bitand", "bitor"):
        try:
            mask = int(v, 0)
        except ValueError:
            raise ValidationError(f"Маска должна быть числом: {v}") from None
        return bit_and(attr, mask) if op == "bitand" else bit_or(attr, mask)
    if op == "inchain":
        try:
            validate_dn(v)
        except DNSyntaxError as exc:
            raise ValidationError(f"Для рекурсивного членства укажите DN группы: {exc}") from None
        return in_chain(attr, v)
    raise ValidationError(f"Неизвестный оператор: {op}")


def build_filter(object_type: str, conditions: list[Condition], combine: str = "AND") -> FilterNode:
    nodes = [condition_node(c) for c in conditions if c.attribute.strip()]
    type_node = OBJECT_TYPES.get(object_type)
    cond: FilterNode | None = None
    if nodes:
        cond = And(*nodes) if combine.upper() == "AND" else Or(*nodes)
    if type_node is None and cond is None:
        return Present("objectClass")
    if type_node is None:
        return cond
    if cond is None:
        return type_node
    return And(type_node, cond)


def validate_attributes(text: str) -> list[str]:
    attrs = [a.strip() for a in (text or "").replace(";", ",").split(",") if a.strip()]
    out = []
    for a in attrs:
        if a in ("*", "1.1"):
            out.append(a)
            continue
        try:
            out.append(validate_attribute_name(a))
        except ValueError as exc:
            raise ValidationError(str(exc)) from None
    return out or ["*"]


class ExplorerService:
    """Read-only by design: it exposes no write operations at all."""

    def __init__(self, ctx: ServiceContext, db=None):
        self.ctx = ctx
        self.gw = ctx.gateway
        self.db = db

    def run(self, base_dn: str, scope: str, filter_text: str, attributes: list[str], limit: int = 1000,
            cancel: CancelToken | None = None) -> ExplorerResult:
        base_dn = (base_dn or "").strip() or self.ctx.base_dn
        try:
            validate_dn(base_dn) if base_dn else None
        except DNSyntaxError as exc:
            raise ValidationError(f"Некорректный Base DN: {exc}") from None
        try:
            node = parse_filter(filter_text)
        except FilterSyntaxError as exc:
            raise ValidationError(f"Синтаксическая ошибка фильтра: {exc}") from None
        sc = {"base": Scope.BASE, "onelevel": Scope.ONELEVEL, "subtree": Scope.SUBTREE}.get(scope, Scope.SUBTREE)
        stats = SearchStats()
        entries: list[Entry] = []
        error = None
        try:
            for e in self.gw.search(base_dn, node, attributes, sc, cancel=cancel, stats=stats):
                entries.append(e)
                if limit and len(entries) >= limit:
                    stats.truncated = True
                    break
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            if self.db is not None:
                self.db.add_query_history(base_dn, sc.value, node.to_ldap(), attributes,
                                          None if error else len(entries), error)
        return ExplorerResult(entries, stats, node.to_ldap(), base_dn, sc.value, attributes)

    def object_attributes(self, dn: str) -> Entry:
        try:
            validate_dn(dn)
        except DNSyntaxError as exc:
            raise ValidationError(str(exc)) from None
        e = self.gw.get(dn, ["*"] + CONSTRUCTED_EXTRA)
        if e is None:
            from ..core.errors import ObjectNotFoundError
            raise ObjectNotFoundError(f"Объект не найден: {dn}")
        return e

    def children(self, dn: str, cancel: CancelToken | None = None) -> list[Entry]:
        return self.gw.search_list(dn, "(objectClass=*)", ["objectClass", "name"], Scope.ONELEVEL, cancel=cancel)

    @staticmethod
    def examples() -> dict[str, str]:
        return {name: node.to_ldap() for name, node in Q.EXAMPLE_FILTERS.items()}
