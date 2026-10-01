"""Hosts and Users pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget

from app.i18n import tr
from app.i18n import severity_label, tr
from app.database.store import GroupFilter
from app.ui import render
from app.ui.pages.base import BasePage
from app.ui.widgets.table import SimpleTable
from app.utils.timeutil import fmt_ts


class EntitiesPage(BasePage):
    def __init__(self, ctx, kind: str, parent=None):
        self.kind = kind
        self.title = "Hosts" if kind == "host" else "Users"
        self.subtitle = ("Monitored agents ranked by the highest risk of their findings." if kind == "host" else
                         "Accounts seen in alerts, ranked by risk.")
        super().__init__(ctx, parent)
        bar = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Filter hosts…") if kind == "host" else tr("Filter users…"))
        self.filter.textChanged.connect(lambda _t: self.refresh())
        bar.addWidget(self.filter, 1)
        self.alerts_btn = QPushButton(tr("Show alerts"))
        self.alerts_btn.clicked.connect(self._show_alerts)
        bar.addWidget(self.alerts_btn)
        self.root.addLayout(bar)
        columns = [("name", "Host" if kind == "host" else "Account", None),
                   ("severity", "Severity", lambda r: severity_label(r["severity"])),
                   ("max_risk", "Max risk", None), ("events", "Events", None), ("groups", "Findings", None),
                   ("incidents", "Incidents", None),
                   ("extra", "Criticality" if kind == "host" else "Hosts", None),
                   ("last_ts", "Last seen", lambda r: fmt_ts(r["last_ts"]))]
        splitter = QSplitter(Qt.Horizontal)
        self.table = SimpleTable(columns, 1000)
        self.table.set_widths([200, 90, 70, 80, 70, 70, 140, 160])
        splitter.addWidget(self.table)
        self.detail = QTextBrowser()
        splitter.addWidget(self.detail)
        splitter.setSizes([700, 600])
        self.root.addWidget(splitter, 1)
        self.table.rowSelected.connect(self._show)
        self._rows: list[dict] = []
        self.current = None

    def on_session(self, session) -> None:
        self._rows = []
        if session is not None:
            for ent in session.store.entities(self.kind):
                data = ent["data"]
                ent["extra"] = tr(data.get("criticality", "")) if self.kind == "host" else \
                    ", ".join(data.get("hosts", [])[:3])
                self._rows.append(ent)
        self.detail.clear()
        self.refresh()

    def refresh(self) -> None:
        if self.session is None:
            self.table.clear()
            return
        text = self.filter.text().strip().lower()
        self.table.set_rows([r for r in self._rows if not text or text in r["name"].lower()])

    def on_show(self, **kwargs) -> None:
        name = kwargs.get("name")
        if name:
            self.filter.setText(name)

    def _filter_for(self, name: str) -> GroupFilter:
        return GroupFilter(agent=name) if self.kind == "host" else GroupFilter(user=name)

    def _show(self, row: dict) -> None:
        session = self.session
        if session is None:
            return
        self.current = row
        groups = session.store.query_groups(self._filter_for(row["name"]), 0, 25)
        self.detail.setHtml(render.render_entity(self.kind, row, groups))

    def _show_alerts(self) -> None:
        if self.current is None or self.session is None:
            return
        f = self._filter_for(self.current["name"])
        ids = [r["id"] for r in self.session.store.group_rows(f, 0, 5000)]
        self.ctx.navigate("alerts", group_ids=ids)
