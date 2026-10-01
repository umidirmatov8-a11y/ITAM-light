"""Executive summary in plain language.

Wording rules: describe observations, avoid claiming compromise unless the evidence is a
confirmed malicious indicator or a successful login after brute force (and even then use
"potential compromise").
"""

from __future__ import annotations

from app.models.analysis import AnalysisSummary, Incident
from app.utils.text import plural
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
        return incident.title[0].lower() + incident.title[1:] if incident.title else "an unclassified finding"
    return template.format(src=(incident.source_ips[0] if incident.source_ips else "unknown sources"),
                           host=(incident.affected_hosts[0] if incident.affected_hosts else "an unknown host"),
                           cve=(incident.cves[0] if incident.cves else "unknown CVE"))


def build_executive_summary(summary: AnalysisSummary, incidents: list[Incident]) -> str:
    sev = summary.severity_counts
    crit, high = sev.get("critical", 0), sev.get("high", 0)
    paragraphs: list[str] = []
    period = ""
    if summary.first_ts and summary.last_ts:
        period = f" between {fmt_ts(summary.first_ts, False)} and {fmt_ts(summary.last_ts, False)}"
    paragraphs.append(f"During the analyzed period{period}, {plural(summary.events, 'security event')} from "
                      f"{plural(summary.agents, 'monitored host')} were analyzed.")
    if summary.events == 0:
        paragraphs.append("No events could be extracted from the provided files, so no assessment is possible.")
        return "\n\n".join(paragraphs)

    paragraphs.append(f"{plural(crit, 'event')} {'was' if crit == 1 else 'were'} classified as critical and "
                      f"{plural(high, 'event')} as high risk. These were consolidated into "
                      f"{plural(len(incidents), 'incident')} for investigation.")

    significant = [i for i in incidents if i.severity in ("critical", "high")]
    if significant:
        top = significant[:3]
        phrases = "; ".join(f"{_phrase(i)} ({i.severity})" for i in top)
        paragraphs.append(f"The most significant activity was associated with {phrases}.")
    elif incidents:
        paragraphs.append(f"The most notable finding was {_phrase(incidents[0])} ({incidents[0].severity}).")
    else:
        paragraphs.append("No activity requiring an incident was identified.")

    compromise = [i for i in incidents if i.assessment in ("Potential compromise",)]
    confirmed_ioc = [i for i in incidents if i.assessment == "Confirmed malicious indicator"]
    if compromise:
        hosts = sorted({h for i in compromise for h in i.affected_hosts})
        paragraphs.append(f"Potential compromise: {plural(len(compromise), 'incident')} show a successful login "
                          f"following repeated failures (hosts: {', '.join(hosts[:5])}). This requires immediate "
                          "verification with the account owners.")
    elif confirmed_ioc:
        paragraphs.append("Indicators confirmed as malicious by threat intelligence were observed. This does not by "
                          "itself prove a compromise, but the affected hosts should be checked with priority.")
    else:
        paragraphs.append("No confirmed compromise was identified based on the available logs.")

    if crit or high:
        paragraphs.append(f"Recommended priority: investigate the {plural(crit + high, 'critical/high event')} "
                          f"starting with incident {incidents[0].id if incidents else '-'}, and review the associated "
                          "source IP addresses and accounts.")
    else:
        paragraphs.append("Recommended priority: review the medium-risk findings during normal operations and tune "
                          "noisy rules.")
    if summary.enrichment_status:
        paragraphs.append(summary.enrichment_status)
    return "\n\n".join(paragraphs)
