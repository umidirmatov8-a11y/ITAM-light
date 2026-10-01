"""Rule Intelligence: local knowledge base of Wazuh rules + statistics from the current analysis."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSplitter, QTextBrowser

from app.i18n import tr
from app.core.severity import Severity
from app.database.store import GroupFilter
from app.ui import render
from app.ui.pages.base import BasePage


class RulesPage(BasePage):
    title = "Rule Intelligence"
    subtitle = "What a Wazuh rule means, typical false positives, investigation and remediation steps."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        bar = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr("Rule ID (e.g. 5710) or keyword…"))
        self.query.returnPressed.connect(self.lookup)
        self.query.textChanged.connect(lambda _t: self.populate())
        btn = QPushButton(tr("Open rule"))
        btn.clicked.connect(self.lookup)
        bar.addWidget(self.query, 1)
        bar.addWidget(btn)
        self.root.addLayout(bar)
        splitter = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda cur, _prev: cur and self.show_rule(cur.data(Qt.UserRole)))
        splitter.addWidget(self.list)
        self.detail = QTextBrowser()
        splitter.addWidget(self.detail)
        splitter.setSizes([380, 900])
        self.root.addWidget(splitter, 1)
        self.populate()

    def on_session(self, session) -> None:
        self.populate()

    def populate(self) -> None:
        text = self.query.text().strip().lower()
        self.list.clear()
        seen = set()
        observed: list[tuple[str, str, int]] = []
        if self.session is not None:
            observed = [(r, d, c) for r, d, c in self.session.dashboard().get("top_rules", [])]
        for rid, desc, cnt in observed:
            if text and text not in rid and text not in desc.lower():
                continue
            item = QListWidgetItem(f"{rid}  —  {desc}  ({cnt:,})")
            item.setData(Qt.UserRole, rid)
            self.list.addItem(item)
            seen.add(rid)
        for info in self.ctx.rule_kb.all():
            if info.rule_id in seen:
                continue
            if text and text not in info.rule_id and text not in info.description.lower():
                continue
            item = QListWidgetItem(f"{info.rule_id}  —  {info.description}")
            item.setData(Qt.UserRole, info.rule_id)
            self.list.addItem(item)

    def lookup(self) -> None:
        text = self.query.text().strip()
        if text:
            self.show_rule(text)

    def on_show(self, **kwargs) -> None:
        if kwargs.get("rule_id"):
            self.query.setText(str(kwargs["rule_id"]))
            self.show_rule(str(kwargs["rule_id"]))

    def show_rule(self, rule_id: str) -> None:
        info = self.ctx.rule_kb.get(rule_id)
        stats = None
        if self.session is not None:
            rows = self.session.store.group_rows(GroupFilter(rule_id=rule_id), 0, 5000)
            if rows:
                worst = max(rows, key=lambda r: Severity.parse(r["severity"]).rank)
                stats = {"rule_id": rule_id, "events": sum(r["count"] for r in rows), "groups": len(rows),
                         "hosts": sorted({r["agent"] for r in rows if r["agent"]}), "severity": worst["severity"]}
        if info is None and stats is None:
            stats = {"rule_id": rule_id}
        self.detail.setHtml(render.render_rule(info, stats))
