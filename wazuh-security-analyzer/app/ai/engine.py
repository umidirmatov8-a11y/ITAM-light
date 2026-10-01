"""AI Analysis Engine.

Pipeline for one finding:

    normalized context (no raw logs) -> sanitization (always for cloud providers)
    -> provider call -> JSON extraction -> Pydantic validation (one repair retry)
    -> guardrails (drop IOCs/CVEs/MITRE IDs not supported by the context)
    -> placeholder restoration for local display

If no provider is configured or it fails, the local analysis remains authoritative and
an explanatory error is returned - the application never depends on AI.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.i18n import get_language, tr
from app.ai.prompts import REPAIR_PROMPT, SYSTEM_PROMPT, build_user_prompt
from app.ai.providers.base import AIProvider
from app.ai.providers.factory import create_provider
from app.ai.schemas import AIAnalysisResult
from app.core.config import AppConfig
from app.core.errors import ProviderResponseError, ProviderUnavailableError
from app.core.secrets import SecretStore
from app.intelligence.mitre import default_catalog
from app.models.analysis import AlertGroup, CVERecord, Incident, IOCRecord
from app.privacy.sanitizer import Sanitizer
from app.services.audit import audit
from app.utils.net import NetworkClassifier
from app.utils.timeutil import fmt_ts

log = logging.getLogger("wsa.analysis")

EXTERNAL_WARNING = ("WARNING: Sending security logs to external AI providers may expose sensitive information. "
                    "Use local AI for confidential data.")


@dataclass
class AIRunResult:
    ok: bool
    result: dict[str, Any] | None = None
    error: str = ""
    provider: str = ""
    model: str = ""
    anonymized: bool = False
    replacements: int = 0
    removed: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    analyzed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "result": self.result, "error": self.error, "provider": self.provider,
                "model": self.model, "anonymized": self.anonymized, "replacements": self.replacements,
                "removed": self.removed, "duration_seconds": self.duration_seconds, "analyzed_at": self.analyzed_at}


def extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a model answer (tolerates code fences and chatter)."""
    if not text:
        raise ValueError("empty answer")
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.M)
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("no JSON object in answer")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                obj = json.loads(cleaned[start:i + 1])
                if isinstance(obj, dict):
                    return obj
                break
    raise ValueError("unterminated JSON object in answer")


class AIAnalysisEngine:
    def __init__(self, config: AppConfig, secrets: SecretStore, provider: AIProvider | None = None,
                 transport=None):
        self.config = config
        self.secrets = secrets
        self.provider = provider if provider is not None else create_provider(config, secrets, transport)
        self.network = NetworkClassifier(config.wazuh.internal_networks, config.wazuh.known_scanners)
        self.catalog = default_catalog()

    @property
    def available(self) -> bool:
        return self.provider is not None

    def should_sanitize(self) -> bool:
        if self.provider is None:
            return False
        return self.provider.is_external or self.config.ai.anonymize_local

    # ------------------------------------------------------------------ context
    def build_context(self, groups: list[AlertGroup], incident: Incident | None = None,
                      iocs: list[IOCRecord] | None = None, cves: list[CVERecord] | None = None) -> dict[str, Any]:
        groups = sorted(groups, key=lambda g: -g.risk_score)
        main = groups[0]
        related = groups[1: 1 + self.config.ai.max_related_events]
        ctx: dict[str, Any] = {
            "finding": {
                "title": incident.title if incident else main.title,
                "local_assessment": incident.assessment if incident else main.assessment,
                "local_risk_score": incident.risk_score if incident else main.risk_score,
                "local_severity": incident.severity if incident else main.severity,
                "local_false_positive_probability": incident.fp_probability if incident else main.fp_probability,
                "attack_chain": incident.chain if incident else [],
                "scenario": incident.scenario if incident else "",
                "event_count": incident.event_count if incident else main.count,
                "first_seen": fmt_ts(incident.first_ts if incident else main.first_ts),
                "last_seen": fmt_ts(incident.last_ts if incident else main.last_ts),
            },
            "main_alert": {
                **main.representative,
                "rule_id": main.rule_id,
                "rule_level": main.rule_level,
                "description": main.rule_description,
                "category": main.category,
                "occurrences": main.count,
                "max_events_in_one_window": main.peak_count,
                "distinct_users": main.users[:20],
                "source_ips": main.src_ips[:20],
                "successful_login_after_failures": main.success_after_failures,
                "failures_before_success": main.failures_before_success,
                "sample_logs": [s[:600] for s in main.sample_logs[:2]],
            },
            "related_alerts": [
                {"rule_id": g.rule_id, "description": g.rule_description, "category": g.category, "count": g.count,
                 "host": g.agent_name, "source_ip": g.src_ip, "users": g.users[:5], "first_seen": fmt_ts(g.first_ts),
                 "process": g.processes[:2], "command_line": [c[:300] for c in g.command_lines[:1]],
                 "local_risk": g.risk_score}
                for g in related
            ],
            "asset_context": {
                "host": main.agent_name,
                "criticality": main.asset_criticality,
                "affected_hosts": incident.affected_hosts[:20] if incident else [main.agent_name],
                "affected_users": incident.affected_users[:20] if incident else main.users[:20],
            },
            "ioc_intelligence": [
                {"type": r.type, "value": r.value, "verdict": r.verdict, "internal": r.internal,
                 "sources": [{"provider": s.get("provider"), "verdict": s.get("verdict"), "score": s.get("score")}
                             for s in r.sources[:4]],
                 "country": r.country, "asn": r.asn}
                for r in (iocs or [])[:20]
            ],
            "mitre_candidates": [
                {"technique_id": m.technique_id, "name": m.name, "tactics": m.tactics, "confidence": m.confidence,
                 "evidence": m.evidence}
                for g in groups[:10] for m in g.mitre
            ][:25],
            "cve_context": [
                {"cve": c.cve, "cvss": c.cvss, "severity": c.severity, "known_exploited": c.known_exploited,
                 "description": c.description[:600], "packages": c.packages[:5]}
                for c in (cves or [])[:10]
            ],
            "local_evidence": (incident.evidence if incident else main.evidence)[:10],
            "local_false_positive_reasons": (incident.fp_reasons if incident else main.fp_reasons)[:6],
        }
        return ctx

    # ------------------------------------------------------------------ analysis
    def analyze(self, groups: list[AlertGroup], incident: Incident | None = None,
                iocs: list[IOCRecord] | None = None, cves: list[CVERecord] | None = None,
                known_users: list[str] | None = None, known_hosts: list[str] | None = None) -> AIRunResult:
        """``known_users`` / ``known_hosts``: all accounts and hosts of the analysis, so that they are masked
        even when they only appear inside free-text log lines of this finding."""
        started = time.time()
        if self.provider is None:
            return AIRunResult(False, error=tr("AI analysis is disabled (Settings > AI provider). "
                                                "Local analysis results are shown."))
        if not groups:
            return AIRunResult(False, error=tr("No alerts to analyze."))
        context = self.build_context(groups, incident, iocs, cves)
        sanitizer: Sanitizer | None = None
        if self.should_sanitize():
            users = {u for g in groups for u in g.users} | {g.user for g in groups if g.user}
            hosts = {g.agent_name for g in groups if g.agent_name}
            if incident:
                users |= set(incident.affected_users)
                hosts |= set(incident.affected_hosts)
            users |= set(known_users or [])
            hosts |= set(known_hosts or [])
            sanitizer = Sanitizer(self.config.privacy, self.network, users, hosts)
            context = sanitizer.sanitize(context)
        allowed_text = json.dumps(context, ensure_ascii=False, default=str)
        provider = self.provider
        audit("ai_request", provider=provider.name, model=provider.model, external=provider.is_external,
              anonymized=sanitizer is not None, replacements=sanitizer.replacements if sanitizer else 0,
              context_chars=len(allowed_text), finding=(incident.id if incident else groups[0].display_id))
        log.info("AI analysis via %s (%s), anonymized=%s", provider.name, provider.model, sanitizer is not None)
        user_prompt = build_user_prompt(context, get_language())
        try:
            answer = provider.complete(SYSTEM_PROMPT, user_prompt)
            try:
                result = AIAnalysisResult.model_validate(extract_json(answer))
            except (ValueError, ValidationError) as exc:
                error = str(exc).splitlines()[0][:300]
                log.warning("AI response invalid (%s); asking the model to repair it", error)
                repaired = provider.complete(SYSTEM_PROMPT, user_prompt + "\n\n" + REPAIR_PROMPT.format(error=error)
                                             + "\nPrevious answer:\n" + answer[:4000])
                result = AIAnalysisResult.model_validate(extract_json(repaired))
        except (ProviderUnavailableError, ProviderResponseError) as exc:
            return AIRunResult(False, error=tr("AI unavailable: {error}. Local analysis results are shown.", error=exc),
                               provider=provider.name, model=provider.model, anonymized=sanitizer is not None,
                               duration_seconds=round(time.time() - started, 1))
        except (ValueError, ValidationError) as exc:
            return AIRunResult(False, error=tr("The AI response did not match the required schema and was discarded. "
                                               "Details: {details}", details=str(exc).splitlines()[0][:200]),
                               provider=provider.name, model=provider.model, anonymized=sanitizer is not None,
                               duration_seconds=round(time.time() - started, 1))
        except Exception as exc:  # pragma: no cover - unexpected provider bugs must not crash the app
            log.exception("Unexpected AI failure")
            return AIRunResult(False, error=tr("AI analysis failed: {error}", error=type(exc).__name__),
                               provider=provider.name)

        cleaned, removed = self._guardrails(result, allowed_text, context)
        data = cleaned.model_dump()
        if sanitizer is not None:
            data = sanitizer.restore(data)
        return AIRunResult(True, data, provider=provider.name, model=provider.model,
                           anonymized=sanitizer is not None,
                           replacements=sanitizer.replacements if sanitizer else 0, removed=removed,
                           duration_seconds=round(time.time() - started, 1), analyzed_at=time.time())

    def _guardrails(self, result: AIAnalysisResult, allowed_text: str,
                    context: dict[str, Any]) -> tuple[AIAnalysisResult, list[str]]:
        removed: list[str] = []
        haystack = allowed_text.lower()
        iocs = []
        for ioc in result.iocs:
            value = ioc.split(":", 1)[1] if re.match(r"^(ip|domain|url|md5|sha1|sha256):", ioc) else ioc
            if value.lower() in haystack or ioc.lower() == "unknown":
                iocs.append(ioc)
            else:
                removed.append(f"IOC not present in context: {ioc}")
        cves = []
        for cve in result.cves:
            if cve.upper() in allowed_text.upper():
                cves.append(cve.upper())
            elif cve.lower() != "unknown":
                removed.append(f"CVE not present in context: {cve}")
        candidates = {m["technique_id"] for m in context.get("mitre_candidates", [])}
        mitre = []
        for item in result.mitre:
            if item.technique_id in candidates:
                mitre.append(item)
                continue
            tech = self.catalog.get(item.technique_id)
            if tech is None:
                removed.append(f"Unknown MITRE technique ID: {item.technique_id}")
                continue
            if not item.evidence:
                removed.append(f"MITRE {item.technique_id} suggested without evidence")
                continue
            item.name = item.name or tech.name
            item.confidence = "low"  # AI-only mappings never exceed low confidence
            mitre.append(item)
        cleaned = result.model_copy(update={"iocs": iocs, "cves": cves, "mitre": mitre})
        return cleaned, removed
