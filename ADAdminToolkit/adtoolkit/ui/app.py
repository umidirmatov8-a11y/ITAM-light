"""Application bootstrap: logging (with secret masking), QApplication, theme, main window."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .. import APP_NAME, __version__
from ..security.masking import SecretMaskingFilter
from ..storage.database import default_data_dir


def setup_logging(debug: bool = False) -> Path:
    log_dir = default_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "adtoolkit.log"
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(SecretMaskingFilter())
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.addHandler(handler)
    # ldap3 protocol logging can contain attribute values — keep it off
    logging.getLogger("ldap3").setLevel(logging.WARNING)
    return path


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "resources" / name


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    demo = "--demo" in argv
    debug = "--debug" in argv
    log_path = setup_logging(debug)
    log = logging.getLogger("adtoolkit")
    log.info("Запуск %s %s", APP_NAME, __version__)

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from ..core.app_config import SettingsManager
    from ..storage.database import Database
    from . import theme
    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("ADAdminToolkit")
    icon = resource_path("icon.png")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    db = Database()
    settings_mgr = SettingsManager(db)
    theme.apply_theme(app, settings_mgr.settings.theme)
    win = MainWindow(db, settings_mgr)
    win.show()

    def excepthook(exc_type, exc, tb):
        import traceback

        from ..security.masking import mask_text
        log.error("Необработанное исключение: %s", mask_text("".join(traceback.format_exception(exc_type, exc, tb))))
        try:
            from .widgets.common import show_error
            show_error(win, exc, "Непредвиденная ошибка")
        except Exception:  # noqa: BLE001
            pass
    sys.excepthook = excepthook

    if demo:
        from ..services.ldap_service import ConnectionService
        QTimer.singleShot(100, lambda: win.set_context(ConnectionService(win.journal, win.settings).connect_demo(read_only=True)))
    else:
        QTimer.singleShot(200, win.show_connect_dialog)
    log.info("Журнал приложения: %s", log_path)
    return app.exec()
