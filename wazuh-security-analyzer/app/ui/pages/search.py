"""Global search results (IP, user, host, rule ID, CVE, hash, domain, MITRE technique)."""

from __future__ import annotations

from html import escape

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QTextBrowser

from app.ui import theme
from app.ui.pages.base import BasePage


class SearchPage(BasePage):
    title = "Search"
    subtitle = "Search every alert by IP, username, hostname, rule ID, CVE, hash, domain or MITRE technique."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        bar = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("e.g. 203.0.113.66, admin, web-01, 5710, CVE-2021-44228, T1110…")
        self.query.returnPressed.connect(self.run)
        btn = QPushButton("Search")
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
            self.result_view.setHtml("<p>No analysis loaded.</p>")
            return
        res = self.session.search(term)
        self.last = res
        a = theme.ACCENT

        def link(kind: str, value: str, text: str | None = None) -> str:
            return f'<a href="{kind}:{escape(value)}" style="color:{a};">{escape(text or value)}</a>'

        if res.empty:
            self.result_view.setHtml(f"<h2>No results for {escape(term)}</h2>"
                                     f"<p style='color:{theme.MUTED};'>Detected search type: {res.kind}</p>")
            return
        html = [f"<h2>Search: {escape(res.term)}</h2><p style='color:{theme.MUTED};'>type: {res.kind}</p>",
                "<table cellpadding='6'><tr>"
                f"<td><b style='font-size:18pt;'>{res.alerts:,}</b><br>alerts</td>"
                f"<td><b style='font-size:18pt;'>{len(res.hosts)}</b><br>hosts</td>"
                f"<td><b style='font-size:18pt;'>{len(res.users)}</b><br>users</td>"
                f"<td><b style='font-size:18pt;'>{len(res.rules)}</b><br>rules</td>"
                f"<td><b style='font-size:18pt;'>{len(res.incidents)}</b><br>incidents</td></tr></table>",
                f"<p>{link('alerts', 'all', 'Show matching findings →')}</p>"]
        if res.incidents:
            html.append("<h3>Incidents</h3><ul>" + "".join(
                f"<li>{link('incident', iid, iid)} <span style='color:{theme.severity_color(sev)};'>"
                f"{sev.upper()}</span> {escape(title)}</li>" for iid, title, sev in res.incidents) + "</ul>")
        if res.hosts:
            html.append("<h3>Hosts</h3><p>" + ", ".join(link("host", h) for h in res.hosts[:50]) + "</p>")
        if res.users:
            html.append("<h3>Users</h3><p>" + ", ".join(link("user", u) for u in res.users[:50]) + "</p>")
        if res.src_ips:
            html.append("<h3>Source IPs</h3><p>" + ", ".join(link("search", ip) for ip in res.src_ips[:50]) + "</p>")
        if res.rules:
            html.append("<h3>Rules</h3><ul>" + "".join(
                f"<li>{link('rule', rid, rid)} {escape(desc)} ({cnt:,})</li>" for rid, desc, cnt in res.rules) + "</ul>")
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
