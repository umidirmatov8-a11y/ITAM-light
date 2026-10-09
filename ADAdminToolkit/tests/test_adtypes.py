from datetime import datetime, timedelta, timezone

from adtoolkit.ldap.adtypes import (FILETIME_NEVER, datetime_to_filetime, decode_attributes, display_value,
                                    filetime_to_datetime, group_category, group_scope, interval_to_timedelta,
                                    make_group_type, parse_generalized_time, sid_rid, sid_to_str, str_to_sid,
                                    to_generalized_time, uac_flags_text)


def test_filetime_roundtrip():
    dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    ft = datetime_to_filetime(dt)
    assert filetime_to_datetime(ft) == dt
    assert filetime_to_datetime(0) is None
    assert filetime_to_datetime(FILETIME_NEVER) is None
    assert filetime_to_datetime("garbage") is None


def test_intervals():
    assert interval_to_timedelta(-90 * 864000000000) == timedelta(days=90)
    assert interval_to_timedelta(-0x8000000000000000) is None
    assert interval_to_timedelta(0) is None


def test_generalized_time():
    assert parse_generalized_time("20260102030405.0Z") == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert parse_generalized_time(b"20260102030405.0+0300") == datetime(2026, 1, 2, 0, 4, 5, tzinfo=timezone.utc)
    dt = datetime(2026, 5, 6, 7, 8, 9, tzinfo=timezone.utc)
    assert parse_generalized_time(to_generalized_time(dt)) == dt


def test_sid_roundtrip():
    s = "S-1-5-21-1111111111-2222222222-3333333333-512"
    assert sid_to_str(str_to_sid(s)) == s
    assert sid_rid(s) == 512
    assert sid_to_str(str_to_sid("S-1-5-32-544")) == "S-1-5-32-544"


def test_group_type():
    gt = make_group_type("global", True)
    assert gt == -2147483646
    assert group_scope(gt) == "Глобальная"
    assert group_category(gt) == "Безопасности"
    assert group_category(make_group_type("universal", False)) == "Распространения"
    assert group_scope(-2147483643) == "Встроенная локальная"


def test_decode_attributes_types_and_ranges():
    raw = {"userAccountControl": [b"514"], "whenCreated": [b"20260101000000.0Z"], "cn": ["Иван".encode()],
           "objectSid": [str_to_sid("S-1-5-21-1-2-3-1000")], "member;range=0-1": [b"CN=a,DC=x", b"CN=b,DC=x"],
           "unicodePwd": [b"secret"], "lastLogonTimestamp": [b"133000000000000000"]}
    d = decode_attributes(raw)
    assert d["userAccountControl"] == [514]
    assert d["whenCreated"][0].year == 2026
    assert d["cn"] == ["Иван"]
    assert d["member"] == ["CN=a,DC=x", "CN=b,DC=x"]
    assert "unicodePwd" not in d
    assert isinstance(d["lastLogonTimestamp"][0], int)
    assert display_value("objectSid", d["objectSid"][0]) == "S-1-5-21-1-2-3-1000"


def test_uac_text():
    assert any("отключена" in t for t in uac_flags_text(514))
