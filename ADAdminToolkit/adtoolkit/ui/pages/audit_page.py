"""Audit and diagnostics: selectable checks, findings with severity and evidence type, summary, export."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSplitter,
                               QVBoxLayout, QWidget)

from ...models.records import Evidence, Severity
from ...services.audit_service import AuditService
from ...services.report_service import FINDING_COLUMNS, finding_rows
from ...reports.exporters import ReportTable
from ..widgets.common import banner, report_meta, set_banner
from ..widgets.table import Column, DataTable
from .base import BasePage


class AuditPage(BasePage):
    title = "Аудит и диагностика"
    subtitle = "потенциальные проблемы безопасности и качества администрирования"

    def __init__(self, win):
        super().__init__(win)
        intro = banner("Находки делятся на «Факт» (прочитано из каталога), «Требует проверки» (индикатор, не доказательство) и "
                       "«Ограниченная точность». Неактивная учётная запись — объект для проверки, а не признак компрометации. "
                       "События безопасности DC — в разделе «Журналы безопасности».")
        intro.setVisible(True)
        self.root.addWidget(intro)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Проверки:"))
        self.checks = QListWidget()
        ll.addWidget(self.checks, 1)
        b_all = QPushButton("Отметить все")
        b_all.clicked.connect(lambda: self._check_all(True))
        b_none = QPushButton("Снять все")
        b_none.clicked.connect(lambda: self._check_all(False))
        row = QHBoxLayout()
        row.addWidget(b_all)
        row.addWidget(b_none)
        ll.addLayout(row)
        self.run_btn = QPushButton("Запустить аудит")
        self.run_btn.setProperty("primary", True)
        self.run_btn.clicked.connect(self.run_audit)
        ll.addWidget(self.run_btn)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        ll.addWidget(self.summary)
        self.check_table = DataTable([Column("title", "Проверка"), Column("count", "Находок", align_right=True),
                                      Column("status", "Статус"), Column("limitations", "Ограничения")],
                                     "audit_checks", win.db, show_toolbar=False)
        self.check_table.set_state_fn(lambda r: "danger" if r["status"].startswith("Ошибка") else None)
        ll.addWidget(self.check_table, 1)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        frow = QHBoxLayout()
        self.sev = QComboBox()
        self.sev.addItem("Любая критичность", None)
        for s in Severity:
            self.sev.addItem(s.label, s)
        self.evd = QComboBox()
        self.evd.addItem("Любой характер", None)
        for e in Evidence:
            self.evd.addItem(e.label, e)
        self.chk = QComboBox()
        self.chk.addItem("Все проверки", None)
        for w in (self.sev, self.evd, self.chk):
            w.currentIndexChanged.connect(self._apply_filter)
            frow.addWidget(w)
        frow.addStretch(1)
        exp_html = QPushButton("Отчёт HTML…")
        exp_html.clicked.connect(lambda: self._export(html=True))
        frow.addWidget(exp_html)
        rl.addLayout(frow)
        ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        cols = [Column(k, t, sort=(lambda r: ranks.get(r["severity_key"], 9)) if k == "severity" else None)
                for k, t in FINDING_COLUMNS]
        self.findings = DataTable(cols, "audit_findings", win.db,
                                  export_cb=lambda: self._export(False))
        self.findings.set_state_fn(lambda r: {"critical": "danger", "high": "danger", "medium": "warning",
                                              "info": "muted"}.get(r["severity_key"]))
        self.findings.activated.connect(self._open)
        rl.addWidget(self.findings, 1)
        split.addWidget(right)
        split.setSizes([360, 900])
        self.root.addWidget(split, 1)
        self.results = []
        self.errors = banner(danger=True)
        self.root.addWidget(self.errors)

    def on_connected(self):
        super().on_connected()
        self.checks.clear()
        self.chk.clear()
        self.chk.addItem("Все проверки", None)
        for c in AuditService(self.ctx).checks:
            item = QListWidgetItem(c.title)
            item.setToolTip(c.description)
            item.setData(Qt.UserRole, c.check_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.checks.addItem(item)
            self.chk.addItem(c.title, c.check_id)

    def on_disconnected(self):
        super().on_disconnected()
        self.findings.set_rows([])
        self.check_table.set_rows([])

    def _check_all(self, on: bool):
        for i in range(self.checks.count()):
            self.checks.item(i).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def run_audit(self):
        if not self.need_ctx():
            return
        ids = [self.checks.item(i).data(Qt.UserRole) for i in range(self.checks.count())
               if self.checks.item(i).checkState() == Qt.Checked]
        if not ids:
            self.win.toast("Не выбрано ни одной проверки", "info")
            return
        ctx = self.ctx
        self.run_btn.setEnabled(False)

        def done(results):
            self.run_btn.setEnabled(True)
            self.results = results
            summary = AuditService.summary(results)
            sev = summary["by_severity"]
            evd = summary["by_evidence"]
            self.summary.setText("<b>Итого находок: {}</b><br>".format(summary["total"]) +
                                 " · ".join(f"{s.label}: {n}" for s, n in sev.items()) + "<br>" +
                                 " · ".join(f"{e.label}: {n}" for e, n in evd.items()))
            self.check_table.set_rows([{"title": r.title, "count": len(r.findings),
                                        "status": f"Ошибка: {r.error}" if r.error else f"OK ({r.duration_s} с)",
                                        "limitations": r.limitations} for r in results])
            set_banner(self.errors, ["Не выполнены проверки: " + ", ".join(summary["failed_checks"])]
                       if summary["failed_checks"] else [])
            self._apply_filter()

        def failed(exc):
            self.run_btn.setEnabled(True)
            from ..widgets.common import show_error
            show_error(self, exc)
        self.run(lambda c, p: AuditService(ctx).run(ids, c, p), done, "Аудит домена", on_error=failed)

    def _filtered(self) -> list[dict]:
        rows = finding_rows(self.results)
        sev, evd, chk = self.sev.currentData(), self.evd.currentData(), self.chk.currentData()
        sev = Severity(sev) if sev else None
        evd = Evidence(evd) if evd else None
        titles = {r.check_id: r.title for r in self.results}
        if sev is not None:
            rows = [r for r in rows if r["severity_key"] == sev.value]
        if evd is not None:
            rows = [r for r in rows if r["evidence"] == evd.label]
        if chk is not None:
            rows = [r for r in rows if r["check"] == titles.get(chk)]
        return rows

    def _apply_filter(self):
        self.findings.set_rows(self._filtered())

    def _open(self, r):
        if not r or not r.get("dn") or self.ctx is None:
            return
        e = self.ctx.gateway.get(r["dn"], ["objectClass"])
        if e is None:
            return
        classes = e.object_classes
        if "computer" in classes:
            self.win.open_computer(r["dn"])
        elif "group" in classes:
            self.win.open_group(r["dn"])
        elif "user" in classes:
            self.win.open_user(r["dn"])

    def _export(self, html: bool):
        if not self.results:
            self.win.toast("Сначала запустите аудит", "info")
            return
        info = self.ctx.gateway.info if self.ctx else None
        summary = AuditService.summary(self.results)
        checks = report_meta(ReportTable("Проверки аудита", [("check", "Проверка"), ("findings", "Находок"), ("error", "Ошибка"),
                                                             ("limitations", "Ограничения")],
                                         [{"check": r.title, "findings": len(r.findings), "error": r.error,
                                           "limitations": r.limitations} for r in self.results]), info)
        findings = report_meta(ReportTable("Находки аудита", list(FINDING_COLUMNS), self._filtered(),
                                           {"Критичность": self.sev.currentText(), "Характер": self.evd.currentText(),
                                            "Проверка": self.chk.currentText()},
                                           ["«Требует проверки» — индикатор для анализа, а не доказательство нарушения."]), info)
        kpis = [(s.label, str(n)) for s, n in summary["by_severity"].items()]
        self.export([checks, findings], "audit", html=html, kpis=kpis, title="Сводный отчёт аудита Active Directory")
