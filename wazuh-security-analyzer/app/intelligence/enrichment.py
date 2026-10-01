"""Threat-intelligence enrichment orchestrator (OFFLINE / ONLINE).

OFFLINE: local IOC list, cached CISA KEV catalog, advisory links.
ONLINE : additionally NVD, CISA KEV refresh, VirusTotal / AbuseIPDB / OTX (when enabled and
         a key is stored), optional active domain checks (DNS/TLS, disabled by default
         because they contact attacker infrastructure).

Only public indicators are ever sent to external services: internal IPs, usernames and
hostnames never leave the machine.  Any provider failure degrades gracefully to local
analysis and is reported in :attr:`EnrichmentReport.status`.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import threading
from dataclasses import dataclass, field
from typing import Callable

from app.core.config import AppConfig
from app.core.errors import ProviderResponseError, ProviderUnavailableError
from app.core.secrets import SecretStore
from app.intelligence.cve import KevCatalog, NvdClient, advisory_links, remediation_text
from app.intelligence.http_client import HttpClient
from app.intelligence.ioc_providers import PROVIDERS, IOCProvider, ProviderResult
from app.intelligence.local_ioc import LocalIOCDatabase
from app.models.analysis import CVERecord, IOCRecord
from app.services.audit import audit

log = logging.getLogger("wsa.analysis")

_VERDICT_RANK = {"malicious": 3, "suspicious": 2, "clean": 1, "unknown": 0}
OFFLINE_MESSAGE = "Internet enrichment unavailable. Offline analysis completed."


def worst_verdict(verdicts) -> str:
    best = "unknown"
    for v in verdicts:
        if _VERDICT_RANK.get(v, 0) > _VERDICT_RANK[best]:
            best = v
    return best


@dataclass
class EnrichmentReport:
    mode: str = "offline"
    status: str = ""
    ioc_lookups: int = 0
    cve_lookups: int = 0
    errors: list[str] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    online_ok: bool = False


class EnrichmentService:
    def __init__(self, config: AppConfig, secrets: SecretStore, state=None,
                 progress: Callable[[str, int, int], None] | None = None,
                 cancel: threading.Event | None = None, transport=None):
        self.config = config
        self.secrets = secrets
        self.state = state
        self.progress = progress or (lambda msg, done, total: None)
        self.cancel = cancel or threading.Event()
        self.transport = transport
        self.local = LocalIOCDatabase()
        self.kev = KevCatalog()

    # ------------------------------------------------------------------ public API
    def enrich(self, iocs: list[IOCRecord], cves: list[CVERecord], online: bool | None = None) -> EnrichmentReport:
        online = self.config.network.online if online is None else online
        report = EnrichmentReport(mode="online" if online else "offline")
        self._apply_local(iocs, cves)
        if online:
            try:
                asyncio.run(self._enrich_online(iocs, cves, report))
            except Exception as exc:  # never let enrichment break the analysis
                log.exception("Online enrichment failed")
                report.errors.append(f"Enrichment error: {type(exc).__name__}: {exc}")
        for record in cves:
            if not record.remediation:
                record.remediation = remediation_text(record)
        if online and report.online_ok:
            report.status = (f"Online enrichment completed: {report.ioc_lookups} IOC and {report.cve_lookups} CVE "
                             f"lookups" + (f" ({len(report.errors)} provider errors)" if report.errors else "") + ".")
        elif online:
            report.status = OFFLINE_MESSAGE
        else:
            report.status = "Offline mode: local IOC list" + (" and cached CISA KEV catalog" if self.kev.available
                                                              else "") + " used."
        return report

    # ------------------------------------------------------------------ offline
    def _apply_local(self, iocs: list[IOCRecord], cves: list[CVERecord]) -> None:
        for record in iocs:
            hit = self.local.lookup(record.type, record.value)
            if hit:
                self._add_source(record, ProviderResult(f"Local IOC list ({hit['source']})", hit["verdict"],
                                                        details={"description": hit["description"]}))
        for record in cves:
            self._apply_kev(record)
            existing = {r.get("url") for r in record.references}
            for link in advisory_links(record.cve):
                if link["url"] not in existing:
                    record.references.append({"url": link["url"], "tags": link["name"]})

    def _apply_kev(self, record: CVERecord) -> None:
        if self.kev.available:
            record.kev_checked = True
        entry = self.kev.lookup(record.cve)
        if entry:
            record.known_exploited = True
            record.kev = entry.model_dump()
            if "CISA KEV" not in record.sources:
                record.sources.append("CISA KEV")

    @staticmethod
    def _add_source(record: IOCRecord, result: ProviderResult) -> None:
        record.sources = [s for s in record.sources if s.get("provider") != result.provider]
        record.sources.append(result.to_dict())
        record.verdict = worst_verdict([s.get("verdict", "unknown") for s in record.sources])
        record.country = record.country or result.country
        record.asn = record.asn or result.asn
        record.as_owner = record.as_owner or result.as_owner
        for tag in result.tags:
            if tag not in record.tags:
                record.tags.append(tag)

    # ------------------------------------------------------------------ online
    def _providers(self, http: HttpClient) -> list[IOCProvider]:
        enabled = {
            "VirusTotal": self.config.threat_intel.virustotal_enabled,
            "AbuseIPDB": self.config.threat_intel.abuseipdb_enabled,
            "AlienVault OTX": self.config.threat_intel.otx_enabled,
        }
        providers = []
        for cls in PROVIDERS:
            if not enabled.get(cls.name):
                continue
            key = self.secrets.get(cls.secret_name)
            if key:
                providers.append(cls(http, key))
        return providers

    async def _enrich_online(self, iocs: list[IOCRecord], cves: list[CVERecord], report: EnrichmentReport) -> None:
        ti = self.config.threat_intel
        async with HttpClient(self.config.network, transport=self.transport) as http:
            providers = self._providers(http)
            report.providers_used = [p.name for p in providers]
            tasks_total = 0
            # --- CISA KEV
            if ti.cisa_kev_enabled and self.kev.is_stale(ti.cache_ttl_hours):
                try:
                    self.progress("Downloading CISA KEV catalog", 0, 1)
                    await self.kev.refresh(http)
                    report.online_ok = True
                    report.providers_used.append("CISA KEV")
                except (ProviderUnavailableError, ProviderResponseError) as exc:
                    report.errors.append(str(exc))
            elif ti.cisa_kev_enabled and self.kev.available:
                report.online_ok = True
            for record in cves:
                self._apply_kev(record)

            # --- IOC reputation
            candidates = [r for r in iocs if not r.internal and r.type in ("ip", "domain", "md5", "sha1", "sha256",
                                                                            "url")]
            candidates.sort(key=lambda r: (-_VERDICT_RANK.get(r.verdict, 0), -r.count))
            candidates = candidates[: ti.max_ioc_lookups]
            sem = asyncio.Semaphore(ti.concurrency)
            done = 0
            jobs = [(p, r) for r in candidates for p in providers if p.supports(r.type)]
            tasks_total = len(jobs)
            if jobs:
                audit("threat_intel_lookup", providers=[p.name for p in providers], indicators=len(candidates))

            async def run(provider: IOCProvider, record: IOCRecord) -> None:
                nonlocal done
                if self.cancel.is_set():
                    return
                cache_key = f"ioc|{provider.name}|{record.type}|{record.value}"
                cached = self.state.cache_get(cache_key) if self.state else None
                try:
                    if cached is not None:
                        result = ProviderResult(**cached)
                    else:
                        async with sem:
                            result = await provider.lookup(record.type, record.value)
                        if result is not None and self.state:
                            self.state.cache_set(cache_key, result.to_dict(), ti.cache_ttl_hours * 3600)
                    if result is not None:
                        self._add_source(record, result)
                        record.enriched = True
                    report.online_ok = True
                    report.ioc_lookups += 1
                except (ProviderUnavailableError, ProviderResponseError) as exc:
                    if len(report.errors) < 50:
                        report.errors.append(str(exc))
                finally:
                    done += 1
                    self.progress("Threat intelligence lookups", done, tasks_total)

            await asyncio.gather(*(run(p, r) for p, r in jobs))

            # --- NVD
            if ti.nvd_enabled and cves and not self.cancel.is_set():
                nvd = NvdClient(http, self.secrets.get("nvd_api_key"))
                targets = sorted(cves, key=lambda c: (-(c.cvss or 0), -c.count))[: ti.max_cve_lookups]
                for idx, record in enumerate(targets, start=1):
                    if self.cancel.is_set():
                        break
                    self.progress(f"NVD lookup {record.cve}", idx, len(targets))
                    cache_key = f"nvd|{record.cve}"
                    info = self.state.cache_get(cache_key) if self.state else None
                    try:
                        if info is None:
                            info = await nvd.fetch(record.cve)
                            if info and self.state:
                                self.state.cache_set(cache_key, info, ti.cache_ttl_hours * 3600)
                        report.online_ok = True
                        report.cve_lookups += 1
                    except (ProviderUnavailableError, ProviderResponseError) as exc:
                        report.errors.append(str(exc))
                        if isinstance(exc, ProviderUnavailableError) and "network" in str(exc):
                            break
                        continue
                    if info:
                        self._apply_nvd(record, info)

            # --- optional active domain checks
            if ti.active_domain_checks:
                domains = [r for r in candidates if r.type == "domain"][:20]
                for record in domains:
                    details = await asyncio.to_thread(_domain_checks, record.value,
                                                      self.config.network.timeout_seconds)
                    if details:
                        self._add_source(record, ProviderResult("Active DNS/TLS check", "unknown", details=details))

    @staticmethod
    def _apply_nvd(record: CVERecord, info: dict) -> None:
        record.description = info.get("description") or record.description
        if info.get("cvss") is not None:
            record.cvss = info["cvss"]
        record.cvss_vector = info.get("cvss_vector", "") or record.cvss_vector
        record.severity = info.get("severity", "") or record.severity
        record.published = info.get("published", "")
        record.cwe = info.get("cwe", [])
        record.affected_software = info.get("affected_software", [])
        existing = {r.get("url") for r in record.references}
        for ref in info.get("references", []):
            if ref.get("url") not in existing:
                record.references.insert(0, ref)
        if "NVD" not in record.sources:
            record.sources.append("NVD")
        record.enriched = True


def _domain_checks(domain: str, timeout: float) -> dict:
    details: dict = {}
    try:
        infos = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
        details["resolves_to"] = sorted({i[4][0] for i in infos})[:10]
    except (socket.gaierror, UnicodeError, OSError):
        details["resolves_to"] = []
        return details
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as tls:
                cert = tls.getpeercert() or {}
        details["tls_issuer"] = " ".join("=".join(x) for rdn in cert.get("issuer", ()) for x in rdn)[:200]
        details["tls_not_after"] = cert.get("notAfter", "")
    except (OSError, ssl.SSLError, ValueError) as exc:
        details["tls_error"] = type(exc).__name__
    return details
