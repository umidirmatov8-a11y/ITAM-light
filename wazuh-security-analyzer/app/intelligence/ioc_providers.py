"""IOC reputation providers: VirusTotal v3, AbuseIPDB v2, AlienVault OTX.

API keys come from the secure secret store only.  Every response is validated with a
Pydantic model; a provider error never aborts the analysis.
"""

from __future__ import annotations

import base64
import ipaddress
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.errors import ProviderResponseError
from app.intelligence.http_client import HttpClient

log = logging.getLogger(__name__)


@dataclass
class ProviderResult:
    provider: str
    verdict: str  # malicious | suspicious | clean | unknown
    score: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    link: str = ""
    country: str = ""
    asn: str = ""
    as_owner: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class IOCProvider:
    name = "provider"
    secret_name = ""
    supported: set[str] = set()

    def __init__(self, http: HttpClient, api_key: str):
        self.http = http
        self.api_key = api_key

    def supports(self, ioc_type: str) -> bool:
        return ioc_type in self.supported

    async def lookup(self, ioc_type: str, value: str) -> ProviderResult | None:
        raise NotImplementedError


# ---------------------------------------------------------------- VirusTotal
class _VTStats(_Lenient):
    malicious: int = 0
    suspicious: int = 0
    harmless: int = 0
    undetected: int = 0


class _VTAttributes(_Lenient):
    last_analysis_stats: _VTStats = Field(default_factory=_VTStats)
    reputation: int | None = None
    country: str = ""
    asn: int | None = None
    as_owner: str = ""
    tags: list[str] = Field(default_factory=list)
    popular_threat_classification: dict[str, Any] = Field(default_factory=dict)
    first_submission_date: int | None = None
    last_analysis_date: int | None = None
    creation_date: int | None = None
    registrar: str = ""
    meaningful_name: str = ""


class _VTData(_Lenient):
    attributes: _VTAttributes = Field(default_factory=_VTAttributes)


class _VTResponse(_Lenient):
    data: _VTData


class VirusTotalProvider(IOCProvider):
    name = "VirusTotal"
    secret_name = "virustotal_api_key"
    supported = {"ip", "domain", "md5", "sha1", "sha256", "url"}
    BASE = "https://www.virustotal.com/api/v3"

    async def lookup(self, ioc_type: str, value: str) -> ProviderResult | None:
        if ioc_type == "ip":
            path, gui = f"/ip_addresses/{value}", f"https://www.virustotal.com/gui/ip-address/{value}"
        elif ioc_type == "domain":
            path, gui = f"/domains/{value}", f"https://www.virustotal.com/gui/domain/{value}"
        elif ioc_type == "url":
            url_id = base64.urlsafe_b64encode(value.encode()).decode().strip("=")
            path, gui = f"/urls/{url_id}", f"https://www.virustotal.com/gui/url/{url_id}"
        else:
            path, gui = f"/files/{value}", f"https://www.virustotal.com/gui/file/{value}"
        status, data = await self.http.get_json(self.BASE + path, headers={"x-apikey": self.api_key})
        if status == 404 or data is None:
            return ProviderResult(self.name, "unknown", "not found", link=gui)
        try:
            attrs = _VTResponse.model_validate(data).data.attributes
        except ValidationError as exc:
            raise ProviderResponseError(f"VirusTotal: invalid response ({exc.error_count()} errors)") from exc
        stats = attrs.last_analysis_stats
        total = stats.malicious + stats.suspicious + stats.harmless + stats.undetected
        if stats.malicious >= 3:
            verdict = "malicious"
        elif stats.malicious >= 1 or stats.suspicious >= 2:
            verdict = "suspicious"
        elif total:
            verdict = "clean"
        else:
            verdict = "unknown"
        details: dict[str, Any] = {"malicious": stats.malicious, "suspicious": stats.suspicious, "total": total,
                                   "reputation": attrs.reputation}
        label = attrs.popular_threat_classification.get("suggested_threat_label")
        if label:
            details["family"] = label
        for key in ("first_submission_date", "last_analysis_date", "creation_date"):
            if getattr(attrs, key):
                details[key] = getattr(attrs, key)
        if attrs.registrar:
            details["registrar"] = attrs.registrar
        if attrs.meaningful_name:
            details["name"] = attrs.meaningful_name
        return ProviderResult(self.name, verdict, f"{stats.malicious}/{total} engines", details, gui,
                              attrs.country, str(attrs.asn or ""), attrs.as_owner, attrs.tags[:10])


# ---------------------------------------------------------------- AbuseIPDB
class _AbuseData(_Lenient):
    abuseConfidenceScore: int = 0
    countryCode: str | None = None
    isp: str | None = None
    domain: str | None = None
    usageType: str | None = None
    totalReports: int = 0
    lastReportedAt: str | None = None
    isWhitelisted: bool | None = None
    isTor: bool | None = None


class _AbuseResponse(_Lenient):
    data: _AbuseData


class AbuseIPDBProvider(IOCProvider):
    name = "AbuseIPDB"
    secret_name = "abuseipdb_api_key"
    supported = {"ip"}
    URL = "https://api.abuseipdb.com/api/v2/check"

    async def lookup(self, ioc_type: str, value: str) -> ProviderResult | None:
        status, data = await self.http.get_json(self.URL, headers={"Key": self.api_key},
                                                params={"ipAddress": value, "maxAgeInDays": 90})
        if data is None:
            return None
        try:
            d = _AbuseResponse.model_validate(data).data
        except ValidationError as exc:
            raise ProviderResponseError(f"AbuseIPDB: invalid response ({exc.error_count()} errors)") from exc
        score = d.abuseConfidenceScore
        if d.isWhitelisted:
            verdict = "clean"
        elif score >= 75:
            verdict = "malicious"
        elif score >= 25:
            verdict = "suspicious"
        elif d.totalReports == 0:
            verdict = "clean"
        else:
            verdict = "clean" if score < 10 else "suspicious"
        details = {"abuse_confidence": score, "reports": d.totalReports, "last_reported": d.lastReportedAt,
                   "usage_type": d.usageType, "isp": d.isp, "domain": d.domain, "tor": d.isTor}
        return ProviderResult(self.name, verdict, f"{score}% confidence, {d.totalReports} reports",
                              {k: v for k, v in details.items() if v not in (None, "")},
                              f"https://www.abuseipdb.com/check/{value}", d.countryCode or "", "", d.isp or "",
                              ["tor"] if d.isTor else [])


# ---------------------------------------------------------------- OTX
class _OTXPulseInfo(_Lenient):
    count: int = 0
    pulses: list[dict[str, Any]] = Field(default_factory=list)


class _OTXGeneral(_Lenient):
    pulse_info: _OTXPulseInfo = Field(default_factory=_OTXPulseInfo)
    reputation: int | None = None
    country_name: str | None = None
    asn: str | None = None


class OTXProvider(IOCProvider):
    name = "AlienVault OTX"
    secret_name = "otx_api_key"
    supported = {"ip", "domain", "md5", "sha1", "sha256"}
    BASE = "https://otx.alienvault.com/api/v1/indicators"

    async def lookup(self, ioc_type: str, value: str) -> ProviderResult | None:
        if ioc_type == "ip":
            section = "IPv6" if ipaddress.ip_address(value).version == 6 else "IPv4"
        elif ioc_type == "domain":
            section = "domain"
        else:
            section = "file"
        status, data = await self.http.get_json(f"{self.BASE}/{section}/{value}/general",
                                                headers={"X-OTX-API-KEY": self.api_key})
        if data is None:
            return ProviderResult(self.name, "unknown", "not found")
        try:
            g = _OTXGeneral.model_validate(data)
        except ValidationError as exc:
            raise ProviderResponseError(f"OTX: invalid response ({exc.error_count()} errors)") from exc
        pulses = g.pulse_info.count
        # Pulses are community reports - treated as "suspicious", never as confirmation on their own.
        verdict = "suspicious" if pulses >= 1 else "unknown"
        names = [str(p.get("name", ""))[:80] for p in g.pulse_info.pulses[:5] if p.get("name")]
        return ProviderResult(self.name, verdict, f"{pulses} pulses", {"pulses": pulses, "pulse_names": names},
                              f"https://otx.alienvault.com/indicator/{section.lower()}/{value}",
                              g.country_name or "", g.asn or "", "", [])


PROVIDERS: list[type[IOCProvider]] = [VirusTotalProvider, AbuseIPDBProvider, OTXProvider]
