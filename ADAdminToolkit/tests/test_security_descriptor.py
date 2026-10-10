from adtoolkit.ldap.security_descriptor import (ACCESS_ALLOWED_ACE_TYPE, Ace, build_security_descriptor,
                                                cannot_change_password, deny_change_password_aces,
                                                parse_security_descriptor)


def test_cannot_change_password_detected():
    sd = build_security_descriptor(deny_change_password_aces())
    flag, who = cannot_change_password(sd)
    assert flag and set(who) == {"Все (Everyone)", "SELF"}


def test_allow_only_dacl():
    sd = build_security_descriptor([Ace(ACCESS_ALLOWED_ACE_TYPE, 0, 0x20094, "S-1-5-11")])
    assert cannot_change_password(sd) == (False, [])
    parsed = parse_security_descriptor(sd)
    assert parsed.owner == "S-1-5-32-544"
    assert parsed.dacl[0].sid == "S-1-5-11"
