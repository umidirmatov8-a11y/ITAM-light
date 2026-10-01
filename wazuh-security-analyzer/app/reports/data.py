"""Collects everything a report needs from an analysis session (format independent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app import __app_name__, __version__
from app.i18n import tr
from app.core.severity import SEVERITY_ORDER
from app.database.store import GroupFilter
from app.models.analysis import AlertGroup, AnalysisSummary, CVERecord, Incident, IOCRecord
from app.recommendations.engine import RecommendationEngine
from app.services.session import AnalysisSession

ALL_SECTIONS = ("executive_summary", "statistics", "critical_alerts", "incidents", "hosts", "users", "iocs", "cves",
                "mitre", "recommendations", "timeline", "appendix")


@dataclass
class ReportData:
    title: str
    generated_at: str
    app: str
    summary: AnalysisSummary
    incidents: list[Incident]
    alerts: list[AlertGroup]
    hosts: list[dict[str, Any]]
    users: list[dict[str, Any]]
    iocs: list[IOCRecord]
    cves: list[CVERecord]
    mitre: list[dict[str, Any]]
    recommendations: dict[str, list[str]]
    timeline: list[dict[str, Any]]
    dashboard: dict[str, Any]
    sections: tuple[str, ...] = ALL_SECTIONS
    appendix: dict[str, Any] = field(default_factory=dict)

    def has(self, section: str) -> bool:
        return section in self.sections


def collect_report_data(session: AnalysisSession, title: str = "Wazuh Security Analysis Report",
                        sections: tuple[str, ...] = ALL_SECTIONS, max_alerts: int = 300) -> ReportData:
    store = session.store
    incidents = session.incidents()
    alerts = store.query_groups(GroupFilter(severities=["critical", "high"]), 0, max_alerts)
    if len(alerts) < 25:
        alerts += store.query_groups(GroupFilter(severities=["medium"]), 0, 25 - len(alerts))
    significant = [i for i in incidents if i.severity in ("critical", "high")] or incidents[:10]
    recs = RecommendationEngine.merge([i.recommendations for i in significant[:10]], limit=12)
    timeline: list[dict[str, Any]] = []
    for inc in sorted(incidents, key=lambda i: i.first_ts or 0):
        if inc.severity in ("critical", "high"):
            timeline.append({"ts": inc.first_ts, "end": inc.last_ts, "text": f"{inc.id}: {inc.title}",
                             "severity": inc.severity})
    dashboard = session.dashboard()
    summary = session.summary
    appendix = {
        "files": summary.file_names,
        "parsers": summary.parsers_used,
        "rejected": summary.rejected_inputs,
        "warnings": summary.warnings,
        "top_rules": dashboard.get("top_rules", []),
        "severity_scale": tr("0-19 Informational, 20-39 Low, 40-59 Medium, 60-79 High, 80-100 Critical"),
        "mode": summary.mode,
        "duration": summary.duration_seconds,
        "duplicates": summary.duplicates,
        "parse_errors": summary.parse_errors,
        "severity_order": [s.value for s in SEVERITY_ORDER],
    }
    return ReportData(
        title=title,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        app=f"{__app_name__} {__version__}",
        summary=summary,
        incidents=incidents,
        alerts=alerts,
        hosts=store.entities("host", 200),
        users=store.entities("user", 200),
        iocs=[i for i in store.iocs(include_internal=False, limit=500)],
        cves=store.cves(),
        mitre=session.mitre_stats(),
        recommendations=recs,
        timeline=timeline[:100],
        dashboard=dashboard,
        sections=tuple(sections),
        appendix=appendix,
    )
