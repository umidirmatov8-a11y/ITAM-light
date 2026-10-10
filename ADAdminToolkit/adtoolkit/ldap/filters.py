"""LDAP search filters (RFC 4515) with Active Directory extensions.

* Filters are built as a small AST (:class:`FilterNode`); every assertion value is escaped when the
  filter is rendered, so user input can never change the structure of a filter.
* :func:`parse_filter` validates filters typed by the administrator in LDAP Explorer and is also used by the
  in-memory directory (demo / test mode) to evaluate filters.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

MATCH_BIT_AND = "1.2.840.113556.1.4.803"
MATCH_BIT_OR = "1.2.840.113556.1.4.804"
MATCH_IN_CHAIN = "1.2.840.113556.1.4.1941"

MAX_FILTER_LENGTH = 32 * 1024
MAX_FILTER_DEPTH = 64

_ATTR_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9-]*|\d+(?:\.\d+)+)(?:;[A-Za-z0-9-]+(?:=[0-9*-]+)?)*$")
_RULE_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9-]*|\d+(?:\.\d+)+)$")


class FilterSyntaxError(ValueError):
    def __init__(self, message: str, position: int | None = None):
        self.position = position
        if position is not None:
            message = f"{message} (позиция {position + 1})"
        super().__init__(message)


# ----------------------------------------------------------------------------------------------------------------
# Escaping
# ----------------------------------------------------------------------------------------------------------------

_ESCAPE_MAP = {"\\": r"\5c", "*": r"\2a", "(": r"\28", ")": r"\29", "\x00": r"\00"}


def escape_filter_value(value) -> str:
    """Escape an assertion value for use inside a filter (RFC 4515 section 3).

    ``bytes`` are fully hex-escaped (used for objectSid / objectGUID searches).
    """
    if isinstance(value, (bytes, bytearray)):
        return "".join(f"\\{b:02x}" for b in value)
    if isinstance(value, bool):
        value = "TRUE" if value else "FALSE"
    return "".join(_ESCAPE_MAP.get(ch, ch) for ch in str(value))


def unescape_filter_bytes(text: str, position: int = 0) -> bytes:
    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            pair = text[i + 1:i + 3]
            if len(pair) != 2 or not all(c in "0123456789abcdefABCDEF" for c in pair):
                raise FilterSyntaxError("Неверная escape-последовательность в значении фильтра", position + i)
            out.append(int(pair, 16))
            i += 3
        else:
            out.extend(ch.encode("utf-8"))
            i += 1
    return bytes(out)


def unescape_filter_value(text: str, position: int = 0) -> str:
    raw = unescape_filter_bytes(text, position)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # binary assertion (e.g. objectSid); keep a lossless representation
        return raw.decode("latin-1")


def validate_attribute_name(name: str) -> str:
    name = (name or "").strip()
    if not _ATTR_RE.match(name):
        raise ValueError(f"Недопустимое имя атрибута LDAP: {name!r}")
    return name


# ----------------------------------------------------------------------------------------------------------------
# AST
# ----------------------------------------------------------------------------------------------------------------

class FilterNode:
    def to_ldap(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def __str__(self) -> str:
        return self.to_ldap()

    def __and__(self, other: "FilterNode") -> "And":
        return And(self, other)

    def __or__(self, other: "FilterNode") -> "Or":
        return Or(self, other)

    def __invert__(self) -> "Not":
        return Not(self)


@dataclass(frozen=True)
class _AttrNode(FilterNode):
    attr: str

    def __post_init__(self):
        validate_attribute_name(self.attr)


@dataclass(frozen=True)
class Equals(_AttrNode):
    value: object = ""

    def to_ldap(self) -> str:
        return f"({self.attr}={escape_filter_value(self.value)})"


@dataclass(frozen=True)
class Present(_AttrNode):
    def to_ldap(self) -> str:
        return f"({self.attr}=*)"


@dataclass(frozen=True)
class GreaterOrEqual(_AttrNode):
    value: object = ""

    def to_ldap(self) -> str:
        return f"({self.attr}>={escape_filter_value(self.value)})"


@dataclass(frozen=True)
class LessOrEqual(_AttrNode):
    value: object = ""

    def to_ldap(self) -> str:
        return f"({self.attr}<={escape_filter_value(self.value)})"


@dataclass(frozen=True)
class Approx(_AttrNode):
    value: object = ""

    def to_ldap(self) -> str:
        return f"({self.attr}~={escape_filter_value(self.value)})"


@dataclass(frozen=True)
class Substring(_AttrNode):
    initial: str | None = None
    any: tuple[str, ...] = ()
    final: str | None = None

    def __post_init__(self):
        super().__post_init__()
        if not self.initial and not self.final and not any(self.any):
            raise ValueError("Подстрочный фильтр должен содержать хотя бы один фрагмент")

    def to_ldap(self) -> str:
        parts = [escape_filter_value(self.initial) if self.initial else ""]
        parts += [escape_filter_value(a) for a in self.any if a]
        parts.append(escape_filter_value(self.final) if self.final else "")
        return f"({self.attr}={'*'.join(parts)})"


@dataclass(frozen=True)
class Extensible(FilterNode):
    attr: str | None
    rule: str | None
    value: object
    dn_attributes: bool = False

    def __post_init__(self):
        if self.attr:
            validate_attribute_name(self.attr)
        if self.rule and not _RULE_RE.match(self.rule):
            raise ValueError(f"Недопустимое правило сопоставления: {self.rule!r}")
        if not self.attr and not self.rule:
            raise ValueError("Расширенный фильтр требует атрибут или правило сопоставления")

    def to_ldap(self) -> str:
        s = self.attr or ""
        if self.dn_attributes:
            s += ":dn"
        if self.rule:
            s += f":{self.rule}"
        return f"({s}:={escape_filter_value(self.value)})"


@dataclass(frozen=True)
class And(FilterNode):
    children: tuple[FilterNode, ...] = field(default_factory=tuple)

    def __init__(self, *children: FilterNode):
        flat: list[FilterNode] = []
        for c in children:
            if c is None:
                continue
            if isinstance(c, And):
                flat.extend(c.children)
            else:
                flat.append(c)
        if not flat:
            raise ValueError("Пустой фильтр AND")
        object.__setattr__(self, "children", tuple(flat))

    def to_ldap(self) -> str:
        if len(self.children) == 1:
            return self.children[0].to_ldap()
        return "(&" + "".join(c.to_ldap() for c in self.children) + ")"


@dataclass(frozen=True)
class Or(FilterNode):
    children: tuple[FilterNode, ...] = field(default_factory=tuple)

    def __init__(self, *children: FilterNode):
        flat: list[FilterNode] = []
        for c in children:
            if c is None:
                continue
            if isinstance(c, Or):
                flat.extend(c.children)
            else:
                flat.append(c)
        if not flat:
            raise ValueError("Пустой фильтр OR")
        object.__setattr__(self, "children", tuple(flat))

    def to_ldap(self) -> str:
        if len(self.children) == 1:
            return self.children[0].to_ldap()
        return "(|" + "".join(c.to_ldap() for c in self.children) + ")"


@dataclass(frozen=True)
class Not(FilterNode):
    child: FilterNode

    def to_ldap(self) -> str:
        return f"(!{self.child.to_ldap()})"


# ----------------------------------------------------------------------------------------------------------------
# Convenience builders
# ----------------------------------------------------------------------------------------------------------------

def eq(attr: str, value) -> Equals:
    return Equals(attr, value)


def present(attr: str) -> Present:
    return Present(attr)


def ge(attr: str, value) -> GreaterOrEqual:
    return GreaterOrEqual(attr, value)


def le(attr: str, value) -> LessOrEqual:
    return LessOrEqual(attr, value)


def contains(attr: str, text: str) -> FilterNode:
    text = (text or "").strip()
    return Present(attr) if not text else Substring(attr, any=(text,))


def starts_with(attr: str, text: str) -> FilterNode:
    text = (text or "").strip()
    return Present(attr) if not text else Substring(attr, initial=text)


def ends_with(attr: str, text: str) -> FilterNode:
    text = (text or "").strip()
    return Present(attr) if not text else Substring(attr, final=text)


def bit_and(attr: str, mask: int) -> Extensible:
    return Extensible(attr, MATCH_BIT_AND, int(mask))


def bit_or(attr: str, mask: int) -> Extensible:
    return Extensible(attr, MATCH_BIT_OR, int(mask))


def in_chain(attr: str, dn: str) -> Extensible:
    """LDAP_MATCHING_RULE_IN_CHAIN — transitive evaluation of linked attributes (member / memberOf)."""
    return Extensible(attr, MATCH_IN_CHAIN, dn)


def any_of(attr: str, values: Iterable) -> FilterNode:
    return Or(*[Equals(attr, v) for v in values])


def text_search(attrs: Iterable[str], text: str) -> FilterNode | None:
    """OR of substring matches over several attributes; ``None`` for empty text."""
    text = (text or "").strip()
    if not text:
        return None
    return Or(*[Substring(a, any=(text,)) for a in attrs])


def all_of(*nodes: FilterNode | None) -> FilterNode:
    return And(*[n for n in nodes if n is not None])


# ----------------------------------------------------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------------------------------------------------

class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.depth = 0

    def error(self, message: str):
        raise FilterSyntaxError(message, self.pos)

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def expect(self, ch: str):
        if self.peek() != ch:
            self.error(f"Ожидался символ '{ch}'")
        self.pos += 1

    def skip_ws(self):
        while self.peek() and self.peek() in " \t\r\n":
            self.pos += 1

    def parse(self) -> FilterNode:
        self.skip_ws()
        node = self.parse_filter()
        self.skip_ws()
        if self.pos != len(self.text):
            self.error("Лишние символы после конца фильтра")
        return node

    def parse_filter(self) -> FilterNode:
        self.depth += 1
        if self.depth > MAX_FILTER_DEPTH:
            self.error("Слишком глубокая вложенность фильтра")
        self.skip_ws()
        self.expect("(")
        self.skip_ws()
        ch = self.peek()
        if ch == "&":
            self.pos += 1
            node: FilterNode = And(*self.parse_list())
        elif ch == "|":
            self.pos += 1
            node = Or(*self.parse_list())
        elif ch == "!":
            self.pos += 1
            node = Not(self.parse_filter())
        elif ch == "":
            self.error("Неожиданный конец фильтра")
        else:
            node = self.parse_item()
        self.skip_ws()
        self.expect(")")
        self.depth -= 1
        return node

    def parse_list(self) -> list[FilterNode]:
        items = []
        self.skip_ws()
        while self.peek() == "(":
            items.append(self.parse_filter())
            self.skip_ws()
        if not items:
            self.error("Логический оператор должен содержать хотя бы один фильтр")
        return items

    def read_value(self) -> str:
        start = self.pos
        while True:
            ch = self.peek()
            if ch == "":
                self.error("Неожиданный конец фильтра в значении")
            if ch == ")":
                break
            if ch == "(":
                self.error("Неэкранированная скобка в значении (используйте \\28)")
            if ch == "\\":
                self.pos += 3
                continue
            self.pos += 1
        return self.text[start:self.pos]

    def parse_item(self) -> FilterNode:
        start = self.pos
        while self.peek() and self.peek() not in "=~<>:()":
            self.pos += 1
        attr = self.text[start:self.pos].strip()
        op = self.peek()
        try:
            if op == ":":
                return self.parse_extensible(attr, start)
            if op == "~":
                self.pos += 1
                self.expect("=")
                vstart = self.pos
                return Approx(validate_attribute_name(attr), unescape_filter_value(self.read_value(), vstart))
            if op in "<>" and op:
                self.pos += 1
                self.expect("=")
                vstart = self.pos
                value = unescape_filter_value(self.read_value(), vstart)
                cls = GreaterOrEqual if op == ">" else LessOrEqual
                return cls(validate_attribute_name(attr), value)
            if op == "=":
                self.pos += 1
                vstart = self.pos
                raw = self.read_value()
                validate_attribute_name(attr)
                if raw == "*":
                    return Present(attr)
                if "*" in raw:
                    pieces = raw.split("*")
                    initial = unescape_filter_value(pieces[0], vstart) if pieces[0] else None
                    final = unescape_filter_value(pieces[-1], vstart) if pieces[-1] else None
                    middle = tuple(unescape_filter_value(p, vstart) for p in pieces[1:-1] if p)
                    return Substring(attr, initial=initial, any=middle, final=final)
                return Equals(attr, unescape_filter_value(raw, vstart))
        except ValueError as exc:
            if isinstance(exc, FilterSyntaxError):
                raise
            raise FilterSyntaxError(str(exc), start) from None
        self.error("Ожидался оператор сравнения (=, >=, <=, ~=, :=)")
        raise AssertionError  # unreachable

    def parse_extensible(self, attr: str, start: int) -> FilterNode:
        # attr[:dn][:rule]:=value   or   [:dn]:rule:=value
        head_end = self.text.find(":=", self.pos)
        if head_end < 0:
            self.error("Ожидалось ':=' в расширенном фильтре")
        head = self.text[start:head_end]
        parts = head.split(":")
        attr_part = parts[0].strip() or None
        dn = False
        rule = None
        for p in parts[1:]:
            p = p.strip()
            if p.lower() == "dn":
                dn = True
            elif p:
                rule = p
        self.pos = head_end + 2
        vstart = self.pos
        value = unescape_filter_value(self.read_value(), vstart)
        try:
            return Extensible(attr_part, rule, value, dn)
        except ValueError as exc:
            raise FilterSyntaxError(str(exc), start) from None


def parse_filter(text: str) -> FilterNode:
    """Parse and validate an LDAP filter string. Raises :class:`FilterSyntaxError`."""
    if text is None:
        raise FilterSyntaxError("Пустой фильтр")
    text = text.strip()
    if not text:
        raise FilterSyntaxError("Пустой фильтр")
    if len(text) > MAX_FILTER_LENGTH:
        raise FilterSyntaxError("Фильтр слишком длинный")
    if not text.startswith("("):
        text = f"({text})"
    return _Parser(text).parse()


def normalize_filter(text: str) -> str:
    """Validate a filter and return its canonical, correctly escaped form."""
    return parse_filter(text).to_ldap()


def iter_attributes(node: FilterNode) -> set[str]:
    """Attribute names referenced by a filter (used to warn about unindexed / unknown attributes)."""
    out: set[str] = set()
    if isinstance(node, (And, Or)):
        for c in node.children:
            out |= iter_attributes(c)
    elif isinstance(node, Not):
        out |= iter_attributes(node.child)
    elif isinstance(node, Extensible):
        if node.attr:
            out.add(node.attr)
    elif isinstance(node, _AttrNode):
        out.add(node.attr)
    return out
