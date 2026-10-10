"""GUI smoke test in offscreen mode against the demo directory (no domain controller)."""
import time

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def pump(app, win, seconds=0.2, limit=60):
    end = time.time() + seconds
    while time.time() < end or win.tasks.active:
        app.processEvents()
        time.sleep(0.005)
        if time.time() > end + limit:
            raise TimeoutError("background tasks did not finish")


def test_main_window_demo(app, db, monkeypatch):
    from adtoolkit.core.app_config import SettingsManager
    from adtoolkit.services.ldap_service import ConnectionService
    from adtoolkit.ui import main_window, theme
    from adtoolkit.ui.widgets import common
    errors = []
    monkeypatch.setattr(main_window, "show_error", lambda parent, exc, title="": errors.append(exc))
    monkeypatch.setattr(common, "show_error", lambda parent, exc, title="": errors.append(exc))
    theme.apply_theme(app, "dark")
    win = main_window.MainWindow(db, SettingsManager(db))
    win.set_context(ConnectionService(win.journal, win.settings).connect_demo(read_only=True))
    for key, _ in main_window.PAGES:
        win.navigate(key)
        pump(app, win)
    assert win.pages["users"].table.model.rowCount() > 200
    assert win.pages["computers"].table.model.rowCount() > 100
    win.pages["audit"].run_audit()
    pump(app, win)
    assert win.pages["audit"].findings.model.rowCount() > 50
    win.search.setText("svc")
    win._global_search()
    pump(app, win)
    assert win.pages["search"].users.model.rowCount() == 4
    # read-only mode: write actions are refused before any LDAP call
    rows = win.pages["users"].table.model.rows[:1]
    win.actions.set_user_enabled(rows, False)
    assert win.ctx.gateway.read_only
    win.apply_theme("light")
    win.disconnect()
    pump(app, win)
    assert win.ctx is None
    assert not errors, errors
    win.close()
