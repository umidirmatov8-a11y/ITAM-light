"""Report export page."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLineEdit, QListWidget,
                               QMessageBox, QPushButton, QTextBrowser, QVBoxLayout)

from app.core import paths
from app.reports.data import ALL_SECTIONS
from app.reports.exporters import export_report
from app.ui import workers
from app.ui.pages.base import BasePage
from app.ui.render import e

FORMAT_LABELS = [("pdf", "PDF"), ("html", "HTML"), ("docx", "Word (DOCX)"), ("xlsx", "Excel"), ("csv", "CSV"),
                 ("json", "JSON")]
SECTION_LABELS = {"executive_summary": "Executive Summary", "statistics": "Statistics",
                  "critical_alerts": "Critical alerts", "incidents": "Incidents", "hosts": "Affected hosts",
                  "users": "Users", "iocs": "IOC", "cves": "CVE", "mitre": "MITRE ATT&CK",
                  "recommendations": "Recommendations", "timeline": "Timeline", "appendix": "Technical appendix"}


class ReportsPage(BasePage):
    title = "Reports"
    subtitle = "Export the analysis for management (Executive Summary) and for the SOC team (technical appendix)."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        top = QHBoxLayout()
        fmt_box = QGroupBox("Formats")
        fl = QVBoxLayout(fmt_box)
        self.formats: dict[str, QCheckBox] = {}
        for key, lbl in FORMAT_LABELS:
            cb = QCheckBox(lbl)
            cb.setChecked(key in ("pdf", "html"))
            self.formats[key] = cb
            fl.addWidget(cb)
        top.addWidget(fmt_box)
        sec_box = QGroupBox("Sections")
        sl = QGridLayout(sec_box)
        self.sections: dict[str, QCheckBox] = {}
        for i, key in enumerate(ALL_SECTIONS):
            cb = QCheckBox(SECTION_LABELS[key])
            cb.setChecked(True)
            self.sections[key] = cb
            sl.addWidget(cb, i // 3, i % 3)
        top.addWidget(sec_box, 1)
        self.root.addLayout(top)
        out = QHBoxLayout()
        self.title_edit = QLineEdit("Wazuh Security Analysis Report")
        self.dir_edit = QLineEdit(str(paths.reports_dir()))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        self.export_btn = QPushButton("Export report")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self._export)
        out.addWidget(self.title_edit, 2)
        out.addWidget(self.dir_edit, 3)
        out.addWidget(browse)
        out.addWidget(self.export_btn)
        self.root.addLayout(out)
        self.results = QListWidget()
        self.results.setMaximumHeight(140)
        self.results.itemDoubleClicked.connect(lambda item: QDesktopServices.openUrl(QUrl.fromLocalFile(item.text())))
        self.root.addWidget(self.results)
        self.preview = QTextBrowser()
        self.root.addWidget(self.preview, 1)

    def on_session(self, session) -> None:
        if session is None:
            self.preview.clear()
            return
        s = session.summary
        self.preview.setHtml("<h3>Executive Summary preview</h3>" + "".join(
            f"<p>{e(p)}</p>" for p in s.executive_summary.split("\n\n")))

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output folder", self.dir_edit.text())
        if folder:
            self.dir_edit.setText(folder)

    def _export(self) -> None:
        session = self.session
        if session is None:
            QMessageBox.information(self, "Reports", "Load and analyze alerts first.")
            return
        formats = [k for k, cb in self.formats.items() if cb.isChecked()]
        sections = tuple(k for k, cb in self.sections.items() if cb.isChecked())
        if not formats:
            QMessageBox.information(self, "Reports", "Select at least one format.")
            return
        out_dir = Path(self.dir_edit.text()).expanduser()
        base = "wazuh_report_" + time.strftime("%Y%m%d_%H%M%S")
        title = self.title_edit.text().strip() or "Wazuh Security Analysis Report"
        self.export_btn.setEnabled(False)
        self.export_btn.setText("Exporting…")

        def job(progress, cancel):
            return export_report(session, out_dir, formats, base, sections, title)

        def done(paths_written) -> None:
            self.export_btn.setEnabled(True)
            self.export_btn.setText("Export report")
            for p in paths_written:
                self.results.insertItem(0, str(p))
            self.ctx.statusMessage.emit(f"Report exported to {out_dir}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

        def failed(message: str) -> None:
            self.export_btn.setEnabled(True)
            self.export_btn.setText("Export report")
            QMessageBox.critical(self, "Export failed", message)

        task = workers.Task(job)
        task.signals.finished.connect(done)
        task.signals.failed.connect(failed)
        workers.start(task)
