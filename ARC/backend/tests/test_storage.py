import json
import os

import pytest

from arc_backend.apps.registry import AppInput, AppRegistry, LaunchType
from arc_backend.automation.controller import MockController
from arc_backend.services import Services
from arc_backend.storage.db import Database
from arc_backend.storage.settings import SettingsStore


def test_settings_persist_across_restart(tmp_path, folders):
    first = Services.create(tmp_path / "d", controller=MockController(), folders=lambda: folders)
    first.settings.update({"ui": {"theme": "phosphor", "scale": 1.25, "animations": False},
                           "network": {"mode": "ONLINE"}, "safety": {"dry_run": False}})
    app = first.registry.add(AppInput(name="Telegram", launch_type=LaunchType.EXE, target=r"C:\T\Telegram.exe",
                                      aliases=["телега"]))
    first.close()

    second = Services.create(tmp_path / "d", controller=MockController(), folders=lambda: folders)
    settings = second.settings.get()
    assert settings.ui.theme == "phosphor" and settings.ui.scale == 1.25 and settings.ui.animations is False
    assert settings.network.mode.value == "ONLINE"
    assert settings.safety.dry_run is False
    assert second.registry.get(app.id).aliases == ["телега"]
    # first-run seeding happens once
    assert len([a for a in second.registry.list() if a.source == "builtin"]) == 6
    assert len(second.scenarios.list()) == 2
    second.close()


def test_first_run_defaults(services, folders):
    settings = services.settings.get()
    assert settings.network.mode.value == "LOCAL"
    assert settings.safety.dry_run is True
    assert set(settings.safety.allowed_dirs) == {folders["desktop"], folders["documents"], folders["downloads"]}


def test_settings_validation(services):
    with pytest.raises(ValueError):
        services.settings.update({"ui": {"theme": "neon-pink"}})
    with pytest.raises(ValueError):
        services.settings.update({"ui": {"unknown_field": 1}})
    with pytest.raises(ValueError):
        services.settings.update({"permissions_override": {}})
    with pytest.raises(ValueError):
        services.settings.update({"network": {"search_url": "http://evil.example/?q={query}"}})
    with pytest.raises(ValueError):
        services.settings.update({"ai": {"ollama_url": "file:///etc/passwd"}})
    assert services.settings.get().ui.theme == "amber"


def test_damaged_settings_fall_back_to_defaults(tmp_path):
    db = Database(tmp_path / "x.db")
    db.execute("INSERT INTO settings(key, value) VALUES('ui', '{not json')")
    db.execute("INSERT INTO settings(key, value) VALUES('network', '{\"mode\": \"MARS\"}')")
    store = SettingsStore(db)
    assert store.get().ui.theme == "amber"
    assert store.get().network.mode.value == "LOCAL"


def test_registry_validation(tmp_path):
    reg = AppRegistry(Database(tmp_path / "r.db"))
    bad = [
        dict(name="x", launch_type="exe", target="relative\\app.exe"),
        dict(name="x", launch_type="exe", target="C:\\app.bat"),
        dict(name="x", launch_type="protocol", target="file:///C:/Windows/system32/cmd.exe"),
        dict(name="x", launch_type="protocol", target="javascript:alert(1)"),
        dict(name="x", launch_type="protocol", target="steam://run/1 & calc"),
        dict(name="x", launch_type="uwp", target="not an aumid"),
        dict(name="x", launch_type="lnk", target="C:\\x.lnk", run_as_admin=True),
        dict(name="x", launch_type="exe", target="C:\\a.exe", process_name="..\\evil.exe"),
        dict(name="", launch_type="exe", target="C:\\a.exe"),
    ]
    for item in bad:
        with pytest.raises(ValueError):
            AppInput.model_validate(item)
    entry = reg.add(AppInput(name="  Steam  ", launch_type=LaunchType.EXE, target="C:\\Steam\\steam.exe"))
    assert entry.name == "Steam" and entry.process_name == "steam.exe"
    with pytest.raises(ValueError):
        reg.add(AppInput(name="Steam 2", launch_type=LaunchType.EXE, target="c:\\steam\\STEAM.exe"))
    updated = reg.update(entry.id, {"aliases": ["стим", "Стим", "  "], "pinned": True})
    assert updated.aliases == ["стим"] and updated.pinned
    with pytest.raises(ValueError):
        reg.update(entry.id, {"id": "hack"})
    assert reg.delete(entry.id) and reg.get(entry.id) is None


def test_journal_export(services):
    services.assistant.handle_text("сверни все окна")
    services.assistant.handle_text("выключи компьютер")
    data = json.loads(services.journal.export("json"))
    actions = [a["action"] for a in data["audit"]]
    assert actions == ["window.minimize_all", "power.shutdown"]
    assert data["audit"][1]["status"] == "pending"
    csv_text = services.journal.export("csv")
    assert csv_text.splitlines()[0].startswith("time,action")
    assert "power.shutdown" in csv_text
    assert services.journal.clear_history() == 2
    assert services.journal.history() == []


def test_database_file_location(services):
    assert os.path.basename(services.db.path) == "arc.db"
    assert services.db.schema_version == 1
