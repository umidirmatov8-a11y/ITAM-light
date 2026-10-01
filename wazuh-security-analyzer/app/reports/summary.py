"""Executive summary in plain language.

Wording rules: describe observations, avoid claiming compromise unless the evidence is a
confirmed malicious indicator or a successful login after brute force (and even then use
"potential compromise").
"""

from __future__ import annotations

from app.i18n import n, severity_label, tr
from app.models.analysis import AnalysisSummary, Incident
from app.utils.timeutil import fmt_ts

_KIND_PHRASES = {
    "brute_force": "repeated authentication attempts from {src}",
    "attack_chain": "a multi-stage activity chain on {host}",
    "malware": "malicious files detected on {host}",
    "vulnerability": "vulnerable software ({cve})",
    "web_attack": "web attack attempts from {src}",
    "scan": "scanning activity from {src}",
}


def _phrase(incident: Incident) -> str:
    template = _KIND_PHRASES.get(incident.kind)
    if not template:
        return incident.title[0].lower() + incident.title[1:] if incident.title else tr("an unclassified finding")
    return tr(template,
              src=(incident.source_ips[0] if incident.source_ips else tr("unknown sources")),
              host=(incident.affected_hosts[0] if incident.affected_hosts else tr("an unknown host")),
              cve=(incident.cves[0] if incident.cves else tr("unknown CVE")))


def build_executive_summary(summary: AnalysisSummary, incidents: list[Incident]) -> str:
    sev = summary.severity_counts
    crit, high = sev.get("critical", 0), sev.get("high", 0)
    paragraphs: list[str] = []
    period = ""
    if summary.first_ts and summary.last_ts:
        period = tr(" between {start} and {end}", start=fmt_ts(summary.first_ts, False),
                    end=fmt_ts(summary.last_ts, False))
    paragraphs.append(tr("During the analyzed period{period}, {events} from {hosts} were analyzed.", period=period,
                         events=n(summary.events, "security event"), hosts=n(summary.agents, "monitored host")))
    if summary.events == 0:
        paragraphs.append(tr("No events could be extracted from the provided files, so no assessment is possible."))
        return "\n\n".join(paragraphs)

    paragraphs.append(tr("Critical events: {critical}; high-risk events: {high}. They were consolidated into {incidents} "
                         "for investigation.", critical=n(crit, "event"), high=n(high, "event"),
                         incidents=n(len(incidents), "incident")))

    significant = [i for i in incidents if i.severity in ("critical", "high")]
    if significant:
        phrases = "; ".join(f"{_phrase(i)} ({severity_label(i.severity, upper=False).lower()})"
                            for i in significant[:3])
        paragraphs.append(tr("The most significant activity was associated with {phrases}.", phrases=phrases))
    elif incidents:
        paragraphs.append(tr("The most notable finding was {phrase} ({severity}).", phrase=_phrase(incidents[0]),
                             severity=severity_label(incidents[0].severity, upper=False).lower()))
    else:
        paragraphs.append(tr("No activity requiring an incident was identified."))

    compromise = [i for i in incidents if i.assessment in ("Potential compromise",)]
    confirmed_ioc = [i for i in incidents if i.assessment == "Confirmed malicious indicator"]
    if compromise:
        hosts = sorted({h for i in compromise for h in i.affected_hosts})
        paragraphs.append(tr("Potential compromise: {incidents} show a successful login following repeated failures "
                             "(hosts: {hosts}). This requires immediate verification with the account owners.",
                             incidents=n(len(compromise), "incident"), hosts=", ".join(hosts[:5])))
    elif confirmed_ioc:
        paragraphs.append(tr("Indicators confirmed as malicious by threat intelligence were observed. This does not by "
                             "itself prove a compromise, but the affected hosts should be checked with priority."))
    else:
        paragraphs.append(tr("No confirmed compromise was identified based on the available logs."))

    if crit or high:
        paragraphs.append(tr("Recommended priority: investigate the {events} starting with incident {incident}, and "
                             "review the associated source IP addresses and accounts.",
                             events=n(crit + high, "critical/high event"),
                             incident=incidents[0].id if incidents else "-"))
    else:
        paragraphs.append(tr("Recommended priority: review the medium-risk findings during normal operations and tune "
                             "noisy rules."))
    if summary.enrichment_status:
        paragraphs.append(summary.enrichment_status)
    return "\n\n".join(paragraphs)
