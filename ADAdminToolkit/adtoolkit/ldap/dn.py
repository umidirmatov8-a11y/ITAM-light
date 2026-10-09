"""Distinguished name helpers (RFC 4514) — parsing, escaping, comparison and display."""
from __future__ import annotations

import re

_DN_SPECIAL = set(',+"\\<>;=')
_ATTR_TYPE_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9-]*|\d+(?:\.\d+)+)$")


class DNSyntaxError(ValueError):
    pass


def escape_dn_value(value: str) -> str:
    """Escape an RDN attribute value (RFC 4514 section 2.4, plus '=' which AD also escapes)."""
    value = str(value)
    if value == "":
        return ""
    out = []
    for i, ch in enumerate(value):
        if ch in _DN_SPECIAL:
            out.append("\\" + ch)
        elif ch == "\x00":
            out.append("\\00")
        elif ch == "\n":
            out.append("\\0A")
        elif ch == "\r":
            out.append("\\0D")
        elif ch == "#" and i == 0:
            out.append("\\#")
        elif ch == " " and (i == 0 or i == len(value) - 1):
            out.append("\\ ")
        else:
            out.append(ch)
    return "".join(out)


RDN = list[tuple[str, str]]


def parse_dn(dn: str) -> list[RDN]:
    """Split a DN into RDNs; each RDN is a list of (type, unescaped value) pairs (multi-valued RDNs use '+')."""
    if dn is None:
        raise DNSyntaxError("Пустой DN")
    s = dn.strip()
    if not s:
        return []
    rdns: list[RDN] = []
    current: RDN = []
    i = 0
    n = len(s)
    while i < n:
        # attribute type
        while i < n and s[i] == " ":
            i += 1
        start = i
        while i < n and s[i] != "=":
            if s[i] in ",+;":
                raise DNSyntaxError(f"Некорректный DN (ожидался '='): {dn}")
            i += 1
        if i >= n:
            raise DNSyntaxError(f"Некорректный DN (нет '='): {dn}")
        attr = s[start:i].strip()
        if not _ATTR_TYPE_RE.match(attr):
            raise DNSyntaxError(f"Некорректный тип атрибута в DN: {attr!r}")
        i += 1  # skip '='
        while i < n and s[i] == " ":
            i += 1
        buf = bytearray()
        trailing_unescaped_spaces = 0
        while i < n and s[i] not in ",+;":
            ch = s[i]
            if ch == "\\":
                if i + 1 >= n:
                    raise DNSyntaxError(f"Незавершённая escape-последовательность в DN: {dn}")
                nxt = s[i + 1]
                if i + 2 < n + 1 and re.match(r"[0-9A-Fa-f]{2}", s[i + 1:i + 3] or ""):
                    buf.append(int(s[i + 1:i + 3], 16))
                    i += 3
                else:
                    buf.extend(nxt.encode("utf-8"))
                    i += 2
                trailing_unescaped_spaces = 0
                continue
            if ch == '"':
                raise DNSyntaxError(f"Неэкранированная кавычка в DN: {dn}")
            buf.extend(ch.encode("utf-8"))
            trailing_unescaped_spaces = trailing_unescaped_spaces + 1 if ch == " " else 0
            i += 1
        if trailing_unescaped_spaces:
            del buf[-trailing_unescaped_spaces:]
        try:
            value = buf.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DNSyntaxError(f"Некорректная кодировка значения в DN: {dn}") from exc
        current.append((attr, value))
        if i < n and s[i] == "+":
            i += 1
            continue
        rdns.append(current)
        current = []
        if i < n:  # ',' or ';'
            i += 1
            if i >= n:
                raise DNSyntaxError(f"DN заканчивается разделителем: {dn}")
    if current:
        rdns.append(current)
    return rdns


def build_dn(rdns: list[RDN]) -> str:
    return ",".join("+".join(f"{t}={escape_dn_value(v)}" for t, v in rdn) for rdn in rdns)


def make_rdn(attr: str, value: str) -> str:
    if not _ATTR_TYPE_RE.match(attr):
        raise DNSyntaxError(f"Некорректный тип атрибута: {attr!r}")
    if not str(value).strip():
        raise DNSyntaxError("Пустое значение RDN")
    return f"{attr}={escape_dn_value(value)}"


def child_dn(parent: str, attr: str, value: str) -> str:
    rdn = make_rdn(attr, value)
    return f"{rdn},{parent}" if parent else rdn


def first_rdn(dn: str) -> str:
    rdns = parse_dn(dn)
    if not rdns:
        return ""
    return "+".join(f"{t}={escape_dn_value(v)}" for t, v in rdns[0])


def rdn_value(dn: str) -> str:
    """Unescaped value of the first RDN — e.g. the CN of a user."""
    try:
        rdns = parse_dn(dn)
    except DNSyntaxError:
        return dn
    return rdns[0][0][1] if rdns else ""


def parent_dn(dn: str) -> str:
    rdns = parse_dn(dn)
    return build_dn(rdns[1:])


def normalize_dn(dn: str) -> str:
    """Canonical form for comparisons: lower-case types, case-folded values, canonical escaping."""
    try:
        rdns = parse_dn(dn)
    except DNSyntaxError:
        return (dn or "").strip().casefold()
    return ",".join(
        "+".join(sorted(f"{t.lower()}={escape_dn_value(v.casefold())}" for t, v in rdn)) for rdn in rdns
    )


def dn_equal(a: str, b: str) -> bool:
    return normalize_dn(a) == normalize_dn(b)


def is_descendant(dn: str, ancestor: str, *, include_self: bool = False) -> bool:
    nd, na = normalize_dn(dn), normalize_dn(ancestor)
    if not na:
        return True
    if nd == na:
        return include_self
    return nd.endswith("," + na)


def domain_components(dn: str) -> list[str]:
    try:
        return [v for rdn in parse_dn(dn) for t, v in rdn if t.lower() == "dc"]
    except DNSyntaxError:
        return []


def dn_to_dns_domain(dn: str) -> str:
    return ".".join(domain_components(dn))


def dns_domain_to_dn(domain: str) -> str:
    domain = (domain or "").strip().strip(".")
    if not domain:
        raise DNSyntaxError("Пустое DNS-имя домена")
    labels = domain.split(".")
    for label in labels:
        if not re.match(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$", label):
            raise DNSyntaxError(f"Некорректная метка DNS-имени: {label!r}")
    return ",".join(f"DC={label}" for label in labels)


def canonical_name(dn: str) -> str:
    """'OU=Sales,OU=Company,DC=corp,DC=local' -> 'corp.local/Company/Sales'."""
    try:
        rdns = parse_dn(dn)
    except DNSyntaxError:
        return dn
    dcs = [v for rdn in rdns for t, v in rdn if t.lower() == "dc"]
    rest = [rdn[0][1] for rdn in rdns if rdn[0][0].lower() != "dc"]
    return "/".join([".".join(dcs)] + list(reversed(rest)))


def container_path(dn: str) -> str:
    """Display path of the container holding *dn* (without the domain part)."""
    try:
        rdns = parse_dn(dn)[1:]
    except DNSyntaxError:
        return ""
    rest = [rdn[0][1] for rdn in rdns if rdn[0][0].lower() != "dc"]
    return "/".join(reversed(rest)) or "(корень домена)"


def validate_dn(dn: str) -> str:
    parse_dn(dn)
    if not dn.strip():
        raise DNSyntaxError("Пустой DN")
    return dn.strip()
