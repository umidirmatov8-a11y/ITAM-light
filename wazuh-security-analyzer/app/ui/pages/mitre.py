"""MITRE ATT&CK matrix view (tactics as columns, observed techniques as cells)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextBrowser)

from app.i18n import n, num, tr
from app.ui import render, theme
from app.ui.pages.base import BasePage


class MitrePage(BasePage):
    title = "MITRE ATT&CK"
    subtitle = ("Techniques observed in the analyzed alerts. Colour = highest risk; confidence shows how the mapping was "
                "derived (Wazuh rule = high, knowledge base = medium, behavioural evidence = medium/low).")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        splitter = QSplitter(Qt.Vertical)
        self.matrix = QTableWidget()
        self.matrix.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.matrix.verticalHeader().setVisible(False)
        self.matrix.setWordWrap(True)
        self.matrix.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.matrix.horizontalHeader().setMinimumSectionSize(170)
        self.matrix.horizontalHeader().setDefaultSectionSize(185)
        self.matrix.cellClicked.connect(self._cell)
        splitter.addWidget(self.matrix)
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        self.detail.anchorClicked.connect(self._anchor)
        splitter.addWidget(self.detail)
        splitter.setSizes([520, 280])
        self.root.addWidget(splitter, 1)
        self.stats: dict[str, dict] = {}

    def on_session(self, session) -> None:
        self.matrix.clear()
        self.detail.clear()
        self.stats = {s["technique_id"]: s for s in (session.mitre_stats() if session else [])}
        tactics = [t for t in self.ctx.catalog.tactic_order
                   if any(t in s["tactics"] for s in self.stats.values())]
        if not tactics:
            self.matrix.setRowCount(0)
            self.matrix.setColumnCount(0)
            return
        columns: dict[str, list[dict]] = {t: [] for t in tactics}
        for s in self.stats.values():
            for t in s["tactics"]:
                if t in columns:
                    columns[t].append(s)
        rows = max(len(v) for v in columns.values())
        self.matrix.setColumnCount(len(tactics))
        self.matrix.setRowCount(rows)
        self.matrix.setHorizontalHeaderLabels([tr(self.ctx.catalog.tactic_name(t)) for t in tactics])
        for c, tactic in enumerate(tactics):
            for r, s in enumerate(sorted(columns[tactic], key=lambda x: -x["max_risk"])):
                item = QTableWidgetItem(f"{s['technique_id']}\n{s['name']}\n{n(s['events'], 'event')} · "
                                        f"{tr(s['confidence'])}")
                item.setData(Qt.UserRole, s["technique_id"])
                sev = "critical" if s["max_risk"] >= 80 else "high" if s["max_risk"] >= 60 else \
                    "medium" if s["max_risk"] >= 40 else "low" if s["max_risk"] >= 20 else "informational"
                color = QColor(theme.severity_color(sev))
                color.setAlpha(90)
                item.setBackground(color)
                item.setToolTip("; ".join(s.get("evidence", [])))
                self.matrix.setItem(r, c, item)
        self.matrix.resizeRowsToContents()

    def _cell(self, row: int, col: int) -> None:
        item = self.matrix.item(row, col)
        if item is None:
            return
        tid = item.data(Qt.UserRole)
        s = self.stats.get(tid)
        if not s:
            return
        html = [f'<p style="font-size:14pt; font-weight:bold;">{render.e(tid)} — {render.e(s["name"])}</p>',
                render.kv_table([("Tactics", ", ".join(tr(self.ctx.catalog.tactic_name(t)) for t in s["tactics"])),
                                 ("Events", num(s['events'])), ("Findings", s["groups"]),
                                 ("Highest risk", f"{s['max_risk']:.0f}"),
                                 ("Mapping confidence", tr(s["confidence"])),
                                 ("Mapping sources", ", ".join(s["sources"])),
                                 ("Hosts", ", ".join(s["hosts"][:15]))]),
                render.h("Evidence"), render.bullets(s.get("evidence", [])),
                f'<p><a href="{render.e(s["url"])}" style="color:{theme.ACCENT};">{render.e(s["url"])}</a></p>',
                '<p><a href="search:' + render.e(tid) + f'" style="color:{theme.ACCENT};">{render.e(tr("Show related alerts"))} →</a></p>']
        self.detail.setHtml("".join(html))

    def _anchor(self, url) -> None:
        text = url.toString()
        if text.startswith("search:"):
            self.ctx.navigate("search", term=text[7:])
        else:
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)
