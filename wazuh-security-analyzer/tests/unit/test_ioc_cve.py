from app.analyzers.ioc_extractor import extract_cves, extract_iocs, refang
from app.utils.net import NetworkClassifier


def test_cve_extraction():
    text = "Found cve-2021-44228 and CVE-2024-3094; CVE-1999-0001 is ok; CVE-20-1 is not"
    assert extract_cves(text) == ["CVE-2021-44228", "CVE-2024-3094", "CVE-1999-0001"]
    assert extract_cves("") == []


def test_ioc_extraction_types():
    text = ("curl http://evil.example.com/a.sh from 203.0.113.9 hash 7d3c2b1a0f9e8d7c6b5a493827160514" +
            " sha256 " + "0123456789abcdef" * 4 + " file.exe script.ps1 System.Management.dll")
    iocs = extract_iocs(text)
    types = {t for t, _ in iocs}
    assert ("url", "http://evil.example.com/a.sh") in iocs
    assert ("domain", "evil.example.com") in iocs
    assert ("ip", "203.0.113.9") in iocs
    assert ("sha256", "0123456789abcdef" * 4) in iocs
    assert "md5" in types
    values = {v for _, v in iocs}
    assert "file.exe" not in values and "script.ps1" not in values


def test_defanged_indicators():
    assert refang("hxxp://bad[.]example[.]com") == "http://bad.example.com"
    iocs = extract_iocs("visit hxxps://bad[.]example[.]net/x")
    assert ("domain", "bad.example.net") in iocs


def test_empty_file_hash_ignored():
    assert extract_iocs("md5 d41d8cd98f00b204e9800998ecf8427e") == []


def test_excluded_domains():
    iocs = extract_iocs("connect to web-01.corp.example.com", exclude_domains=["corp.example.com"])
    assert not any(t == "domain" for t, _ in iocs)


def test_invalid_ips_not_extracted():
    assert extract_iocs("version 1.2.3.4.5 and 999.1.1.1") == []


def test_network_classifier():
    nc = NetworkClassifier(internal_networks=["203.0.113.0/28"], known_scanners=["10.10.5.5"])
    assert nc.is_internal("10.1.2.3") and nc.is_internal("192.168.1.1") and nc.is_internal("127.0.0.1")
    assert nc.is_external("198.51.100.4")  # documentation range treated as external
    assert nc.is_internal("203.0.113.5")  # custom internal network
    assert nc.is_internal("not-an-ip") is None
    assert nc.is_internal("::ffff:10.0.0.1")
    assert nc.is_known_scanner("10.10.5.5") and not nc.is_known_scanner("10.10.5.6")
