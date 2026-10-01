"""IOC and CVE pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QSplitter,
                               QTextBrowser)

from app.intelligence.enrichment import EnrichmentService
from app.ui import render, workers
from app.ui.pages.base import BasePage
from app.ui.widgets.table import SimpleTable
from app.utils.timeutil import fmt_ts

IOC_COLUMNS = [("type", "Type", None), ("value", "Value", None), ("verdict", "Verdict", None),
               ("count", "Occurrences", None), ("hosts", "Hosts", lambda r: ", ".join(r["hosts"][:3])),
               ("country", "Country", None), ("scope", "Scope", lambda r: "internal" if r["internal"] else "external"),
               ("sources", "Sources", lambda r: ", ".join(s.get("provider", "") for s in r["sources"][:3])),
               ("last_seen", "Last seen", lambda r: fmt_ts(r["last_seen"]))]
CVE_COLUMNS = [("cve", "CVE", None), ("cvss", "CVSS", lambda r: "" if r["cvss"] is None else f"{r['cvss']:.1f}"),
               ("severity", "Severity", lambda r: (r["severity"] or "").upper()),
               ("known_exploited", "Known exploited", lambda r: "YES" if r["known_exploited"] else ""),
               ("hosts", "Hosts", lambda r: len(r["hosts"])), ("packages", "Packages", lambda r: ", ".join(r["packages"][:2])),
               ("count", "Alerts", None)]


class IOCPage(BasePage):
    title = "Indicators of Compromise"
    subtitle = "IPs, domains, URLs and file hashes extracted from alerts, with local and online reputation."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        bar = QHBoxLayout()
        self.type_filter = QComboBox()
        self.type_filter.addItem("All types", "")
        for t in ("ip", "domain", "url", "sha256", "sha1", "md5"):
            self.type_filter.addItem(t.upper(), t)
        self.verdict_filter = QComboBox()
        self.verdict_filter.addItem("All verdicts", "")
        for v in ("malicious", "suspicious", "clean", "unknown"):
            self.verdict_filter.addItem(v.capitalize(), v)
        self.internal = QCheckBox("Include internal")
        self.text = QLineEdit()
        self.text.setPlaceholderText("Filter value…")
        self.enrich_btn = QPushButton("\U0001F310 Enrich selected online")
        self.enrich_btn.setObjectName("primary")
        for w in (self.type_filter, self.verdict_filter, self.internal):
            bar.addWidget(w)
        bar.addWidget(self.text, 1)
        bar.addWidget(self.enrich_btn)
        self.root.addLayout(bar)
        for sig in (self.type_filter.currentIndexChanged, self.verdict_filter.currentIndexChanged):
            sig.connect(lambda _i: self.refresh())
        self.internal.toggled.connect(lambda _c: self.refresh())
        self.text.textChanged.connect(lambda _t: self.refresh())
        splitter = QSplitter(Qt.Horizontal)
        self.table = SimpleTable(IOC_COLUMNS, 1000)
        self.table.set_widths([60, 300, 90, 90, 160, 70, 70, 160, 150])
        splitter.addWidget(self.table)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        splitter.addWidget(self.detail)
        splitter.setSizes([800, 500])
        self.root.addWidget(splitter, 1)
        self.table.rowSelected.connect(self._show)
        self.table.rowActivated.connect(lambda r: self.ctx.navigate("search", term=r["value"]))
        self.enrich_btn.clicked.connect(self._enrich)
        self.records = []
        self._by_key = {}

    def on_session(self, session) -> None:
        self.records = session.store.iocs() if session else []
        self._by_key = {(r.type, r.value): r for r in self.records}
        self.detail.clear()
        self.refresh()

    def refresh(self) -> None:
        t = self.type_filter.currentData()
        v = self.verdict_filter.currentData()
        text = self.text.text().strip().lower()
        rows = []
        for r in self.records:
            if (r.internal and not self.internal.isChecked()) or (t and r.type != t) or (v and r.verdict != v):
                continue
            if text and text not in r.value.lower():
                continue
            rows.append(r.to_dict())
        self.table.set_rows(rows)

    def _show(self, row: dict) -> None:
        rec = self._by_key.get((row["type"], row["value"]))
        if rec:
            self.detail.setHtml(render.render_ioc(rec))

    def _enrich(self) -> None:
        row = self.table.current_row()
        if row is None or self.session is None:
            return
        rec = self._by_key.get((row["type"], row["value"]))
        if rec is None or rec.internal:
            QMessageBox.information(self, "Enrichment", "Internal indicators are never sent to external services.")
            return
        if QMessageBox.question(self, "Online enrichment",
                                f"Send the public indicator {rec.value} to the enabled threat-intelligence providers "
                                "(VirusTotal / AbuseIPDB / OTX)?") != QMessageBox.Yes:
            return
        service = EnrichmentService(self.ctx.config, self.ctx.secrets, self.ctx.state)

        def job(progress, cancel):
            return service.enrich([rec], [], online=True)

        def done(report) -> None:
            self.enrich_btn.setEnabled(True)
            self.session.store.save_iocs(self.records)
            self._show(row)
            self.refresh()
            msg = report.status + (("\n\n" + "\n".join(report.errors[:5])) if report.errors else "")
            msg += "\n\nRisk scores of related findings are recalculated on the next analysis run."
            if not report.providers_used:
                msg += "\n\nNo reputation provider is enabled. Configure API keys in Settings › Threat intelligence."
            QMessageBox.information(self, "Enrichment", msg)

        self.enrich_btn.setEnabled(False)
        task = workers.Task(job)
        task.signals.finished.connect(done)
        task.signals.failed.connect(lambda m: (self.enrich_btn.setEnabled(True),
                                               QMessageBox.warning(self, "Enrichment", m)))
        workers.start(task)


class CVEPage(BasePage):
    title = "Vulnerabilities (CVE)"
    subtitle = "CVE found in Wazuh vulnerability-detector alerts and log text. ONLINE mode adds NVD and CISA KEV data."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        bar = QHBoxLayout()
        self.text = QLineEdit()
        self.text.setPlaceholderText("Filter CVE / package…")
        self.text.textChanged.connect(lambda _t: self.refresh())
        self.kev_only = QCheckBox("Known exploited only")
        self.kev_only.toggled.connect(lambda _c: self.refresh())
        self.enrich_btn = QPushButton("\U0001F310 Fetch NVD / KEV for selected")
        self.enrich_btn.clicked.connect(self._enrich)
        bar.addWidget(self.text, 1)
        bar.addWidget(self.kev_only)
        bar.addWidget(self.enrich_btn)
        self.root.addLayout(bar)
        splitter = QSplitter(Qt.Horizontal)
        self.table = SimpleTable(CVE_COLUMNS, 1000)
        self.table.set_widths([140, 50, 80, 110, 50, 220, 60])
        splitter.addWidget(self.table)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        splitter.addWidget(self.detail)
        splitter.setSizes([700, 600])
        self.root.addWidget(splitter, 1)
        self.table.rowSelected.connect(self._show)
        self.table.rowActivated.connect(lambda r: self.ctx.navigate("search", term=r["cve"]))
        self.records = []

    def on_session(self, session) -> None:
        self.records = session.store.cves() if session else []
        self.detail.clear()
        self.refresh()

    def refresh(self) -> None:
        text = self.text.text().strip().lower()
        rows = [c.to_dict() for c in self.records
                if (not self.kev_only.isChecked() or c.known_exploited)
                and (not text or text in c.cve.lower() or any(text in p.lower() for p in c.packages))]
        self.table.set_rows(rows)

    def _show(self, row: dict) -> None:
        rec = next((c for c in self.records if c.cve == row["cve"]), None)
        if rec:
            self.detail.setHtml(render.render_cve(rec))

    def _enrich(self) -> None:
        row = self.table.current_row()
        if row is None or self.session is None:
            return
        rec = next((c for c in self.records if c.cve == row["cve"]), None)
        if rec is None:
            return
        service = EnrichmentService(self.ctx.config, self.ctx.secrets, self.ctx.state)

        def job(progress, cancel):
            return service.enrich([], [rec], online=True)

        def done(report) -> None:
            self.enrich_btn.setEnabled(True)
            self.session.store.save_cves(self.records)
            self._show(row)
            self.refresh()
            self.ctx.statusMessage.emit(report.status)
            if report.errors:
                QMessageBox.warning(self, "CVE enrichment", report.status + "\n\n" + "\n".join(report.errors[:5]))

        self.enrich_btn.setEnabled(False)
        task = workers.Task(job)
        task.signals.finished.connect(done)
        task.signals.failed.connect(lambda m: (self.enrich_btn.setEnabled(True),
                                               QMessageBox.warning(self, "CVE enrichment", m)))
        workers.start(task)
