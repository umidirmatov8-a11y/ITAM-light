"""Global search results (IP, user, host, rule ID, CVE, hash, domain, MITRE technique)."""

from __future__ import annotations

from html import escape

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QTextBrowser

from app.i18n import tr
from app.i18n import num, severity_label, tr
from app.ui import theme
from app.ui.pages.base import BasePage


class SearchPage(BasePage):
    title = "Search"
    subtitle = "Search every alert by IP, username, hostname, rule ID, CVE, hash, domain or MITRE technique."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        bar = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr("e.g. 203.0.113.66, admin, web-01, 5710, CVE-2021-44228, T1110…"))
        self.query.returnPressed.connect(self.run)
        btn = QPushButton(tr("Search"))
        btn.setObjectName("primary")
        btn.clicked.connect(self.run)
        bar.addWidget(self.query, 1)
        bar.addWidget(btn)
        self.root.addLayout(bar)
        self.result_view = QTextBrowser()
        self.result_view.setOpenLinks(False)
        self.result_view.anchorClicked.connect(self._anchor)
        self.root.addWidget(self.result_view, 1)
        self.last = None

    def on_show(self, **kwargs) -> None:
        term = kwargs.get("term")
        if term:
            self.query.setText(str(term))
            self.run()

    def on_session(self, session) -> None:
        self.result_view.clear()
        self.last = None

    def run(self) -> None:
        term = self.query.text().strip()
        if not term:
            return
        if self.session is None:
            self.result_view.setHtml(f"<p>{escape(tr('No analysis loaded.'))}</p>")
            return
        res = self.session.search(term)
        self.last = res
        a = theme.ACCENT

        def link(kind: str, value: str, text: str | None = None) -> str:
            return f'<a href="{kind}:{escape(value)}" style="color:{a};">{escape(text or value)}</a>'

        if res.empty:
            self.result_view.setHtml(f"<h2>{escape(tr('No results for {term}', term=term))}</h2>"
                                     f"<p style='color:{theme.MUTED};'>{escape(tr('Detected search type'))}: "
                                     f"{escape(tr(res.kind))}</p>")
            return

        def stat(value: int, label: str) -> str:
            return f"<td><b style='font-size:18pt;'>{num(value)}</b><br>{escape(label)}</td>"

        arrow = " \u2192"
        html = [f"<h2>{escape(tr('Search'))}: {escape(res.term)}</h2><p style='color:{theme.MUTED};'>"
                f"{escape(tr('type'))}: {escape(tr(res.kind))}</p>",
                "<table cellpadding='6'><tr>" + stat(res.alerts, tr("alerts")) + stat(len(res.hosts), tr("hosts"))
                + stat(len(res.users), tr("users")) + stat(len(res.rules), tr("rules"))
                + stat(len(res.incidents), tr("incidents")) + "</tr></table>",
                f"<p>{link('alerts', 'all', tr('Show matching findings') + arrow)}</p>"]
        if res.incidents:
            html.append(f"<h3>{escape(tr('Incidents'))}</h3><ul>" + "".join(
                f"<li>{link('incident', iid, iid)} <span style='color:{theme.severity_color(sev)};'>"
                f"{escape(severity_label(sev))}</span> {escape(title)}</li>" for iid, title, sev in res.incidents)
                + "</ul>")
        if res.hosts:
            html.append(f"<h3>{escape(tr('Hosts'))}</h3><p>" + ", ".join(link("host", h) for h in res.hosts[:50])
                        + "</p>")
        if res.users:
            html.append(f"<h3>{escape(tr('Users'))}</h3><p>" + ", ".join(link("user", u) for u in res.users[:50])
                        + "</p>")
        if res.src_ips:
            html.append(f"<h3>{escape(tr('Source IPs'))}</h3><p>" + ", ".join(link("search", ip)
                                                                             for ip in res.src_ips[:50]) + "</p>")
        if res.rules:
            html.append(f"<h3>{escape(tr('Rules'))}</h3><ul>" + "".join(
                f"<li>{link('rule', rid, rid)} {escape(desc)} ({num(cnt)})</li>" for rid, desc, cnt in res.rules)
                + "</ul>")
        self.result_view.setHtml("".join(html))

    def _anchor(self, url) -> None:
        kind, _, value = url.toString().partition(":")
        if kind == "alerts" and self.last is not None:
            self.ctx.navigate("alerts", group_ids=list(self.last.group_ids))
        elif kind == "incident":
            self.ctx.navigate("incidents", incident_id=value)
        elif kind == "host":
            self.ctx.navigate("hosts", name=value)
        elif kind == "user":
            self.ctx.navigate("users", name=value)
        elif kind == "rule":
            self.ctx.navigate("rules", rule_id=value)
        elif kind == "search":
            self.ctx.navigate("search", term=value)
