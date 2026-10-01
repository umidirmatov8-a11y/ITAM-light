from app.analyzers.normalizer import Normalizer
from app.utils.timeutil import parse_timestamp

SHA256 = "2B1F0C9A7E5D3B1A0F9E8D7C6B5A49382716051F4E3D2C1B0A99887766554433"
MD5 = "1A2B3C4D5E6F708192A3B4C5D6E7F801"
SHA1 = "5e7a1c3b9d0f2468ace13579bdf02468ace13579"


def n(raw):
    return Normalizer().normalize(raw, "f.json", "test")


def test_sshd_alert(alert_factory):
    a = n(alert_factory(data={"srcip": "203.0.113.4", "dstuser": "admin"},
                        full_log="Invalid user admin from 203.0.113.4 port 1", mitre=["T1110.001", "bogus"]))
    assert a.rule_id == "5710" and a.rule_level == 5
    assert a.src_ip == "203.0.113.4" and a.user == "admin"
    assert a.rule_mitre_ids == ("T1110.001",)
    assert ("ip", "203.0.113.4") in a.iocs
    assert a.timestamp == parse_timestamp("2026-09-30T10:00:00Z")


def test_missing_fields_do_not_fail():
    a = n({})
    assert a.rule_id == "unknown" and a.rule_level == 0 and a.timestamp is None
    a = n({"rule": "not-a-dict", "agent": None, "data": [1, 2]})
    assert a.rule_id == "unknown"
    a = n("plain string event")
    assert a.full_log == "plain string event"


def test_level_clamped_and_non_numeric():
    assert n({"rule": {"id": "1", "level": 99}}).rule_level == 15
    assert n({"rule": {"id": "1", "level": "abc"}}).rule_level == 0


def test_windows_eventchannel_and_sysmon_hashes():
    raw = {"rule": {"id": "100", "level": 10, "description": "x", "groups": ["windows", "sysmon_event1"]},
           "agent": {"name": "WS1"},
           "data": {"win": {"system": {"eventID": "1"},
                            "eventdata": {"image": "C:\\Windows\\System32\\cmd.exe", "commandLine": "cmd /c whoami",
                                          "targetUserName": "CORP\\bob", "ipAddress": "::ffff:198.51.100.5",
                                          "hashes": "SHA256=" + SHA256 + ",MD5=" + MD5}}}}
    a = n(raw)
    assert a.process.endswith("cmd.exe") and a.command_line == "cmd /c whoami"
    assert a.user == "bob"
    assert a.src_ip == "198.51.100.5"
    assert a.hashes["sha256"] == SHA256.lower() and a.hashes["md5"] == MD5.lower()


def test_vulnerability_detector_layouts():
    old = n({"rule": {"id": "23505", "level": 10, "description": "CVE", "groups": ["vulnerability-detector"]},
             "data": {"vulnerability": {"cve": "CVE-2021-4034", "severity": "High",
                                        "cvss": {"cvss3": {"base_score": "7.8"}},
                                        "package": {"name": "policykit-1", "version": "0.105"}}}})
    assert old.cves == ("CVE-2021-4034",) and old.cvss == 7.8 and old.package == "policykit-1 0.105"
    new = n({"rule": {"id": "23506", "level": 13, "description": "x"},
             "data": {"vulnerability": {"id": "cve-2024-3094", "score": {"base": 10}, "severity": "Critical"}}})
    assert new.cves == ("CVE-2024-3094",) and new.cvss == 10.0


def test_virustotal_and_syscheck():
    a = n({"rule": {"id": "87105", "level": 12, "description": "VT"},
           "data": {"virustotal": {"positives": "54", "total": "72",
                                   "source": {"file": "/tmp/x", "sha1": SHA1}}},
           "syscheck": {"path": "/tmp/x", "sha256_after": SHA256}})
    assert a.vt_positives == 54 and a.vt_total == 72
    assert a.file_path == "/tmp/x"
    assert a.hashes["sha1"] == SHA1 and a.hashes["sha256"] == SHA256.lower()


def test_flattened_record():
    a = n({"rule.id": "5715", "rule.level": "3", "agent.name": "h", "data.srcip": "10.1.1.1"})
    assert a.rule_id == "5715" and a.rule_level == 3 and a.agent_name == "h" and a.src_ip == "10.1.1.1"


def test_relative_url_is_not_ioc():
    a = n({"rule": {"id": "31103", "level": 7, "description": "SQL injection attempt."},
           "data": {"srcip": "192.0.2.1", "url": "/index.php?id=1' OR '1'='1"}})
    assert not any(t == "url" for t, _ in a.iocs)


def test_uid_stable_and_distinct(alert_factory):
    a1 = n(alert_factory(full_log="x"))
    a2 = n(alert_factory(full_log="x"))
    a3 = n(alert_factory(full_log="y"))
    assert a1.uid == a2.uid != a3.uid


def test_timestamp_formats():
    assert parse_timestamp("2026-09-30T10:00:00.000+0000") == parse_timestamp("2026-09-30T10:00:00Z")
    assert parse_timestamp("2026-09-30 10:00:00") is not None
    assert parse_timestamp(1790762400) == 1790762400.0
    assert parse_timestamp(1790762400000) == 1790762400.0
    assert parse_timestamp("2026 Sep 30 10:00:00") is not None
    assert parse_timestamp("Sep 30 10:00:00", default_year=2026) == parse_timestamp("2026-09-30T10:00:00Z")
    assert parse_timestamp("garbage") is None
    assert parse_timestamp("1970-01-01T00:00:00Z") is None
