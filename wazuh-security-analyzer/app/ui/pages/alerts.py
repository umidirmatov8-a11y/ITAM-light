"""Alerts: grouped findings (cards) and raw events, with filters and pagination."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QHBoxLayout, QLineEdit, QMessageBox, QPushButton,
                               QRadioButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from app.i18n import tr
from app.i18n import severity_label, tr
from app.core.severity import SEVERITY_ORDER
from app.database.store import GroupFilter
from app.models.categories import CATEGORY_LABELS
from app.ui import render
from app.ui.ai_actions import run_ai
from app.ui.pages.base import BasePage
from app.ui.widgets.table import PagedTable
from app.utils.timeutil import fmt_ts

GROUP_COLUMNS = [
    ("id", "ID", lambda r: f"#{r['id']:05d}"),
    ("severity", "Severity", lambda r: severity_label(r["severity"])),
    ("risk_score", "Risk", None),
    ("title", "Finding", None),
    ("agent", "Host", None),
    ("src_ip", "Source", None),
    ("user", "User", None),
    ("count", "Count", None),
    ("assessment", "Assessment", lambda r: tr(r["assessment"] or "")),
    ("fp_probability", "FP", lambda r: f"{r['fp_probability']:.0%}"),
    ("first_ts", "First seen", lambda r: fmt_ts(r["first_ts"])),
    ("rule_id", "Rule", None),
    ("incident_id", "Incident", None),
]
EVENT_COLUMNS = [
    ("id", "#", None),
    ("ts", "Time", lambda r: fmt_ts(r["ts"])),
    ("severity", "Severity", lambda r: severity_label(r.get("severity") or "")),
    ("rule_id", "Rule", None),
    ("level", "Lvl", None),
    ("description", "Description", None),
    ("agent", "Host", None),
    ("src_ip", "Source IP", None),
    ("user", "User", None),
    ("process", "Process", None),
]


class AlertsPage(BasePage):
    title = "Alerts"
    subtitle = "Repeated alerts are grouped into findings. Select a finding to see the explanation, evidence and actions."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.group_ids: list[int] | None = None
        self.event_group: int | None = None

        bar = QHBoxLayout()
        self.mode_findings = QRadioButton(tr("Findings"))
        self.mode_events = QRadioButton(tr("Raw events"))
        self.mode_findings.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.mode_findings)
        grp.addButton(self.mode_events)
        self.severity = QComboBox()
        self.severity.addItem(tr("All severities"), "")
        for s in SEVERITY_ORDER:
            self.severity.addItem(severity_label(s.value, upper=False), s.value)
        self.category = QComboBox()
        self.category.addItem(tr("All categories"), "")
        for cat, lbl in CATEGORY_LABELS.items():
            self.category.addItem(tr(lbl), cat.value)
        self.text = QLineEdit()
        self.text.setPlaceholderText(tr("Filter: host, IP, user, rule ID, CVE, MITRE ID, text…"))
        self.text.returnPressed.connect(self.apply)
        apply_btn = QPushButton(tr("Apply"))
        apply_btn.clicked.connect(self.apply)
        self.clear_btn = QPushButton(tr("Clear filters"))
        self.clear_btn.clicked.connect(self.clear_filters)
        for w in (self.mode_findings, self.mode_events, self.severity, self.category):
            bar.addWidget(w)
        bar.addWidget(self.text, 1)
        bar.addWidget(apply_btn)
        bar.addWidget(self.clear_btn)
        self.root.addLayout(bar)
        self.mode_findings.toggled.connect(lambda _c: self.apply())
        self.severity.currentIndexChanged.connect(lambda _i: self.apply())
        self.category.currentIndexChanged.connect(lambda _i: self.apply())

        splitter = QSplitter(Qt.Horizontal)
        page_size = ctx.config.ui.page_size
        self.findings = PagedTable(GROUP_COLUMNS, page_size)
        self.findings.set_widths([70, 120, 50, 320, 110, 120, 100, 70, 190, 50, 150, 60, 110])
        self.events = PagedTable(EVENT_COLUMNS, page_size)
        self.events.set_widths([70, 150, 120, 60, 40, 360, 110, 120, 100, 200])
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.findings)
        ll.addWidget(self.events)
        self.events.hide()
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        actions = QHBoxLayout()
        self.ai_btn = QPushButton(tr("✨ Analyze with AI"))
        self.ai_btn.setObjectName("primary")
        self.events_btn = QPushButton(tr("Show events"))
        self.incident_btn = QPushButton(tr("Open incident"))
        for b in (self.ai_btn, self.events_btn, self.incident_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        rl.addLayout(actions)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        rl.addWidget(self.detail, 1)
        splitter.addWidget(right)
        splitter.setSizes([780, 620])
        self.root.addWidget(splitter, 1)

        self.findings.rowSelected.connect(self._show_group)
        self.events.rowSelected.connect(self._show_event)
        self.ai_btn.clicked.connect(self._analyze_ai)
        self.events_btn.clicked.connect(self._show_group_events)
        self.incident_btn.clicked.connect(self._open_incident)
        self.current_group = None

    # ------------------------------------------------------------------ data
    def on_session(self, session) -> None:
        self.group_ids = None
        self.event_group = None
        if session is None:
            self.findings.clear()
            self.events.clear()
            self.detail.clear()
            return
        self.apply()

    def on_show(self, **kwargs) -> None:
        if not kwargs or self.session is None:
            return
        self.blockSignals(True)
        self.group_ids = kwargs.get("group_ids")
        self.event_group = None
        if "group_id" in kwargs:
            self.group_ids = [int(kwargs["group_id"])]
        self._set_combo(self.severity, kwargs.get("severity", ""))
        self._set_combo(self.category, kwargs.get("category", ""))
        self.text.setText(kwargs.get("text", ""))
        self.mode_findings.setChecked(True)
        self.blockSignals(False)
        self.apply()

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        combo.blockSignals(True)
        idx = combo.findData(value)
        combo.setCurrentIndex(max(idx, 0))
        combo.blockSignals(False)

    def clear_filters(self) -> None:
        self.group_ids = None
        self.event_group = None
        self._set_combo(self.severity, "")
        self._set_combo(self.category, "")
        self.text.clear()
        self.apply()

    def _filter(self) -> GroupFilter:
        sev = self.severity.currentData()
        cat = self.category.currentData()
        return GroupFilter(severities=[sev] if sev else [], categories=[cat] if cat else [],
                           text=self.text.text().strip(), group_ids=self.group_ids)

    def apply(self) -> None:
        session = self.session
        if session is None:
            return
        store = session.store
        findings_mode = self.mode_findings.isChecked()
        self.findings.setVisible(findings_mode)
        self.events.setVisible(not findings_mode)
        self.clear_btn.setText(tr("Clear filters") + (tr(" (selection active)") if self.group_ids or self.event_group
                                                      else ""))
        if findings_mode:
            f = self._filter()
            self.findings.set_source(lambda off, lim: store.group_rows(f, off, lim), lambda: store.count_groups(f))
        else:
            sev = self.severity.currentData() or None
            text = self.text.text().strip()
            gid = self.event_group
            self.events.set_source(
                lambda off, lim: store.query_alerts(gid, sev, text, off, lim),
                lambda: store.count_alerts(gid, sev, text))

    # ------------------------------------------------------------------ details
    def _show_group(self, row: dict) -> None:
        session = self.session
        if session is None:
            return
        group = session.group(row["id"])
        self.current_group = group
        if group is None:
            return
        self.detail.setHtml(render.render_group(group, self.ctx.rule_kb.get(group.rule_id)))
        self.incident_btn.setEnabled(bool(group.incident_id))

    def _show_event(self, row: dict) -> None:
        session = self.session
        if session is None:
            return
        detail = session.store.alert_detail(row["id"])
        if detail:
            self.detail.setHtml(render.render_raw_alert(detail))

    def _show_group_events(self) -> None:
        if self.current_group is None:
            return
        self.event_group = self.current_group.id
        self.mode_events.setChecked(True)
        self.apply()

    def _open_incident(self) -> None:
        if self.current_group is not None and self.current_group.incident_id:
            self.ctx.navigate("incidents", incident_id=self.current_group.incident_id)

    def _analyze_ai(self) -> None:
        group = self.current_group
        session = self.session
        if group is None or session is None:
            return
        related = []
        if group.incident_id:
            incident = session.incident(group.incident_id)
            if incident:
                related = [g for g in session.store.get_groups(incident.group_ids[:50]) if g.id != group.id]
        self.ai_btn.setEnabled(False)
        self.ai_btn.setText(tr("Analyzing…"))

        def done(result: dict) -> None:
            self.ai_btn.setEnabled(True)
            self.ai_btn.setText(tr("✨ Analyze with AI"))
            group.ai_analysis = result
            session.store.update_group(group)
            if self.current_group is group:
                self.detail.setHtml(render.render_group(group, self.ctx.rule_kb.get(group.rule_id)))
            if not result.get("ok"):
                self.ctx.statusMessage.emit(result.get("error", tr("AI analysis failed")))

        def failed(message: str) -> None:
            self.ai_btn.setEnabled(True)
            self.ai_btn.setText(tr("✨ Analyze with AI"))
            QMessageBox.warning(self, tr("AI analysis"), message)

        if not run_ai(self, self.ctx, [group] + related, None, done, failed):
            self.ai_btn.setEnabled(True)
            self.ai_btn.setText(tr("✨ Analyze with AI"))
