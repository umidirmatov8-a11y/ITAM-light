"""GUI entry point."""

from __future__ import annotations

import logging
import sys
import traceback

from app import __app_name__, __version__
from app.core.config import ConfigManager
from app.core.logging_setup import setup_logging
from app.core.secrets import SecretStore
from app.database.state import StateStore
from app.i18n import set_language

log = logging.getLogger(__name__)


def _install_excepthook(app) -> None:
    from PySide6.QtWidgets import QMessageBox

    def hook(exc_type, exc, tb):
        log.critical("Unhandled exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        try:
            QMessageBox.critical(None, "Unexpected error",
                                 f"{exc_type.__name__}: {exc}\n\nThe application keeps running. Details were written "
                                 "to logs/errors.log.")
        except Exception:
            pass

    sys.excepthook = hook


def _onboarding(config_manager: ConfigManager) -> bool:
    """First-run dialog (shown before the main window so the chosen language applies at once)."""
    from app.ui.onboarding import OnboardingDialog

    dlg = OnboardingDialog()
    dlg.exec()
    cfg = config_manager.config.model_copy(deep=True)
    cfg.ui.first_run = False
    cfg.ui.language = dlg.language.currentData()
    cfg.network.mode = "online" if dlg.choice == OnboardingDialog.ONLINE else "offline"
    config_manager.update(cfg)
    set_language(cfg.language)
    return dlg.choice == OnboardingDialog.CONFIGURE_AI


def run_gui(argv: list[str] | None = None, initial_paths: list[str] | None = None) -> int:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication

    from app.core import paths
    from app.ui.context import AppContext
    from app.ui.main_window import MainWindow
    from app.ui.theme import apply_theme

    config_manager = ConfigManager()
    cfg = config_manager.config
    set_language(cfg.language)
    setup_logging(cfg.logging.level, cfg.logging.max_file_mb, cfg.logging.backup_count)
    log.info("%s %s starting", __app_name__, __version__)

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("WazuhSecurityAnalyzer")
    icon = paths.resources_dir() / "icons" / "app.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    apply_theme(app)
    _install_excepthook(app)

    open_ai_settings = False
    if cfg.ui.first_run:
        open_ai_settings = _onboarding(config_manager)
    state = StateStore(cfg.storage.state_database_url or None)
    ctx = AppContext(config_manager, SecretStore(), state)
    window = MainWindow(ctx)
    window.show()
    if open_ai_settings:
        QTimer.singleShot(150, window.open_ai_settings)
    if initial_paths:
        QTimer.singleShot(400, lambda: window.start_analysis(initial_paths))
    code = app.exec()
    state.dispose()
    log.info("Application exited with code %s", code)
    return code
