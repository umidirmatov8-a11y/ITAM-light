import pytest

from adtoolkit.ldap.dn import (DNSyntaxError, build_dn, canonical_name, child_dn, container_path, dn_to_dns_domain,
                               dns_domain_to_dn, escape_dn_value, first_rdn, is_descendant, normalize_dn, parent_dn,
                               parse_dn, rdn_value)


@pytest.mark.parametrize("value,expected", [
    ("Smith, John", r"Smith\, John"),
    (" leading", r"\ leading"),
    ("trailing ", r"trailing\ "),
    ("#hash", r"\#hash"),
    ('a+b"c\\d<e>f;g=h', r'a\+b\"c\\d\<e\>f\;g\=h'),
    ("Иванов И.И.", "Иванов И.И."),
])
def test_escape_dn_value(value, expected):
    assert escape_dn_value(value) == expected


def test_parse_escaped_and_hex():
    dn = r"CN=Smith\, John,OU=Sales \28RU\29,OU=A\2CB,DC=corp,DC=local"
    rdns = parse_dn(dn)
    assert rdns[0] == [("CN", "Smith, John")]
    assert rdns[1] == [("OU", "Sales (RU)")]
    assert rdns[2] == [("OU", "A,B")]
    assert rdn_value(dn) == "Smith, John"
    assert parent_dn(dn) == r"OU=Sales (RU),OU=A\,B,DC=corp,DC=local"


def test_utf8_hex_escapes():
    assert rdn_value(r"CN=\D0\98\D0\B2\D0\B0\D0\BD,DC=x") == "Иван"


def test_multivalued_rdn_and_build():
    rdns = parse_dn("CN=a+UID=b,DC=x")
    assert rdns[0] == [("CN", "a"), ("UID", "b")]
    assert build_dn(rdns) == "CN=a+UID=b,DC=x"


def test_child_dn_escapes_user_input():
    dn = child_dn("OU=Users,DC=x", "CN", "Evil,OU=Admins")
    assert dn == r"CN=Evil\,OU\=Admins,OU=Users,DC=x"
    assert parent_dn(dn) == "OU=Users,DC=x"
    assert first_rdn(dn) == r"CN=Evil\,OU\=Admins"


@pytest.mark.parametrize("bad", ["CN", "=x", "CN=a,", "CN=a\\", 'CN=a"b'])
def test_invalid_dns(bad):
    with pytest.raises(DNSyntaxError):
        parse_dn(bad)


def test_normalize_and_descendant():
    assert normalize_dn("cn=Ivan ,  OU=Users,dc=CORP,DC=local") == normalize_dn("CN=ivan,OU=users,DC=corp,DC=Local")
    assert is_descendant("CN=a,OU=b,DC=x", "ou=B,dc=X")
    assert not is_descendant("OU=b,DC=x", "OU=b,DC=x")
    assert is_descendant("OU=b,DC=x", "OU=b,DC=x", include_self=True)
    assert not is_descendant("CN=a,OU=bb,DC=x", "OU=b,DC=x")


def test_domain_helpers():
    assert dn_to_dns_domain("OU=x,DC=company,DC=local") == "company.local"
    assert dns_domain_to_dn("company.local") == "DC=company,DC=local"
    with pytest.raises(DNSyntaxError):
        dns_domain_to_dn("bad domain.local")
    assert canonical_name("CN=u,OU=Sales,OU=Company,DC=corp,DC=local") == "corp.local/Company/Sales/u"
    assert container_path("CN=u,OU=Sales,OU=Company,DC=corp,DC=local") == "Company/Sales"
