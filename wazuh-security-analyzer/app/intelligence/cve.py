"""CVE intelligence: NVD API 2.0, CISA Known Exploited Vulnerabilities and vendor advisories.

API responses are validated with Pydantic models before use.  The KEV catalog is cached on
disk so that once downloaded it is also available in OFFLINE mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core import paths
from app.core.errors import ProviderResponseError
from app.intelligence.http_client import HttpClient
from app.models.analysis import CVERecord

log = logging.getLogger(__name__)

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


def advisory_links(cve: str) -> list[dict[str, str]]:
    """Authoritative pages for a CVE (links only - content is not scraped)."""
    return [
        {"name": "NVD", "url": f"https://nvd.nist.gov/vuln/detail/{cve}"},
        {"name": "CVE.org (MITRE)", "url": f"https://www.cve.org/CVERecord?id={cve}"},
        {"name": "CISA KEV", "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"},
        {"name": "Microsoft MSRC", "url": f"https://msrc.microsoft.com/update-guide/vulnerability/{cve}"},
        {"name": "Red Hat", "url": f"https://access.redhat.com/security/cve/{cve}"},
        {"name": "Ubuntu", "url": f"https://ubuntu.com/security/{cve}"},
        {"name": "Debian", "url": f"https://security-tracker.debian.org/tracker/{cve}"},
    ]


# ---------------------------------------------------------------- response models
class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class KevEntry(_Lenient):
    cveID: str
    vendorProject: str = ""
    product: str = ""
    vulnerabilityName: str = ""
    dateAdded: str = ""
    shortDescription: str = ""
    requiredAction: str = ""
    dueDate: str = ""
    knownRansomwareCampaignUse: str = ""


class KevFeed(_Lenient):
    catalogVersion: str = ""
    dateReleased: str = ""
    vulnerabilities: list[KevEntry] = Field(default_factory=list)


class _NvdDescription(_Lenient):
    lang: str = ""
    value: str = ""


class _CvssData(_Lenient):
    baseScore: float | None = None
    baseSeverity: str = ""
    vectorString: str = ""


class _CvssMetric(_Lenient):
    cvssData: _CvssData = Field(default_factory=_CvssData)
    baseSeverity: str = ""  # CVSS v2 places severity here


class _Weakness(_Lenient):
    description: list[_NvdDescription] = Field(default_factory=list)


class _Reference(_Lenient):
    url: str
    source: str = ""
    tags: list[str] = Field(default_factory=list)


class _CpeMatch(_Lenient):
    criteria: str = ""
    vulnerable: bool = True


class _Node(_Lenient):
    cpeMatch: list[_CpeMatch] = Field(default_factory=list)


class _Configuration(_Lenient):
    nodes: list[_Node] = Field(default_factory=list)


class _NvdCve(_Lenient):
    id: str
    published: str = ""
    descriptions: list[_NvdDescription] = Field(default_factory=list)
    metrics: dict[str, list[_CvssMetric]] = Field(default_factory=dict)
    weaknesses: list[_Weakness] = Field(default_factory=list)
    references: list[_Reference] = Field(default_factory=list)
    configurations: list[_Configuration] = Field(default_factory=list)


class _NvdItem(_Lenient):
    cve: _NvdCve


class NvdResponse(_Lenient):
    vulnerabilities: list[_NvdItem] = Field(default_factory=list)


# ---------------------------------------------------------------- KEV
class KevCatalog:
    def __init__(self, cache_file: Path | None = None):
        self.cache_file = cache_file or paths.cache_dir() / "cisa_kev.json"
        self.entries: dict[str, KevEntry] = {}
        self.loaded_at: float = 0.0
        self._load_cache()

    def _load_cache(self) -> None:
        if not self.cache_file.exists():
            return
        try:
            feed = KevFeed.model_validate(json.loads(self.cache_file.read_text(encoding="utf-8")))
            self.entries = {e.cveID.upper(): e for e in feed.vulnerabilities}
            self.loaded_at = self.cache_file.stat().st_mtime
        except (OSError, ValueError, ValidationError) as exc:
            log.warning("KEV cache unreadable: %s", exc)

    @property
    def available(self) -> bool:
        return bool(self.entries)

    def is_stale(self, ttl_hours: int) -> bool:
        return not self.entries or (time.time() - self.loaded_at) > ttl_hours * 3600

    async def refresh(self, http: HttpClient) -> None:
        status, data = await http.get_json(KEV_URL, max_bytes=50 * 1024 * 1024)
        if status != 200 or not isinstance(data, dict):
            raise ProviderResponseError("CISA KEV: unexpected response")
        try:
            feed = KevFeed.model_validate(data)
        except ValidationError as exc:
            raise ProviderResponseError(f"CISA KEV: response failed validation ({exc.error_count()} errors)") from exc
        self.entries = {e.cveID.upper(): e for e in feed.vulnerabilities}
        self.loaded_at = time.time()
        tmp = self.cache_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(self.cache_file)

    def lookup(self, cve: str) -> KevEntry | None:
        return self.entries.get(cve.upper())


# ---------------------------------------------------------------- NVD
class NvdClient:
    def __init__(self, http: HttpClient, api_key: str | None = None):
        self.http = http
        self.api_key = api_key
        # NVD public rate limits: 5 requests / 30 s without key, 50 / 30 s with key.
        self.delay = 0.7 if api_key else 6.0
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def fetch(self, cve: str) -> dict[str, Any] | None:
        async with self._lock:
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            headers = {"apiKey": self.api_key} if self.api_key else None
            try:
                status, data = await self.http.get_json(NVD_URL, headers=headers, params={"cveId": cve})
            finally:
                self._last = time.monotonic()
        if status == 404 or not data:
            return None
        try:
            parsed = NvdResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderResponseError(f"NVD: response failed validation ({exc.error_count()} errors)") from exc
        if not parsed.vulnerabilities:
            return None
        return parse_nvd_cve(parsed.vulnerabilities[0].cve)


def parse_nvd_cve(cve: _NvdCve) -> dict[str, Any]:
    description = next((d.value for d in cve.descriptions if d.lang == "en"), "")
    cvss = None
    vector = ""
    severity = ""
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        metrics = cve.metrics.get(key) or []
        if metrics and metrics[0].cvssData.baseScore is not None:
            cvss = metrics[0].cvssData.baseScore
            vector = metrics[0].cvssData.vectorString
            severity = (metrics[0].cvssData.baseSeverity or metrics[0].baseSeverity).lower()
            break
    cwe = sorted({d.value for w in cve.weaknesses for d in w.description if d.value.startswith("CWE-")})
    software: list[str] = []
    for conf in cve.configurations:
        for node in conf.nodes:
            for match in node.cpeMatch:
                if match.vulnerable and match.criteria:
                    parts = match.criteria.split(":")
                    if len(parts) > 5:
                        name = f"{parts[3]} {parts[4]}" + (f" {parts[5]}" if parts[5] not in ("*", "-") else "")
                        if name not in software:
                            software.append(name)
    refs = [{"url": r.url, "tags": ", ".join(r.tags)} for r in cve.references
            if any(t in r.tags for t in ("Vendor Advisory", "Patch", "Mitigation", "Third Party Advisory"))]
    return {"description": description, "cvss": cvss, "cvss_vector": vector, "severity": severity,
            "published": cve.published, "cwe": cwe, "affected_software": software[:15], "references": refs[:15]}


def remediation_text(record: CVERecord) -> str:
    if record.kev.get("requiredAction"):
        return record.kev["requiredAction"]
    from app.i18n import tr
    pkg = ", ".join(record.packages[:3]) if record.packages else tr("the affected software")
    return tr("Update {package} to a version that fixes {cve} as listed in the vendor advisory (see sources). If no fix "
              "is available, apply the vendor's mitigations and limit exposure of the vulnerable service.",
              package=pkg, cve=record.cve)
