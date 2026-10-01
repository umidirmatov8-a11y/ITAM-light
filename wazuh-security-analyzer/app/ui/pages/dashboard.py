"""Dashboard: drop zone, load summary, SOC overview cards and charts."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget)

from app.core.severity import SEVERITY_ORDER
from app.models.categories import Category
from app.ui import theme
from app.ui.pages.base import BasePage
from app.ui.render import e
from app.ui.widgets.charts import DonutChart, HBarChart, TimelineChart
from app.ui.widgets.common import Card, DropZone, StatCard, label
from app.utils.timeutil import fmt_duration, fmt_ts


class DashboardPage(BasePage):
    title = "Security Overview"
    subtitle = "Drop Wazuh alerts to start. Analysis runs locally; nothing leaves this computer in OFFLINE mode."

    pathsSelected = Signal(list)
    demoRequested = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.stack = QStackedWidget()
        self.root.addWidget(self.stack, 1)

        # --- empty state
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.addStretch(1)
        self.drop = DropZone()
        self.drop.pathsSelected.connect(self.pathsSelected.emit)
        self.drop.demoRequested.connect(self.demoRequested.emit)
        el.addWidget(self.drop)
        hint = label("Supported: Wazuh alerts.json, alerts.log, OpenSearch/Indexer exports, Wazuh API output, CSV, "
                     "XML, CEF, syslog. Multiple files, folders, ZIP and .gz archives are accepted.", "muted", True)
        hint.setAlignment(Qt.AlignCenter)
        el.addWidget(hint)
        el.addStretch(2)
        self.stack.addWidget(empty)

        # --- results
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("page")
        content.setAttribute(Qt.WA_StyledBackground, True)
        grid = QVBoxLayout(content)
        grid.setContentsMargins(0, 0, 6, 0)
        grid.setSpacing(12)

        top = QHBoxLayout()
        self.load_info = Card("Loaded data")
        self.load_text = label("", wrap=True)
        self.load_info.add(self.load_text)
        top.addWidget(self.load_info, 2)
        self.compact_drop = DropZone(compact=True)
        self.compact_drop.pathsSelected.connect(self.pathsSelected.emit)
        self.compact_drop.demoRequested.connect(self.demoRequested.emit)
        top.addWidget(self.compact_drop, 3)
        grid.addLayout(top)

        cards = QGridLayout()
        cards.setSpacing(10)
        self.sev_cards: dict[str, StatCard] = {}
        for i, sev in enumerate(SEVERITY_ORDER):
            card = StatCard(sev.value, "0", theme.SEV[sev.value])
            card.clicked.connect(lambda s=sev.value: self.ctx.navigate("alerts", severity=s))
            self.sev_cards[sev.value] = card
            cards.addWidget(card, 0, i)
        self.metric_cards: dict[str, StatCard] = {}
        for i, (key, title, page) in enumerate([("incidents", "Incidents", "incidents"),
                                                 ("hosts", "Affected Hosts", "hosts"),
                                                 ("users", "Affected Users", "users"),
                                                 ("external", "External IPs", "ioc"), ("cves", "CVE", "cve"),
                                                 ("mitre", "MITRE Techniques", "mitre")]):
            card = StatCard(title, "0")
            card.clicked.connect(lambda p=page: self.ctx.navigate(p))
            self.metric_cards[key] = card
            cards.addWidget(card, 1 + i // 5, i % 5)
        grid.addLayout(cards)

        row1 = QHBoxLayout()
        sev_card = Card("Severity distribution")
        self.donut = DonutChart()
        sev_card.add(self.donut, 1)
        row1.addWidget(sev_card, 1)
        tl_card = Card("Timeline (events by severity)")
        self.timeline = TimelineChart()
        tl_card.add(self.timeline, 1)
        row1.addWidget(tl_card, 3)
        grid.addLayout(row1)

        exec_card = Card("Executive summary")
        self.exec_text = QTextBrowser()
        self.exec_text.setMinimumHeight(150)
        self.exec_text.setOpenExternalLinks(False)
        exec_card.add(self.exec_text)
        inc_card = Card("Top incidents")
        self.incident_list = QListWidget()
        self.incident_list.setMinimumHeight(150)
        self.incident_list.itemActivated.connect(self._open_incident)
        self.incident_list.itemClicked.connect(self._open_incident)
        inc_card.add(self.incident_list)
        row2 = QHBoxLayout()
        row2.addWidget(exec_card, 3)
        row2.addWidget(inc_card, 2)
        grid.addLayout(row2)

        charts = QGridLayout()
        charts.setSpacing(12)
        self.charts: dict[str, HBarChart] = {}
        specs = [("rules", "Top rules"), ("hosts", "Top affected hosts"), ("src", "Top source IPs"),
                 ("users", "Top users"), ("mitre", "MITRE ATT&CK techniques"), ("categories", "Behaviour categories"),
                 ("cves", "CVE"), ("iocs", "External IOC"), ("repeated", "Most repeated findings")]
        for idx, (key, title) in enumerate(specs):
            card = Card(title)
            chart = HBarChart(max_items=10)
            chart.itemClicked.connect(lambda payload, k=key: self._chart_clicked(k, payload))
            card.add(chart, 1)
            self.charts[key] = chart
            charts.addWidget(card, idx // 3, idx % 3)
        grid.addLayout(charts)
        grid.addStretch(1)
        scroll.setWidget(content)
        self.stack.addWidget(scroll)

    # ------------------------------------------------------------------
    def on_session(self, session) -> None:
        if session is None:
            self.stack.setCurrentIndex(0)
            return
        s = session.summary
        d = session.dashboard()
        self.stack.setCurrentIndex(1)
        period = f"{fmt_ts(s.first_ts, False)}  –  {fmt_ts(s.last_ts, False)}" if s.first_ts else "no timestamps"
        warn = ""
        if s.rejected_inputs:
            warn += f"<br><span style='color:{theme.SEV['high']};'>Rejected: {len(s.rejected_inputs)} input(s) " \
                    f"(see Reports › appendix)</span>"
        if s.parse_errors:
            warn += f"<br><span style='color:{theme.SEV['medium']};'>{s.parse_errors:,} malformed record(s) skipped</span>"
        self.load_text.setTextFormat(Qt.RichText)
        self.load_text.setText(
            f"<b>Files:</b> {s.files} &nbsp; <b>Events:</b> {s.events:,} &nbsp; <b>Findings:</b> {s.groups:,}<br>"
            f"<b>Time range:</b> {e(period)}<br>"
            f"<b>Agents:</b> {s.agents:,} &nbsp; <b>Rules:</b> {s.rules:,} &nbsp; <b>Duplicates removed:</b> "
            f"{s.duplicates:,}<br><b>Mode:</b> {s.mode.upper()} &nbsp; <b>Analysis time:</b> "
            f"{fmt_duration(s.duration_seconds)}<br><span style='color:{theme.MUTED};'>{e(s.enrichment_status)}</span>"
            + warn)
        for sev, card in self.sev_cards.items():
            card.set_value(s.severity_counts.get(sev, 0))
        self.metric_cards["incidents"].set_value(s.incidents)
        self.metric_cards["hosts"].set_value(s.affected_hosts)
        self.metric_cards["users"].set_value(s.affected_users)
        self.metric_cards["external"].set_value(s.external_ips)
        self.metric_cards["cves"].set_value(s.cves)
        self.metric_cards["mitre"].set_value(s.mitre_techniques)
        self.donut.set_values(s.severity_counts)
        self.timeline.set_data(d.get("timeline", {}))
        paras = "".join(f"<p>{e(p)}</p>" for p in s.executive_summary.split("\n\n"))
        self.exec_text.setHtml(paras)
        self.incident_list.clear()
        for inc in session.incidents()[:30]:
            item = QListWidgetItem(f"{inc.id}   {inc.severity.upper():<9}  {inc.risk_score:>3.0f}   {inc.title}")
            item.setData(Qt.UserRole, inc.id)
            item.setToolTip(inc.summary)
            item.setForeground(QColor(theme.severity_color(inc.severity)))
            self.incident_list.addItem(item)
        self.charts["rules"].set_items([(f"{rid}  {desc[:40]}", cnt, None, rid) for rid, desc, cnt in d.get("top_rules", [])])
        self.charts["hosts"].set_items([(h, c, None, h) for h, c in d.get("top_hosts", [])])
        self.charts["src"].set_items([(ip, c, None, ip) for ip, c in d.get("top_src_ips", [])])
        self.charts["users"].set_items([(u, c, None, u) for u, c in d.get("top_users", [])])
        mitre = session.mitre_stats()[:10]
        self.charts["mitre"].set_items([(f"{m['technique_id']} {m['name']}", m["events"],
                                         theme.SEV["high"] if m["max_risk"] >= 60 else theme.ACCENT, m["technique_id"])
                                        for m in mitre])
        self.charts["categories"].set_items([(Category.parse(c).label, n, None, c) for c, n in d.get("categories", [])])
        self.charts["cves"].set_items([(c, n, theme.SEV["high"], c) for c, n in d.get("top_cves", [])])
        verdict_color = {"malicious": theme.SEV["critical"], "suspicious": theme.SEV["medium"]}
        self.charts["iocs"].set_items([(ip, c, verdict_color.get(v), ip) for ip, c, v in d.get("top_external_ips", [])])
        self.charts["repeated"].set_items([(f"{desc[:38]} @ {agent}", cnt, theme.severity_color(sev), gid)
                                           for gid, _rid, desc, agent, cnt, sev in d.get("repeated", [])])

    def _open_incident(self, item: QListWidgetItem) -> None:
        self.ctx.navigate("incidents", incident_id=item.data(Qt.UserRole))

    def _chart_clicked(self, key: str, payload) -> None:
        if key in ("rules", "hosts", "src", "users", "cves", "iocs", "mitre"):
            self.ctx.navigate("search", term=str(payload))
        elif key == "categories":
            self.ctx.navigate("alerts", category=str(payload))
        elif key == "repeated":
            self.ctx.navigate("alerts", group_id=int(payload))
