import json

import httpx

from app.core.config import AppConfig
from app.core.secrets import MemorySecretStore
from app.intelligence.cve import KevCatalog, NvdResponse, parse_nvd_cve
from app.intelligence.enrichment import OFFLINE_MESSAGE, EnrichmentService, worst_verdict
from app.intelligence.local_ioc import LocalIOCDatabase
from app.intelligence.mitre import TECHNIQUE_RE, default_catalog, map_alert_group
from app.analyzers.rule_knowledge import default_rule_kb
from app.models.analysis import CVERecord, IOCRecord
from tests.unit.helpers import group

KEV = {"catalogVersion": "1", "vulnerabilities": [{"cveID": "CVE-2021-44228", "vendorProject": "Apache",
                                                   "product": "Log4j2", "vulnerabilityName": "Log4Shell",
                                                   "dateAdded": "2021-12-10", "requiredAction": "Apply updates.",
                                                   "knownRansomwareCampaignUse": "Known"}]}
NVD = {"vulnerabilities": [{"cve": {
    "id": "CVE-2021-44228", "published": "2021-12-10T10:15:09",
    "descriptions": [{"lang": "en", "value": "Apache Log4j2 JNDI features..."}],
    "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 10.0, "baseSeverity": "CRITICAL",
                                                "vectorString": "CVSS:3.1/AV:N"}}]},
    "weaknesses": [{"description": [{"lang": "en", "value": "CWE-502"}]}],
    "references": [{"url": "https://logging.apache.org/log4j/2.x/security.html", "tags": ["Vendor Advisory"]}],
    "configurations": [{"nodes": [{"cpeMatch": [{"criteria": "cpe:2.3:a:apache:log4j:*:*:*:*:*:*:*:*",
                                                 "vulnerable": True}]}]}]}}]}


def online_config(**ti):
    return AppConfig.model_validate({"network": {"mode": "online"},
                                     "threat_intel": {"virustotal_enabled": True, "abuseipdb_enabled": True, **ti}})


def mock_transport():
    def handler(request: httpx.Request):
        url = str(request.url)
        if "known_exploited" in url:
            return httpx.Response(200, json=KEV)
        if "services.nvd.nist.gov" in url:
            return httpx.Response(200, json=NVD)
        if "abuseipdb" in url:
            assert request.headers["Key"] == "abuse-key"
            return httpx.Response(200, json={"data": {"abuseConfidenceScore": 100, "countryCode": "NL",
                                                      "totalReports": 50, "isp": "Bad ISP"}})
        if "virustotal" in url:
            assert request.headers["x-apikey"] == "vt-key"
            if "/files/" in url:
                return httpx.Response(404, json={"error": {"code": "NotFoundError"}})
            return httpx.Response(200, json={"data": {"attributes": {
                "last_analysis_stats": {"malicious": 12, "suspicious": 1, "harmless": 50, "undetected": 10},
                "country": "NL", "asn": 64500, "as_owner": "Example AS"}}})
        return httpx.Response(500)
    return httpx.MockTransport(handler)


def test_worst_verdict():
    assert worst_verdict(["clean", "suspicious", "unknown"]) == "suspicious"
    assert worst_verdict([]) == "unknown"


def test_local_ioc_lookup():
    db = LocalIOCDatabase()
    assert db.lookup("ip", "203.0.113.66")["verdict"] == "malicious"
    assert db.lookup("ip", "192.0.2.200")["verdict"] == "suspicious"  # CIDR entry
    assert db.lookup("domain", "cdn.update-check.example-malware.test")["verdict"] == "malicious"
    assert db.lookup("ip", "8.8.8.8") is None


def test_offline_enrichment_uses_local_list_only(tmp_path):
    iocs = [IOCRecord("ip", "203.0.113.66"), IOCRecord("ip", "10.0.0.1", internal=True)]
    cves = [CVERecord("CVE-2021-44228")]

    def no_network(request):
        raise AssertionError("network must not be used offline")

    svc = EnrichmentService(AppConfig(), MemorySecretStore(), transport=httpx.MockTransport(no_network))
    svc.kev = KevCatalog(tmp_path / "kev.json")
    report = svc.enrich(iocs, cves)
    assert report.mode == "offline"
    assert iocs[0].verdict == "malicious" and iocs[1].verdict == "unknown"
    assert not cves[0].kev_checked and any("nvd.nist.gov" in r["url"] for r in cves[0].references)
    assert cves[0].remediation


def test_online_enrichment_with_providers(tmp_path):
    secrets = MemorySecretStore({"virustotal_api_key": "vt-key", "abuseipdb_api_key": "abuse-key"})
    svc = EnrichmentService(online_config(), secrets, transport=mock_transport())
    svc.kev = KevCatalog(tmp_path / "kev.json")
    iocs = [IOCRecord("ip", "198.51.100.77"), IOCRecord("sha256", "ab" * 32), IOCRecord("ip", "10.1.1.1", internal=True)]
    cves = [CVERecord("CVE-2021-44228", packages=["log4j 2.11"])]
    report = svc.enrich(iocs, cves)
    assert report.online_ok, report.errors
    assert iocs[0].verdict == "malicious" and iocs[0].country == "NL"
    providers = {s["provider"] for s in iocs[0].sources}
    assert {"VirusTotal", "AbuseIPDB"} <= providers
    assert iocs[1].verdict == "unknown"  # VT 404
    assert iocs[2].sources == []  # internal never sent
    c = cves[0]
    assert c.known_exploited and c.kev_checked and c.cvss == 10.0 and c.cwe == ["CWE-502"]
    assert c.remediation == "Apply updates."
    assert "NVD" in c.sources and "CISA KEV" in c.sources
    assert (tmp_path / "kev.json").exists()  # cached for offline use
    assert KevCatalog(tmp_path / "kev.json").lookup("CVE-2021-44228") is not None


def test_api_timeout_degrades_gracefully(tmp_path):
    def timeout(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    secrets = MemorySecretStore({"virustotal_api_key": "vt-key"})
    svc = EnrichmentService(online_config(), secrets, transport=httpx.MockTransport(timeout))
    svc.kev = KevCatalog(tmp_path / "kev.json")
    iocs = [IOCRecord("ip", "198.51.100.77")]
    report = svc.enrich(iocs, [CVERecord("CVE-2021-44228")])
    assert report.status == OFFLINE_MESSAGE
    assert report.errors and iocs[0].verdict == "unknown"


def test_invalid_api_response_rejected(tmp_path):
    def bad(request):
        if "virustotal" in str(request.url):
            return httpx.Response(200, json={"unexpected": True})
        return httpx.Response(200, content=b"<html>not json</html>")

    secrets = MemorySecretStore({"virustotal_api_key": "vt-key"})
    svc = EnrichmentService(online_config(abuseipdb_enabled=False), secrets, transport=httpx.MockTransport(bad))
    svc.kev = KevCatalog(tmp_path / "kev.json")
    iocs = [IOCRecord("ip", "198.51.100.77")]
    report = svc.enrich(iocs, [])
    assert iocs[0].verdict == "unknown"
    assert any("invalid" in e.lower() for e in report.errors)


def test_auth_error_reported(tmp_path):
    secrets = MemorySecretStore({"virustotal_api_key": "wrong"})
    svc = EnrichmentService(online_config(abuseipdb_enabled=False, cisa_kev_enabled=False), secrets,
                            transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    report = svc.enrich([IOCRecord("ip", "198.51.100.7")], [])
    assert any("authentication failed" in e for e in report.errors)


def test_nvd_parser():
    info = parse_nvd_cve(NvdResponse.model_validate(NVD).vulnerabilities[0].cve)
    assert info["cvss"] == 10.0 and info["severity"] == "critical"
    assert info["affected_software"] == ["apache log4j"]
    assert info["references"][0]["tags"] == "Vendor Advisory"


def test_mitre_catalog_integrity():
    cat = default_catalog()
    assert len(cat.techniques) > 80
    for tid, tech in cat.techniques.items():
        assert TECHNIQUE_RE.match(tid)
        assert tech.tactics and all(t in cat.tactics for t in tech.tactics)
    for info in default_rule_kb().all():
        for tid in info.mitre:
            assert cat.get(tid) is not None, f"rule {info.rule_id} maps unknown technique {tid}"


def test_mitre_mapping_confidence_levels():
    cat = default_catalog()
    g = group(rule_mitre_ids=["T1110.001"], count=50, peak_count=50, users=[f"u{i}" for i in range(6)],
              processes=["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"],
              command_lines=["powershell -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoA"])
    mappings = {m.technique_id: m for m in map_alert_group(g, cat, default_rule_kb(), 5)}
    assert mappings["T1110.001"].confidence == "high" and mappings["T1110.001"].source == "wazuh_rule"
    assert mappings["T1110"].source in ("rule_kb", "heuristic")
    assert mappings["T1059.001"].confidence == "medium" and mappings["T1059.001"].evidence
    assert mappings["T1027"].evidence == "Base64-encoded PowerShell command"


def test_no_mapping_without_evidence():
    g = group(rule_id="999999", category="other", src_ip="")
    assert map_alert_group(g, default_catalog(), default_rule_kb(), 5) == []
