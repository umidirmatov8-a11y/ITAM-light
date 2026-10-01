import os
import time

import pytest

pytestmark = pytest.mark.gui

QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from app.ui.theme import apply_theme

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    apply_theme(app)
    return app


def wait(app, condition, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def window(qapp, tmp_path):
    from app.core.config import ConfigManager
    from app.core.secrets import MemorySecretStore
    from app.database.state import StateStore
    from app.ui.context import AppContext
    from app.ui.main_window import MainWindow

    cm = ConfigManager(tmp_path / "config.yaml")
    ctx = AppContext(cm, MemorySecretStore(), StateStore(f"sqlite:///{tmp_path / 'state.db'}"))
    w = MainWindow(ctx)
    w.show()
    yield w
    w.close()


def test_demo_loads_and_all_pages_render(qapp, window):
    window.load_demo()
    assert wait(qapp, lambda: window.task is None and window.ctx.session is not None)
    session = window.ctx.session
    assert session.summary.events > 2000
    dash = window.pages["dashboard"]
    assert dash.stack.currentIndex() == 1
    assert dash.sev_cards["critical"].value.text() != "0"
    for name in ("alerts", "incidents", "hosts", "users", "ioc", "cve", "mitre", "rules", "reports", "settings"):
        window.navigate(name, {})
        qapp.processEvents()
    alerts = window.pages["alerts"]
    window.navigate("alerts", {"severity": "critical"})
    assert alerts.findings.model.rowCount() > 0
    assert "What happened?" in alerts.detail.toPlainText()
    incidents = window.pages["incidents"]
    window.navigate("incidents", {"incident_id": session.incidents()[0].id})
    assert "Possible" in incidents.detail.toPlainText() or "Malware" in incidents.detail.toPlainText()
    window.navigate("search", {"term": "203.0.113.66"})
    assert "alerts" in window.pages["search"].result_view.toPlainText()
    assert window.pages["mitre"].matrix.rowCount() > 0


def test_raw_events_view_and_status_change(qapp, window):
    window.load_demo()
    assert wait(qapp, lambda: window.task is None and window.ctx.session is not None)
    alerts = window.pages["alerts"]
    window.navigate("alerts", {})
    alerts._show_group_events()
    assert alerts.events.model.rowCount() > 0
    incidents = window.pages["incidents"]
    window.navigate("incidents", {})
    incidents.table.view.selectRow(0)
    incidents.status.setCurrentIndex(incidents.status.findData("INVESTIGATING"))
    incidents._change_status(0)
    inc = window.ctx.session.incident(incidents.current.id)
    assert inc.status == "INVESTIGATING"
    assert window.ctx.state.get_status(inc.fingerprint) == "INVESTIGATING"


def test_ai_disabled_message(qapp, window, monkeypatch):
    window.load_demo()
    assert wait(qapp, lambda: window.task is None and window.ctx.session is not None)
    shown = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    window.navigate("alerts", {})
    window.pages["alerts"]._analyze_ai()
    assert shown and "disabled" in shown[0]


def test_settings_roundtrip(qapp, window):
    settings = window.pages["settings"]
    settings.mode_online.setChecked(True)
    settings.thresholds["critical"].setValue(85)
    settings.save()
    assert window.ctx.config.network.mode == "online"
    assert window.ctx.config.risk_thresholds.critical == 85
    settings.weights_edit.setPlainText("not: [valid")
    shown = []
    QtWidgets.QMessageBox.critical = lambda *a, **k: shown.append(a)
    settings.save()
    assert shown and window.ctx.config.risk_thresholds.critical == 85


def test_secret_saved_not_in_config(qapp, window, tmp_path):
    settings = window.pages["settings"]
    settings.key_edits["virustotal_api_key"].setText("vt-secret-123")
    settings._save_key("virustotal_api_key")
    settings.save()
    assert window.ctx.secrets.get("virustotal_api_key") == "vt-secret-123"
    assert "vt-secret-123" not in (tmp_path / "config.yaml").read_text()


def test_bad_input_does_not_crash(qapp, window, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\x00\x01garbage{{{")
    warnings = []
    QtWidgets.QMessageBox.warning = lambda *a, **k: warnings.append(a)
    window.start_analysis([str(bad), str(tmp_path / "missing.json")])
    assert wait(qapp, lambda: window.task is None)
    assert window.ctx.session is not None and warnings
