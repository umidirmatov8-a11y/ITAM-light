"""Main window: sidebar navigation, global search, mode indicator, background analysis."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QStackedWidget, QStatusBar, QVBoxLayout, QWidget)

from app import __app_name__, __version__
from app.ai.providers.factory import PROVIDER_LABELS
from app.core import paths
from app.core.errors import AnalysisCancelled
from app.services.pipeline import AnalysisPipeline, Progress
from app.ui import theme, workers
from app.ui.context import AppContext
from app.ui.onboarding import OnboardingDialog
from app.ui.pages.alerts import AlertsPage
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.entities import EntitiesPage
from app.ui.pages.incidents import IncidentsPage
from app.ui.pages.intel import CVEPage, IOCPage
from app.ui.pages.mitre import MitrePage
from app.ui.pages.reports import ReportsPage
from app.ui.pages.rules import RulesPage
from app.ui.pages.search import SearchPage
from app.ui.pages.settings import SettingsPage

log = logging.getLogger(__name__)

NAV = [
    ("dashboard", "▣  Dashboard"),
    ("alerts", "⚠  Alerts"),
    ("incidents", "⚑  Incidents"),
    ("hosts", "🖥  Hosts"),
    ("users", "👤  Users"),
    ("ioc", "◉  IOC"),
    ("cve", "☢  CVE"),
    ("mitre", "▦  MITRE ATT&&CK"),
    ("rules", "ℹ  Rule Intelligence"),
    ("reports", "📄  Reports"),
    ("settings", "⚙  Settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.task: workers.Task | None = None
        self.setWindowTitle(f"{__app_name__} {__version__}")
        icon = paths.resources_dir() / "icons" / "app.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1480, 920)
        self.setMinimumSize(1100, 700)
        self.setAcceptDrops(True)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._build_topbar())
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        root.addLayout(right, 1)
        self.setCentralWidget(central)

        self.pages = {
            "dashboard": DashboardPage(ctx),
            "alerts": AlertsPage(ctx),
            "incidents": IncidentsPage(ctx),
            "hosts": EntitiesPage(ctx, "host"),
            "users": EntitiesPage(ctx, "user"),
            "ioc": IOCPage(ctx),
            "cve": CVEPage(ctx),
            "mitre": MitrePage(ctx),
            "rules": RulesPage(ctx),
            "reports": ReportsPage(ctx),
            "settings": SettingsPage(ctx),
            "search": SearchPage(ctx),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        dash: DashboardPage = self.pages["dashboard"]  # type: ignore[assignment]
        dash.pathsSelected.connect(self.start_analysis)
        dash.demoRequested.connect(self.load_demo)

        self._build_statusbar()
        ctx.navigateRequested.connect(self.navigate)
        ctx.statusMessage.connect(lambda msg: self.status_label.setText(msg))
        ctx.configChanged.connect(self._refresh_badges)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search.setFocus())
        QShortcut(QKeySequence("Ctrl+O"), self, activated=lambda: dash.drop.btn_files.click())
        self._refresh_badges()
        self.navigate("dashboard", {})

    # ------------------------------------------------------------------ layout
    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(10, 16, 10, 12)
        lay.setSpacing(3)
        brand = QLabel("\U0001F6E1 Wazuh Security\nAnalyzer")
        brand.setObjectName("brand")
        lay.addWidget(brand)
        sub = QLabel(f"SOC analysis assistant · v{__version__}")
        sub.setObjectName("brandSub")
        lay.addWidget(sub)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for key, text in NAV:
            btn = QPushButton(text)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, k=key: self.navigate(k, {}))
            self.nav_group.addButton(btn)
            self.nav_buttons[key] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        logs_btn = QPushButton("Open logs folder")
        logs_btn.setObjectName("navButton")
        logs_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.logs_dir()))))
        lay.addWidget(logs_btn)
        return side

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        self.search = QLineEdit()
        self.search.setObjectName("globalSearch")
        self.search.setPlaceholderText("\U0001F50D  Search IP, user, host, rule ID, CVE, hash, domain, MITRE ID  (Ctrl+F)")
        self.search.returnPressed.connect(lambda: self.navigate("search", {"term": self.search.text().strip()}))
        lay.addWidget(self.search, 1)
        lay.addStretch(0)
        self.mode_badge = QPushButton("")
        self.mode_badge.setCursor(Qt.PointingHandCursor)
        self.mode_badge.setToolTip("Click to switch between OFFLINE and ONLINE analysis")
        self.mode_badge.clicked.connect(self._toggle_mode)
        self.ai_badge = QPushButton("")
        self.ai_badge.setCursor(Qt.PointingHandCursor)
        self.ai_badge.clicked.connect(lambda: self.navigate("settings", {}))
        lay.addWidget(self.mode_badge)
        lay.addWidget(self.ai_badge)
        return bar

    def _build_statusbar(self) -> None:
        status = QStatusBar()
        self.status_label = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(380)
        self.progress.setRange(0, 1000)
        self.progress.hide()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(self._cancel)
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.progress)
        status.addPermanentWidget(self.cancel_btn)
        self.setStatusBar(status)

    def _refresh_badges(self) -> None:
        cfg = self.ctx.config
        online = cfg.network.online
        color = theme.SUCCESS if online else theme.MUTED
        self.mode_badge.setText("● ONLINE" if online else "● OFFLINE")
        self.mode_badge.setStyleSheet(f"color: {color}; font-weight: 700; border-radius: 12px; padding: 4px 12px;")
        provider = cfg.ai.provider
        label = "AI: off" if provider == "none" else f"AI: {PROVIDER_LABELS.get(provider, provider).split(' (')[0]}"
        external = provider in ("openai", "anthropic")
        self.ai_badge.setText(label)
        self.ai_badge.setStyleSheet(
            f"color: {theme.WARNING if external else (theme.ACCENT if provider != 'none' else theme.MUTED)};"
            "border-radius: 12px; padding: 4px 12px;")
        self.ai_badge.setToolTip("External provider - data is anonymized before sending" if external else
                                 "Local or disabled AI")

    # ------------------------------------------------------------------ navigation
    def navigate(self, page: str, kwargs: dict) -> None:
        widget = self.pages.get(page)
        if widget is None:
            return
        self.stack.setCurrentWidget(widget)
        btn = self.nav_buttons.get(page)
        if btn is not None:
            btn.setChecked(True)
        else:
            checked = self.nav_group.checkedButton()
            if checked:
                self.nav_group.setExclusive(False)
                checked.setChecked(False)
                self.nav_group.setExclusive(True)
        if kwargs and self.ctx.session is None and page not in ("settings", "rules"):
            return
        widget.on_show(**kwargs)

    def _toggle_mode(self) -> None:
        cfg = self.ctx.config.model_copy(deep=True)
        cfg.network.mode = "offline" if cfg.network.online else "online"
        self.ctx.update_config(cfg)
        self.status_label.setText(f"Analysis mode: {cfg.network.mode.upper()} (applies to the next analysis)")

    # ------------------------------------------------------------------ analysis
    def load_demo(self) -> None:
        demo = paths.sample_data_dir()
        if not demo.exists():
            QMessageBox.warning(self, "Demo dataset", f"Demo data not found in {demo}")
            return
        self.start_analysis([str(demo)])

    def start_analysis(self, inputs: list[str]) -> None:
        if self.task is not None:
            QMessageBox.information(self, "Analysis running", "Please wait for the current analysis to finish.")
            return
        config = self.ctx.config
        state = self.ctx.state
        secrets = self.ctx.secrets

        def job(progress, cancel):
            pipeline = AnalysisPipeline(config, secrets, state, progress=progress, cancel=cancel)
            return pipeline.run(inputs)

        self.task = workers.Task(job)
        self.task.signals.progress.connect(self._on_progress)
        self.task.signals.finished.connect(self._on_finished)
        self.task.signals.failed.connect(self._on_failed)
        self.task.signals.cancelled.connect(self._on_cancelled)
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_btn.show()
        self.status_label.setText(f"Analyzing {len(inputs)} input(s)…")
        workers.start(self.task)

    def _on_progress(self, p: Progress) -> None:
        self.progress.setValue(int(p.percent * 10))
        self.progress.setFormat(f"{p.percent:.0f}%")
        if p.stage == "parse" and p.processed:
            total = f" / ~{p.total:,}" if p.total else ""
            self.status_label.setText(f"Analyzing…  {p.processed:,}{total} events  —  {p.message}")
        else:
            self.status_label.setText(f"{p.message}…")

    def _finish_task(self) -> None:
        self.task = None
        self.progress.hide()
        self.cancel_btn.hide()

    def _on_finished(self, session) -> None:
        self._finish_task()
        self.ctx.set_session(session)
        s = session.summary
        self.status_label.setText(f"Analysis complete: {s.events:,} events, {s.incidents} incidents, "
                                  f"{s.duration_seconds:.1f}s. {s.enrichment_status}")
        self.navigate("dashboard", {})
        problems = s.rejected_inputs + ([f"{s.parse_errors} malformed records skipped"] if s.parse_errors else [])
        if s.events == 0:
            QMessageBox.warning(self, "No events", "No events could be extracted from the selected input.\n\n"
                                + "\n".join(problems[:10]))
        elif s.rejected_inputs:
            QMessageBox.warning(self, "Some inputs were rejected", "\n".join(s.rejected_inputs[:15]))

    def _on_failed(self, message: str) -> None:
        self._finish_task()
        self.status_label.setText("Analysis failed")
        QMessageBox.critical(self, "Analysis failed", f"{message}\n\nDetails were written to logs/errors.log.")

    def _on_cancelled(self) -> None:
        self._finish_task()
        self.status_label.setText("Analysis cancelled")

    def _cancel(self) -> None:
        if self.task is not None:
            self.task.cancel()
            self.status_label.setText("Cancelling…")

    # ------------------------------------------------------------------ window events
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths_ = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths_:
            self.start_analysis(paths_)

    def maybe_onboard(self) -> None:
        if not self.ctx.config.ui.first_run:
            return
        dlg = OnboardingDialog(self)
        dlg.exec()
        cfg = self.ctx.config.model_copy(deep=True)
        cfg.ui.first_run = False
        cfg.network.mode = "online" if dlg.choice == OnboardingDialog.ONLINE else "offline"
        self.ctx.update_config(cfg)
        if dlg.choice == OnboardingDialog.CONFIGURE_AI:
            self.navigate("settings", {})
            settings: SettingsPage = self.pages["settings"]  # type: ignore[assignment]
            settings.tabs.setCurrentIndex(1)

    def closeEvent(self, event) -> None:
        if self.task is not None:
            self.task.cancel()
        try:
            if self.ctx.session is not None:
                self.ctx.session.close()
        finally:
            super().closeEvent(event)


def open_path(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


__all__ = ["MainWindow", "QTimer", "AnalysisCancelled"]
