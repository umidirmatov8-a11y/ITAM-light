"""Incidents: correlated findings with triage status."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton, QSplitter,
                               QTextBrowser, QVBoxLayout, QWidget)

from app.i18n import tr
from app.i18n import severity_label, tr
from app.models.analysis import IncidentStatus
from app.ui import render
from app.ui.ai_actions import run_ai
from app.ui.pages.base import BasePage
from app.ui.widgets.table import SimpleTable
from app.utils.timeutil import fmt_ts

COLUMNS = [
    ("id", "Incident", None),
    ("severity", "Severity", lambda r: severity_label(r["severity"])),
    ("risk_score", "Risk", None),
    ("title", "Title", None),
    ("assessment", "Assessment", lambda r: tr(r["assessment"] or "")),
    ("status", "Status", lambda r: tr(r["status"])),
    ("event_count", "Events", None),
    ("hosts", "Hosts", None),
    ("first_ts", "Start", lambda r: fmt_ts(r["first_ts"])),
]


class IncidentsPage(BasePage):
    title = "Incidents"
    subtitle = "Related alerts are combined into incidents. Track triage with the status field (stored locally)."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        filters = QHBoxLayout()
        self.status_filter = QComboBox()
        self.status_filter.addItem(tr("All statuses"), "")
        for st in IncidentStatus:
            self.status_filter.addItem(tr(st.value), st.value)
        self.status_filter.currentIndexChanged.connect(lambda _i: self.refresh())
        filters.addWidget(QLabel(tr("Status:")))
        filters.addWidget(self.status_filter)
        filters.addStretch(1)
        self.root.addLayout(filters)

        splitter = QSplitter(Qt.Horizontal)
        self.table = SimpleTable(COLUMNS, 500)
        self.table.set_widths([120, 120, 50, 330, 200, 130, 70, 60, 150])
        splitter.addWidget(self.table)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        actions = QHBoxLayout()
        actions.addWidget(QLabel(tr("Status:")))
        self.status = QComboBox()
        for st in IncidentStatus:
            self.status.addItem(tr(st.value), st.value)
        self.status.activated.connect(self._change_status)
        actions.addWidget(self.status)
        self.note_btn = QPushButton(tr("Add note"))
        self.alerts_btn = QPushButton(tr("Show alerts"))
        self.ai_btn = QPushButton(tr("✨ Analyze with AI"))
        self.ai_btn.setObjectName("primary")
        for b in (self.note_btn, self.alerts_btn, self.ai_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        rl.addLayout(actions)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        rl.addWidget(self.detail, 1)
        splitter.addWidget(right)
        splitter.setSizes([700, 700])
        self.root.addWidget(splitter, 1)
        self.table.rowSelected.connect(self._show)
        self.alerts_btn.clicked.connect(self._show_alerts)
        self.note_btn.clicked.connect(self._add_note)
        self.ai_btn.clicked.connect(self._analyze)
        self.current = None

    def on_session(self, session) -> None:
        self.current = None
        self.detail.clear()
        self.refresh()

    def refresh(self) -> None:
        session = self.session
        if session is None:
            self.table.clear()
            return
        status = self.status_filter.currentData()
        rows = []
        for inc in session.incidents():
            if status and inc.status != status:
                continue
            rows.append({"id": inc.id, "severity": inc.severity, "risk_score": inc.risk_score, "title": inc.title,
                         "assessment": inc.assessment, "status": inc.status, "event_count": inc.event_count,
                         "hosts": len(inc.affected_hosts), "first_ts": inc.first_ts})
        self.table.set_rows(rows)

    def on_show(self, **kwargs) -> None:
        incident_id = kwargs.get("incident_id")
        if incident_id:
            self.status_filter.setCurrentIndex(0)
            for r, row in enumerate(self.table.model.rows):
                if row["id"] == incident_id:
                    self.table.view.selectRow(r)
                    return
            # not on the current page - render directly
            session = self.session
            inc = session.incident(incident_id) if session else None
            if inc:
                self.current = inc
                self.detail.setHtml(render.render_incident(inc))

    def _show(self, row: dict) -> None:
        session = self.session
        if session is None:
            return
        inc = session.incident(row["id"])
        self.current = inc
        if inc is None:
            return
        self.status.setCurrentIndex(max(0, self.status.findData(inc.status)))
        self.detail.setHtml(render.render_incident(inc))

    def _change_status(self, _index: int) -> None:
        if self.current is None or self.session is None:
            return
        new_status = self.status.currentData()
        self.session.set_incident_status(self.current.id, new_status, self.ctx.state)
        self.ctx.statusMessage.emit(tr("{incident} status set to {status}", incident=self.current.id,
                                       status=tr(new_status)))
        current_id = self.current.id
        self.refresh()
        self.on_show(incident_id=current_id)

    def _add_note(self) -> None:
        if self.current is None or self.session is None:
            return
        text, ok = QInputDialog.getMultiLineText(self, tr("Analyst note"), tr("Note for {incident}:", incident=self.current.id),
                                                 self.current.note)
        if ok:
            self.session.set_incident_status(self.current.id, self.current.status, self.ctx.state, text.strip())
            self.detail.setHtml(render.render_incident(self.current))

    def _show_alerts(self) -> None:
        if self.current is not None:
            self.ctx.navigate("alerts", group_ids=list(self.current.group_ids))

    def _analyze(self) -> None:
        inc = self.current
        session = self.session
        if inc is None or session is None:
            return
        groups = session.store.get_groups(inc.group_ids[:60])
        self.ai_btn.setEnabled(False)
        self.ai_btn.setText(tr("Analyzing…"))

        def reset() -> None:
            self.ai_btn.setEnabled(True)
            self.ai_btn.setText(tr("✨ Analyze with AI"))

        def done(result: dict) -> None:
            reset()
            inc.ai_analysis = result
            session.save_incident_ai(inc)
            if self.current is inc:
                self.detail.setHtml(render.render_incident(inc))
            if not result.get("ok"):
                self.ctx.statusMessage.emit(result.get("error", tr("AI analysis failed")))

        def failed(message: str) -> None:
            reset()
            QMessageBox.warning(self, tr("AI analysis"), message)

        if not run_ai(self, self.ctx, groups, inc, done, failed):
            reset()
