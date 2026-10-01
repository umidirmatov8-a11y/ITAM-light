"""HTML renderers for detail panes (QTextBrowser rich text). All values are HTML-escaped."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any

from app.models.analysis import AlertGroup, CVERecord, Incident, IOCRecord
from app.models.categories import Category
from app.recommendations.engine import SECTION_TITLES, SECTIONS
from app.i18n import n, num, severity_label, tr
from app.ui import theme
from app.utils.timeutil import fmt_duration, fmt_ts

ICON = {"critical": "\U0001F534", "high": "\U0001F7E0", "medium": "\U0001F7E1", "low": "\U0001F535",
        "informational": "⚪"}


def e(value: Any) -> str:
    return escape("" if value is None else str(value))


def badge(severity: str, text: str | None = None) -> str:
    color = theme.severity_color(severity)
    fg = "#ffffff" if severity == "critical" else "#0d1117"
    label = (text or severity_label(severity)).upper()
    return (f'<span style="background-color:{color}; color:{fg}; font-weight:bold;">&nbsp;{e(label)}'
            f'&nbsp;</span>')


def h(title: str) -> str:
    return (f'<p style="margin-top:12px; margin-bottom:3px; color:{theme.ACCENT}; font-weight:bold; '
            f'font-size:10pt;">{e(tr(title))}</p>')


def para(text: str, muted: bool = False) -> str:
    color = theme.MUTED if muted else theme.TEXT
    return f'<p style="margin:2px 0 4px 0; color:{color};">{e(text)}</p>'


def bullets(items: list[str], ordered: bool = False, mono: bool = False) -> str:
    if not items:
        return para("—", True)
    tag = "ol" if ordered else "ul"
    style = ' style="font-family:Consolas,monospace; font-size:9pt;"' if mono else ""
    return f"<{tag} style='margin-top:0; margin-bottom:4px;'>" + "".join(
        f"<li{style}>{e(i)}</li>" for i in items) + f"</{tag}>"


def kv_table(rows: list[tuple[str, Any]]) -> str:
    body = "".join(f'<tr><td style="color:{theme.MUTED}; padding:2px 12px 2px 0;" valign="top">{e(tr(k))}</td>'
                   f'<td style="padding:2px 0;">{v if isinstance(v, _Raw) else e(v)}</td></tr>'
                   for k, v in rows if v not in (None, "", [], "-"))
    return f'<table cellspacing="0" cellpadding="0">{body}</table>'


class _Raw(str):
    """Marks pre-built, already escaped HTML."""


def _head(title: str, severity: str, subtitle: str = "") -> str:
    return (f'<p style="font-size:9pt; color:{theme.MUTED}; margin:0;">{e(subtitle)}</p>'
            f'<p style="font-size:14pt; font-weight:bold; margin:2px 0 6px 0;">{ICON.get(severity, "")} {e(title)}</p>')


def _scorebar(risk: float, confidence: float, fp: float, assessment: str, severity: str) -> str:
    return (f'<table cellspacing="0" cellpadding="4" style="margin-bottom:6px;"><tr>'
            f'<td nowrap>{badge(severity)}</td>'
            f'<td style="color:{theme.MUTED};">{e(tr("Risk"))}</td><td><b>{risk:.0f}</b>/100</td>'
            f'<td style="color:{theme.MUTED};">{e(tr("Confidence"))}</td><td><b>{confidence:.0%}</b></td>'
            f'<td style="color:{theme.MUTED};">{e(tr("False positive"))}</td><td><b>{fp:.0%}</b></td></tr></table>'
            f'<p style="margin:0 0 6px 0;">{e(tr("Assessment"))}: <b>{e(tr(assessment))}</b></p>')


def recommendations_html(recs: dict[str, list[str]]) -> str:
    out = []
    for key in SECTIONS:
        steps = recs.get(key) or []
        if steps:
            out.append(f'<p style="margin:6px 0 2px 0; font-weight:bold;">{e(tr(SECTION_TITLES[key]))}</p>')
            out.append(bullets(steps, ordered=True))
    return "".join(out) or para(tr("No specific actions - informational event."), True)


def _tactic(shortname: str) -> str:
    from app.intelligence.mitre import default_catalog
    return tr(default_catalog().tactic_name(shortname))


def mitre_html(mappings) -> str:
    if not mappings:
        return para(tr("No technique mapped (no sufficient evidence)."), True)
    rows = []
    for m in mappings:
        conf_color = {"high": theme.SEV["low"], "medium": theme.SEV["medium"], "low": theme.MUTED}.get(m.confidence)
        rows.append(f'<tr><td style="padding:1px 10px 1px 0;"><a href="{e(m.url)}" style="color:{theme.ACCENT};">'
                    f'{e(m.technique_id)}</a></td><td style="padding:1px 10px 1px 0;">{e(m.name)}</td>'
                    f'<td style="padding:1px 10px 1px 0; color:{theme.MUTED};">{e(", ".join(_tactic(t) for t in m.tactics))}</td>'
                    f'<td style="color:{conf_color}; padding-right:10px;">{e(tr(m.confidence).capitalize())}</td>'
                    f'<td style="color:{theme.MUTED};">{e(m.evidence)}</td></tr>')
    return '<table cellspacing="0">' + "".join(rows) + "</table>"


def ai_html(ai: dict[str, Any] | None) -> str:
    if not ai:
        return ""
    if not ai.get("ok"):
        return h("AI analysis") + para(ai.get("error") or tr("AI analysis failed."), True)
    r = ai.get("result") or {}
    meta = (f"{ai.get('provider')} · {ai.get('model')} · "
            f"{tr('anonymized') if ai.get('anonymized') else tr('not anonymized')} · "
            f"{ai.get('duration_seconds', 0)} s")
    out = [h("AI analyst assessment"), para(meta, True),
           _scorebar(_pct_score(r.get("severity")), float(r.get("confidence", 0)),
                     float(r.get("false_positive_probability", 0)), r.get("summary", ""), r.get("severity", "low"))]
    for key, title in (("what_happened", "What happened (AI)"), ("why_it_matters", "Why it matters (AI)"),
                       ("possible_attack", "Possible attack (AI)"),
                       ("false_positive_reasoning", "False-positive reasoning (AI)")):
        if r.get(key):
            out.append(f'<p style="margin:4px 0;"><b>{e(tr(title))}:</b> {e(r[key])}</p>')
    if r.get("mitre"):
        out.append(f'<p style="margin:4px 0;"><b>{e(tr("MITRE (AI)"))}:</b> ' + e(", ".join(
            f"{m.get('technique_id')} {m.get('name', '')} ({m.get('confidence')})" for m in r["mitre"])) + "</p>")
    recs = {"immediate": r.get("immediate_actions", []), "investigation": r.get("investigation_steps", []),
            "remediation": r.get("remediation", []), "prevention": r.get("prevention", [])}
    out.append(recommendations_html(recs))
    if ai.get("removed"):
        out.append(para(tr("Guardrails removed unsupported items: {items}", items="; ".join(ai["removed"])), True))
    out.append(para(tr("AI output is advisory. Verify against the evidence above."), True))
    return "".join(out)


def _pct_score(sev: str | None) -> float:
    return {"critical": 90, "high": 70, "medium": 50, "low": 30}.get((sev or "").lower(), 10)


# ----------------------------------------------------------------------------------- alert card
def render_group(g: AlertGroup, rule_info=None) -> str:
    out = [_head(g.title or g.rule_description, g.severity,
                 tr("{id} · Rule {rule} · Wazuh level {level} · {category}", id=g.display_id,
                    rule=g.rule_id, level=g.rule_level, category=Category.parse(g.category).label)
                 + (f" · {g.incident_id}" if g.incident_id else "")),
           _scorebar(g.risk_score, g.confidence, g.fp_probability, g.assessment, g.severity)]
    out += [h("What happened?"), para(g.what_happened)]
    out += [h("Why is it dangerous?"), para(g.why_it_matters)]
    out += [h("Possible attack"), para(g.possible_attack)]
    rows = [("Affected asset", f"{g.agent_name} ({g.agent_ip})" if g.agent_ip else g.agent_name),
            ("Asset criticality", tr(g.asset_criticality)),
            ("Affected user(s)", ", ".join(g.users[:15]) + (f" (+{len(g.users) - 15})" if len(g.users) > 15 else "")),
            ("Source", ", ".join(g.src_ips[:10]) + (tr(" (external)") if g.src_external else
                                                    (tr(" (internal)") if g.src_ip else ""))),
            ("Occurrences", num(g.count) + (tr(" (peak {peak} per window)", peak=num(g.peak_count))
                                            if g.peak_count > 1 else "")),
            ("Timeline", f"{fmt_ts(g.first_ts)} → {fmt_ts(g.last_ts)} "
                         f"({fmt_duration((g.last_ts or 0) - (g.first_ts or 0)) if g.first_ts else '-'})"),
            ("Processes", ", ".join(g.processes[:5])),
            ("Files", ", ".join(g.file_paths[:5])),
            ("CVE", ", ".join(g.cves[:10]) + (f" · CVSS {g.cvss:.1f}" if g.cvss is not None else "") +
             (" · " + tr("KNOWN EXPLOITED") if g.kev else "")),
            ("Threat intel", (tr(g.ioc_verdict) + ": " + "; ".join(g.ioc_verdict_sources[:3]))
             if g.ioc_verdict != "unknown" else ""),
            ("Source files", ", ".join(g.source_files[:5]))]
    out.append(h("Context"))
    out.append(kv_table(rows))
    out += [h("MITRE ATT&CK"), mitre_html(g.mitre)]
    out += [h("Evidence (observed facts)"), bullets(g.evidence)]
    if g.command_lines:
        out += [h("Command line"), bullets(g.command_lines[:3], mono=True)]
    out += [h("Reasoning (risk score factors)"),
            bullets([f"{f.points:+.1f}  {f.reason}" for f in g.risk_factors])]
    out.append(h(tr("False positive analysis — probability {probability}",
                    probability=f"{g.fp_probability:.0%}")))
    if g.fp_reasons:
        out.append(para(tr("Why this may be a false positive:"), True))
        out.append(bullets(g.fp_reasons))
    if g.fp_counter_reasons:
        out.append(para(tr("Why this is likely real:"), True))
        out.append(bullets(g.fp_counter_reasons))
    if rule_info:
        out += [h(tr("Rule intelligence — {rule}", rule=rule_info.rule_id)), para(rule_info.explanation)]
        if rule_info.false_positives:
            out.append(para(tr("Typical false positives: {items}", items="; ".join(rule_info.false_positives)), True))
    out += [h("Recommended actions"), recommendations_html(g.recommendations)]
    if g.sample_logs:
        out += [h("Sample log"), bullets(g.sample_logs[:2], mono=True)]
    out.append(ai_html(g.ai_analysis))
    return "".join(out)


# ----------------------------------------------------------------------------------- incident card
def render_incident(inc: Incident) -> str:
    out = [_head(inc.title, inc.severity, tr("{id} · {kind} · Status: {status}", id=inc.id,
                                            kind=tr(inc.kind.replace('_', ' ')), status=tr(inc.status))),
           _scorebar(inc.risk_score, inc.confidence, inc.fp_probability, inc.assessment, inc.severity),
           para(inc.summary)]
    if inc.chain:
        out.append(h("⚠ Possible attack chain"))
        chain_rows = []
        for idx, step in enumerate(inc.timeline):
            chain_rows.append(f'<tr><td style="color:{theme.MUTED}; padding-right:10px;">{e(fmt_ts(step.get("ts")))}'
                              f'</td><td><b>{e(step.get("text", "").split(":")[0])}</b>'
                              f' <span style="color:{theme.MUTED};">({e(n(step.get("count", 0), "event"))})</span></td></tr>')
            if idx < len(inc.timeline) - 1:
                chain_rows.append(f'<tr><td></td><td style="color:{theme.ACCENT}; font-size:12pt;">&#8595;</td></tr>')
        out.append('<table cellspacing="0">' + "".join(chain_rows) + "</table>")
        if inc.scenario:
            out.append(f'<p>{e(tr("Possible scenario"))}: <b>{e(inc.scenario)}</b></p>')
    out.append(h("Scope"))
    out.append(kv_table([("Affected hosts", f"{len(inc.affected_hosts)}: " + ", ".join(inc.affected_hosts[:15])),
                         ("Affected accounts", f"{len(inc.affected_users)}: " + ", ".join(inc.affected_users[:15])),
                         ("Source IPs", ", ".join(inc.source_ips[:15])),
                         ("Events", num(inc.event_count)),
                         ("Period", f"{fmt_ts(inc.first_ts)} → {fmt_ts(inc.last_ts)}"),
                         ("IOC", ", ".join(inc.iocs[:10])),
                         ("CVE", ", ".join(inc.cves[:10]))]))
    out += [h("MITRE ATT&CK"), mitre_html(inc.mitre)]
    out += [h("Evidence (observed facts)"), bullets(inc.evidence)]
    out += [h("Reasoning"), bullets(inc.reasoning)]
    if inc.fp_reasons:
        out += [h(tr("False positive considerations — {probability}", probability=f"{inc.fp_probability:.0%}")),
                bullets(inc.fp_reasons)]
    if not inc.chain and inc.timeline:
        out.append(h("Timeline"))
        out.append(bullets([f"{fmt_ts(t.get('ts'))}  {t.get('text')}  ({num(t.get('count', 0))})"
                            for t in inc.timeline[:25]]))
    out += [h("Recommended actions"), recommendations_html(inc.recommendations)]
    if inc.note:
        out += [h("Analyst note"), para(inc.note)]
    out.append(ai_html(inc.ai_analysis))
    return "".join(out)


# ----------------------------------------------------------------------------------- IOC / CVE / rule / entity
def render_ioc(rec: IOCRecord) -> str:
    sev = {"malicious": "critical", "suspicious": "medium", "clean": "low"}.get(rec.verdict, "informational")
    out = [_head(rec.value, sev, f"{rec.type.upper()} · {tr('internal') if rec.internal else tr('external')}"),
           f"<p>{e(tr('Verdict'))}: {badge(sev, tr(rec.verdict))}</p>",
           kv_table([("Occurrences", num(rec.count)), ("First seen", fmt_ts(rec.first_seen)),
                     ("Last seen", fmt_ts(rec.last_seen)), ("Hosts", ", ".join(rec.hosts[:20])),
                     ("Country", rec.country), ("ASN", rec.asn), ("AS owner", rec.as_owner),
                     ("Tags", ", ".join(rec.tags))])]
    out.append(h("Threat intelligence"))
    if not rec.sources:
        out.append(para(tr("No intelligence available. Switch to ONLINE mode and configure API keys to enrich this "
                           "indicator, or add it to the local IOC list."), True))
    for s in rec.sources:
        details = s.get("details") or {}
        detail_txt = "; ".join(f"{k}: {v}" for k, v in details.items() if v not in (None, "", [], {}))
        out.append(f'<p style="margin:3px 0;"><b>{e(s.get("provider"))}</b>: {e(tr(s.get("verdict") or "unknown"))}'
                   f'{(" (" + e(s.get("score")) + ")") if s.get("score") else ""}<br>'
                   f'<span style="color:{theme.MUTED};">{e(detail_txt)}</span>'
                   + (f'<br><a href="{e(s.get("link"))}" style="color:{theme.ACCENT};">{e(s.get("link"))}</a>'
                      if s.get("link") else "") + "</p>")
    return "".join(out)


def render_cve(rec: CVERecord) -> str:
    sev = (rec.severity or ("critical" if (rec.cvss or 0) >= 9 else "high" if (rec.cvss or 0) >= 7 else
                            "medium" if (rec.cvss or 0) >= 4 else "low")).lower()
    out = [_head(rec.cve, sev, tr("Vulnerability")),
           kv_table([("CVSS", f"{rec.cvss}" + (f"  {rec.cvss_vector}" if rec.cvss_vector else "")
                      if rec.cvss is not None else tr("unknown")),
                     ("Severity", severity_label(rec.severity) if rec.severity else tr("unknown").upper()),
                     ("Known exploited", _Raw(badge("critical", tr("YES - CISA KEV"))) if rec.known_exploited else
                      (tr("No (not listed in the CISA KEV catalog)") if rec.kev_checked else
                       tr("Unknown - CISA KEV catalog not loaded yet (run one analysis in ONLINE mode; it is then "
                          "cached for offline use)"))),
                     ("Published", rec.published), ("CWE", ", ".join(rec.cwe)),
                     ("Affected hosts", f"{len(rec.hosts)}: " + ", ".join(rec.hosts[:20])),
                     ("Installed packages", ", ".join(rec.packages)),
                     ("Affected software (NVD)", ", ".join(rec.affected_software[:10]))])]
    if rec.kev:
        out += [h("CISA KEV"), kv_table([("Vulnerability", rec.kev.get("vulnerabilityName")),
                                         ("Date added", rec.kev.get("dateAdded")),
                                         ("Due date", rec.kev.get("dueDate")),
                                         ("Ransomware use", rec.kev.get("knownRansomwareCampaignUse")),
                                         ("Required action", rec.kev.get("requiredAction"))])]
    out += [h("Description"), para(rec.description or tr("Not available offline. Switch to ONLINE mode to fetch the "
                                                          "NVD description."), not rec.description)]
    out += [h("Recommended remediation"), para(rec.remediation)]
    out.append(h("Sources"))
    links = [f'<a href="{e(r.get("url"))}" style="color:{theme.ACCENT};">{e(r.get("tags") or r.get("url"))}</a>'
             for r in rec.references[:15] if r.get("url", "").startswith("https://")]
    out.append("<p>" + "<br>".join(links) + "</p>")
    out.append(para(tr("Data sources used: {sources}", sources=", ".join(rec.sources) or tr("Wazuh alert only")),
                    True))
    return "".join(out)


def render_rule(info, stats: dict[str, Any] | None = None) -> str:
    if info is None:
        out = [_head(tr("Rule {rule}", rule=stats.get('rule_id') if stats else ''), "informational",
                     tr("Rule intelligence")),
               para(tr("This rule is not in the local knowledge base (custom or less common rule). The analyzer "
                       "classifies it from its groups and description."), True)]
    else:
        out = [_head(tr("Rule {rule}", rule=info.rule_id) + f": {info.description}", info.typical_severity,
                     tr("Rule intelligence · category {category} · typical level {level}",
                        category=Category.parse(info.category).label, level=info.typical_level)),
               h("Explanation"), para(info.explanation),
               h("MITRE ATT&CK"), para(", ".join(info.mitre) or tr("None")),
               h("Common false positives"), bullets(info.false_positives),
               h("Investigation steps"), bullets(info.investigation, ordered=True),
               h("Recommended remediation"), bullets(info.remediation, ordered=True)]
    if stats:
        out += [h("In the current analysis"),
                kv_table([("Events", num(stats.get('events', 0))), ("Findings", stats.get("groups", 0)),
                          ("Hosts", ", ".join(stats.get("hosts", [])[:15])),
                          ("Highest severity", severity_label(stats["severity"]) if stats.get("severity") else "-")])]
    return "".join(out)


def render_entity(kind: str, entity: dict[str, Any], groups: list[AlertGroup]) -> str:
    data = entity.get("data", {})
    rows = [("Events", num(entity.get('events', 0))), ("Findings", entity.get("groups")),
            ("Incidents", entity.get("incidents")), ("Max risk", f"{entity.get('max_risk', 0):.0f}"),
            ("First seen", fmt_ts(entity.get("first_ts"))), ("Last seen", fmt_ts(entity.get("last_ts")))]
    if kind == "host":
        rows += [("IP", data.get("ip")), ("Criticality", tr(data.get("criticality") or "")),
                 ("Accounts", ", ".join(data.get("users", [])[:15])),
                 ("Source IPs", ", ".join(data.get("src_ips", [])[:15]))]
    else:
        rows += [("Hosts", ", ".join(data.get("hosts", [])[:15])),
                 ("Source IPs", ", ".join(data.get("src_ips", [])[:15]))]
    cats = data.get("categories", {})
    rows.append(("Behaviour", ", ".join(f"{Category.parse(k).label} ({num(v)})" for k, v in cats.items())))
    out = [_head(entity.get("name", ""), entity.get("severity", "informational"),
                 tr("Host") if kind == "host" else tr("User")), kv_table(rows),
           h("Top findings")]
    items = []
    for g in groups[:25]:
        items.append(f'<li>{badge(g.severity)} <b>{e(g.title)}</b> <span style="color:{theme.MUTED};">'
                     f'({e(tr("{events}, risk {risk}", events=n(g.count, "event"), risk=f"{g.risk_score:.0f}"))}, '
                     f'{e(g.display_id)})</span></li>')
    out.append("<ul>" + "".join(items) + "</ul>" if items else para(tr("No findings."), True))
    return "".join(out)


def render_raw_alert(detail: dict[str, Any]) -> str:
    import json
    raw = detail.get("raw")
    pretty = json.dumps(raw, indent=2, ensure_ascii=False, default=str) if isinstance(raw, (dict, list)) else str(raw)
    ts = detail.get("ts")
    return (_head(tr("Event #{id}", id=detail.get('id')), "informational",
                  datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else "")
            + kv_table([(k, detail.get(k)) for k in ("rule_id", "level", "description", "category", "agent",
                                                      "src_ip", "dst_ip", "user", "process", "file_path", "hash",
                                                      "cve", "source_file")])
            + h("Full log") + f'<pre style="white-space:pre-wrap;">{e(detail.get("full_log"))}</pre>'
            + h("Raw event (JSON)") + f'<pre style="font-family:Consolas,monospace; font-size:8.5pt;">{e(pretty)}</pre>')
