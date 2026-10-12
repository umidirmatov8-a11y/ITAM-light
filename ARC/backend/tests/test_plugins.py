"""Plugin Manager: declarative, signed modules with their own permissions."""
from __future__ import annotations

import copy
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from arc_backend.api.server import create_app
from arc_backend.models import Source, Status
from arc_backend.plugins.manager import PluginError
from arc_backend.plugins.manifest import PluginManifest
from arc_backend.plugins.signing import key_id, public_key_b64, sign
from arc_backend.plugins.tool import main as tool_main

MANIFEST = {
    "format": 1,
    "id": "quiet-hours",
    "name": "Тихие часы",
    "version": "1.0.0",
    "author": "Тест",
    "description": "Команды для вечера",
    "permissions": ["volume", "windows", "apps"],
    "commands": [
        {"phrases": ["вечерний режим", "пора отдыхать"],
         "actions": [{"action": "volume.set", "params": {"level": 15}}, {"action": "window.minimize_all"}],
         "reply": "Хорошего вечера."},
        {"phrases": ["открой мессенджер"], "actions": [{"action": "app.launch", "app": "Telegram"}]},
    ],
}

KEY = Ed25519PrivateKey.generate()
PUBLIC = public_key_b64(KEY)


def package(manifest=None, key=KEY, signed=True) -> bytes:
    manifest = copy.deepcopy(manifest or MANIFEST)
    doc = {"manifest": manifest, "signature": sign(manifest, key) if signed else None}
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


def trust(services, public=PUBLIC, name="Автор"):
    services.settings.update({"plugins": {"trusted_keys": [{"id": key_id(public), "name": name, "public_key": public}]}})
    services.plugins.refresh_trust()


def install(services, data=None, modules=("volume", "windows", "apps")):
    plugin = services.plugins.import_bytes(data or package())
    services.plugins.set_modules(plugin.id, list(modules))
    services.plugins.set_enabled(plugin.id, True)
    return plugin


# ------------------------------------------------------------------ manifest validation
@pytest.mark.parametrize("change,needle", [
    ({"commands": [{"phrases": ["выключи всё"], "actions": [{"action": "power.shutdown", "params": {"delay_s": 0}}]}],
      "permissions": ["volume"]}, "power"),
    ({"permissions": ["volume"], "commands": [{"phrases": ["онлайн"], "actions": [
        {"action": "mode.set", "params": {"mode": "ONLINE"}}]}]}, "not available"),
    ({"permissions": ["volume"], "commands": [{"phrases": ["убить"], "actions": [
        {"action": "window.minimize_all"}]}]}, "windows"),
    ({"commands": [{"phrases": ["x1"], "actions": [{"action": "app.launch", "params": {"app_id": "abc"}}]}]}, "app"),
    ({"commands": [{"phrases": ["громче"], "actions": [{"action": "volume.set", "params": {"level": 500}}]}]}, "level"),
    ({"commands": [{"phrases": ["скрипт"], "actions": [{"action": "shell.run", "params": {"cmd": "calc"}}]}]},
     "unknown action"),
    ({"run": "powershell -c calc"}, "run"),
    ({"id": "../../evil"}, "id"),
])
def test_dangerous_or_malformed_manifests_are_rejected(change, needle):
    with pytest.raises(ValueError) as info:
        PluginManifest.model_validate({**MANIFEST, **change})
    assert needle in str(info.value)


def test_power_and_modes_cannot_even_be_requested():
    for module in ("power", "modes"):
        with pytest.raises(ValueError):
            PluginManifest.model_validate({**MANIFEST, "permissions": [module]})


# ------------------------------------------------------------------ trust
def test_unknown_key_unsigned_and_tampered_are_refused(services):
    with pytest.raises(PluginError, match="неизвестным ключом"):
        services.plugins.import_bytes(package())
    with pytest.raises(PluginError, match="не подписан"):
        services.plugins.import_bytes(package(signed=False))
    trust(services)
    doc = json.loads(package())
    doc["manifest"]["commands"][0]["actions"][0]["params"]["level"] = 100  # changed after signing
    with pytest.raises(PluginError, match="не сходится"):
        services.plugins.import_bytes(json.dumps(doc).encode())
    assert services.plugins.list() == []


def test_unsigned_only_when_explicitly_allowed(services):
    services.settings.update({"plugins": {"allow_unsigned": True}})
    plugin = services.plugins.import_bytes(package(signed=False))
    assert plugin.trust == "unsigned"
    services.settings.update({"plugins": {"allow_unsigned": False}})
    services.plugins.refresh_trust()
    view = services.plugins.view(services.plugins.get(plugin.id))
    assert view["blocked"] and not view["enabled"]
    with pytest.raises(PluginError):
        services.plugins.set_enabled(plugin.id, True)


def test_installed_module_is_off_and_has_no_permissions(services):
    trust(services)
    plugin = services.plugins.import_bytes(package())
    view = services.plugins.view(plugin)
    assert view["trust"] == "trusted" and view["signer"] == "Автор"
    assert not view["enabled"] and view["granted"] == []
    assert services.assistant.handle_text("вечерний режим").status == Status.UNKNOWN


def test_update_rules(services):
    trust(services)
    install(services)
    with pytest.raises(PluginError, match="уже установлен"):
        services.plugins.import_bytes(package())
    other = Ed25519PrivateKey.generate()
    trust_both = [{"id": key_id(PUBLIC), "name": "A", "public_key": PUBLIC},
                  {"id": key_id(public_key_b64(other)), "name": "B", "public_key": public_key_b64(other)}]
    services.settings.update({"plugins": {"trusted_keys": trust_both}})
    newer = {**MANIFEST, "version": "1.1.0"}
    with pytest.raises(PluginError, match="другим ключом"):
        services.plugins.import_bytes(package(newer, key=other))
    newer["permissions"] = ["volume", "windows", "apps", "files"]
    services.plugins.import_bytes(package(newer))
    grant = services.settings.get().plugins.grants["quiet-hours"]
    assert grant.enabled and "files" not in grant.modules  # new permission starts switched off


def test_removing_trust_disables_the_module(services):
    trust(services)
    install(services)
    services.settings.update({"plugins": {"trusted_keys": []}})
    services.plugins.refresh_trust()
    assert services.assistant.handle_text("вечерний режим").status == Status.UNKNOWN


def test_modules_survive_restart(tmp_path, folders, controller):
    from arc_backend.services import Services
    from conftest import offline_planner
    svc = Services.create(tmp_path / "data", controller=controller, folders=lambda: folders, planner=offline_planner())
    trust(svc)
    install(svc)
    svc.close()
    svc = Services.create(tmp_path / "data", controller=controller, folders=lambda: folders, planner=offline_planner())
    try:
        assert svc.plugins.get("quiet-hours").trust == "trusted"
        assert svc.assistant.handle_text("вечерний режим").status == Status.DONE
    finally:
        svc.close()


# ------------------------------------------------------------------ running commands
def test_module_command_runs_catalog_actions(services, controller, apps):
    trust(services)
    install(services)
    response = services.assistant.handle_text("АРК, вечерний режим")
    assert response.status == Status.DONE, response.message
    assert response.intent == "plugin.command" and response.data["plugin"] == "quiet-hours"
    assert response.message.startswith("Хорошего вечера.")
    assert controller.called("volume_set") == [(15,)] and controller.called("minimize_all")
    audit = services.journal.audit_entries(5)
    assert {e["source"] for e in audit if e["action"] in ("volume.set", "window.minimize_all")} == {"plugin"}
    launch = services.assistant.handle_text("открой мессенджер")
    assert launch.status == Status.DONE and "Telegram" in launch.message


def test_builtin_commands_win_over_modules(services, controller):
    manifest = {**MANIFEST, "commands": [{"phrases": ["сверни все окна"],
                                          "actions": [{"action": "volume.set", "params": {"level": 100}}]}]}
    trust(services)
    install(services, package(manifest))
    services.assistant.handle_text("сверни все окна")
    assert controller.called("minimize_all") and not controller.called("volume_set")


def test_permission_not_granted(services, controller):
    trust(services)
    install(services, modules=("volume",))
    response = services.assistant.handle_text("вечерний режим")
    assert response.status == Status.DENIED and "windows" in response.message
    assert not controller.called("volume_set")  # nothing runs when any action is not permitted


def test_category_b_from_module_still_needs_user_confirmation(services, controller, folders):
    manifest = {**MANIFEST, "permissions": ["files"], "commands": [
        {"phrases": ["новый проект"], "actions": [{"action": "files.create_folder",
                                                   "params": {"name": "Проект", "parent": "desktop"}}]}]}
    trust(services)
    install(services, package(manifest), modules=("files",))
    response = services.assistant.handle_text("новый проект")
    assert response.status == Status.NEEDS_CONFIRMATION
    assert services.assistant.confirm(response.confirmation.id, True, Source.PLUGIN).status == Status.DENIED
    assert services.assistant.confirm(response.confirmation.id, True, Source.UI).status == Status.DRY_RUN


def test_permission_manager_blocks_plugin_source_for_critical_actions(services):
    from arc_backend.models import ActionRequest
    for action, params in (("power.shutdown", {"delay_s": 60}), ("mode.set", {"mode": "ONLINE"}),
                           ("process.terminate", {"pid": 1234})):
        decision = services.permissions.evaluate(ActionRequest(action=action, params=params, source=Source.PLUGIN))
        assert decision.verdict == "deny"


# ------------------------------------------------------------------ API and CLI
def test_api_flow(services, tmp_path):
    app = create_app(services, "t" * 43, allowed_hosts=("testserver",))
    with TestClient(app) as c:
        c.headers["X-ARC-Token"] = "t" * 43
        path = tmp_path / "quiet.arcplugin"
        path.write_bytes(package())
        reply = c.post("/api/plugins/import", json={"path": str(path)})
        assert reply.status_code == 409 and "неизвестным ключом" in reply.json()["detail"]
        assert c.post("/api/plugins/keys", json={"name": "Автор", "public_key": "bad"}).status_code in (400, 422)
        c.post("/api/plugins/keys", json={"name": "Автор", "public_key": PUBLIC})
        assert c.post("/api/plugins/import", json={"path": str(tmp_path / "x.exe")}).status_code == 409
        view = c.post("/api/plugins/import", json={"path": str(path)}).json()
        assert view["installed"] == "quiet-hours" and view["plugins"][0]["trust"] == "trusted"
        assert c.put("/api/plugins/quiet-hours/grants", json={"modules": ["power"]}).status_code == 409
        c.put("/api/plugins/quiet-hours/grants", json={"modules": ["volume", "windows"]})
        view = c.post("/api/plugins/quiet-hours/enable", json={"enabled": True}).json()
        assert view["plugins"][0]["enabled"] and view["plugins"][0]["granted"] == ["volume", "windows"]
        assert c.post("/api/command", json={"text": "пора отдыхать"}).json()["status"] == "done"
        assert c.delete("/api/plugins/quiet-hours").json()["plugins"] == []
        assert c.post("/api/command", json={"text": "пора отдыхать"}).json()["status"] == "unknown"
        actions = [e["action"] for e in c.get("/api/audit").json()]
        assert {"plugins.install", "plugins.grant", "plugins.enable", "plugins.remove", "plugins.trust_key"} <= set(actions)
        assert c.post("/api/command", json={"text": "x", "source": "plugin"}).status_code == 422


def test_cli_keygen_sign_verify(tmp_path, capsys):
    key = tmp_path / "author.pem"
    assert tool_main(["keygen", "--out", str(key)]) == 0
    public = json.loads(capsys.readouterr().out)["public_key"]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(MANIFEST, ensure_ascii=False), encoding="utf-8")
    assert tool_main(["check", str(manifest)]) == 0
    out = tmp_path / "quiet.arcplugin"
    assert tool_main(["sign", str(manifest), "--key", str(key), "--out", str(out)]) == 0
    capsys.readouterr()
    assert tool_main(["verify", str(out), "--public-key", public]) == 0
    assert "SIGNATURE OK" in capsys.readouterr().out
    assert tool_main(["verify", str(out), "--public-key", PUBLIC]) == 1


def test_example_manifest_in_docs_is_valid():
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "docs" / "plugins" / "example-evening.json"
    manifest = PluginManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert manifest.id == "evening-mode" and manifest.permissions == ["apps", "volume", "windows"]
