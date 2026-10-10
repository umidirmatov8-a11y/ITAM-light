import pytest

from adtoolkit.ldap.filters import (And, Equals, FilterSyntaxError, Not, Or, Present, Substring, bit_and, contains,
                                    escape_filter_value, in_chain, normalize_filter, parse_filter, unescape_filter_value)
from adtoolkit.services import ad_queries as Q


@pytest.mark.parametrize("raw,expected", [
    ("Parens R Us (for all your parenthetical needs)", r"Parens R Us \28for all your parenthetical needs\29"),
    ("*", r"\2a"),
    ("C:\\MyFile", r"C:\5cMyFile"),
    ("NUL\x00here", r"NUL\00here"),
    ("Lučić", "Lučić"),
    ("Иванов (ИТ)*", r"Иванов \28ИТ\29\2a"),
])
def test_escape_rfc4515_vectors(raw, expected):
    assert escape_filter_value(raw) == expected


def test_escape_bytes_is_fully_hex_encoded():
    assert escape_filter_value(b"\x01\x05\xff") == r"\01\05\ff"


def test_injection_attempt_stays_a_literal_value():
    payload = "*)(objectClass=*))(|(cn=*"
    flt = And(Equals("objectCategory", "person"), Equals("sAMAccountName", payload)).to_ldap()
    assert flt == r"(&(objectCategory=person)(sAMAccountName=\2a\29\28objectClass=\2a\29\29\28|\28cn=\2a))"
    node = parse_filter(flt)
    assert isinstance(node, And) and len(node.children) == 2
    assert node.children[1].value == payload


def test_substring_builders():
    assert contains("cn", "abc").to_ldap() == "(cn=*abc*)"
    assert Substring("cn", initial="a*b").to_ldap() == r"(cn=a\2ab*)"
    assert Substring("cn", final="z").to_ldap() == "(cn=*z)"
    assert contains("cn", "").to_ldap() == "(cn=*)"
    with pytest.raises(ValueError):
        Substring("cn")


def test_ad_matching_rules():
    assert bit_and("userAccountControl", 2).to_ldap() == "(userAccountControl:1.2.840.113556.1.4.803:=2)"
    assert in_chain("memberOf", "CN=G (1),DC=x").to_ldap() == r"(memberOf:1.2.840.113556.1.4.1941:=CN=G \281\29,DC=x)"


def test_predefined_example_filters():
    assert Q.USERS_DISABLED.to_ldap() == "(&(objectCategory=person)(objectClass=user)(userAccountControl:1.2.840.113556.1.4.803:=2))"
    assert Q.USERS_LOCKED_CANDIDATES.to_ldap() == "(&(objectCategory=person)(objectClass=user)(lockoutTime>=1))"
    assert Q.IS_COMPUTER.to_ldap() == "(objectCategory=computer)"
    assert Q.COMPUTERS_DISABLED.to_ldap() == "(&(objectCategory=computer)(userAccountControl:1.2.840.113556.1.4.803:=2))"
    for f in Q.EXAMPLE_FILTERS.values():
        assert parse_filter(f.to_ldap()).to_ldap() == f.to_ldap()


def test_attribute_names_are_validated():
    for bad in ("cn)(x", "", "1a", "a b", "cn=", "cn*"):
        with pytest.raises(ValueError):
            Equals(bad, "x")
    Equals("msDS-User-Account-Control-Computed", 1)
    Equals("1.2.840.113556.1.4.656", "x")


@pytest.mark.parametrize("text", [
    "(cn=a", "(&)", "cn=a)", "(cn=(a))", r"(cn=\zz)", "(!(cn=a)(cn=b))", "", "   ", "(cn~a)", "((cn=a))",
])
def test_parser_rejects_invalid(text):
    with pytest.raises(FilterSyntaxError):
        parse_filter(text)


def test_parser_reports_position():
    with pytest.raises(FilterSyntaxError) as exc:
        parse_filter("(&(cn=a)(sn=b)")
    assert exc.value.position is not None


def test_parser_roundtrip_and_normalisation():
    text = r"(&(objectClass=user)(|(cn=Ivan*)(mail=*@x.ru))(!(userAccountControl:1.2.840.113556.1.4.803:=2))(lockoutTime>=1)(sn<=Z)(givenName~=Ann))"
    node = parse_filter(text)
    assert node.to_ldap() == text
    assert normalize_filter("objectClass=user") == "(objectClass=user)"
    assert normalize_filter(r"(cn=a\2Ab)") == r"(cn=a\2ab)"


def test_parser_depth_limit():
    deep = "(!" * 80 + "(cn=a)" + ")" * 80
    with pytest.raises(FilterSyntaxError):
        parse_filter(deep)


def test_unescape_utf8_and_binary():
    assert unescape_filter_value(r"\d0\98\d0\b2\d0\b0\d0\bd") == "Иван"
    assert unescape_filter_value(r"\ff\00").encode("latin-1") == b"\xff\x00"


def test_operators():
    f = (Equals("a", 1) & Present("b")) | ~Equals("c", "d")
    assert isinstance(f, Or)
    assert f.to_ldap() == "(|(&(a=1)(b=*))(!(c=d)))"
    assert isinstance(~Present("x"), Not)
