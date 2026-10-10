import pytest
from fastapi.testclient import TestClient

from arc_backend.api.server import create_app

TOKEN = "t" * 43


@pytest.fixture
def client(services, apps):
    app = create_app(services, TOKEN, allowed_hosts=("testserver", "127.0.0.1", "localhost"))
    with TestClient(app) as c:
        c.headers["X-ARC-Token"] = TOKEN
        yield c


def test_token_required(services):
    app = create_app(services, TOKEN, allowed_hosts=("testserver",))
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 403
        assert c.get("/api/health", headers={"X-ARC-Token": "wrong"}).status_code == 403
        assert c.get("/api/health", headers={"X-ARC-Token": TOKEN}).status_code == 200


def test_browser_requests_rejected(client):
    assert client.get("/api/health", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/health", headers={"Origin": "null"}).status_code == 403
    assert client.get("/api/health", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_dns_rebinding_rejected(client):
    assert client.get("/api/health", headers={"Host": "evil.example:8000"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "127.0.0.1:5000"}).status_code == 200


def test_form_post_rejected(client):
    response = client.post("/api/command", content="text=выключи компьютер",
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert response.status_code == 403


def test_command_and_confirm(client):
    response = client.post("/api/command", json={"text": "открой телеграм"}).json()
    assert response["status"] == "done"
    response = client.post("/api/command", json={"text": "выключи компьютер"}).json()
    assert response["status"] == "needs_confirmation"
    confirmation = response["confirmation"]
    assert confirmation["risk"] == "C" and confirmation["requires_acknowledge"]
    assert client.get("/api/state").json()["pending_confirmation"]["id"] == confirmation["id"]
    denied = client.post("/api/confirm", json={"id": confirmation["id"], "approve": True}).json()
    assert denied["status"] == "denied"
    done = client.post("/api/confirm", json={"id": confirmation["id"], "approve": True, "acknowledge": True}).json()
    assert done["status"] == "dry_run"


def test_client_cannot_spoof_privileged_sources(client):
    for source in ("ui", "ai", "scenario", "gesture"):
        assert client.post("/api/command", json={"text": "сверни окна", "source": source}).status_code == 422


def test_settings_roundtrip(client):
    assert client.get("/api/settings").json()["ui"]["theme"] == "amber"
    updated = client.put("/api/settings", json={"ui": {"theme": "ice", "scale": 1.1}}).json()
    assert updated["ui"]["theme"] == "ice"
    bad = client.put("/api/settings", json={"ui": {"theme": "x"}})
    assert bad.status_code == 400
    assert client.get("/api/settings").json()["ui"]["theme"] == "ice"


def test_apps_crud_and_untrusted(client, controller, monkeypatch):
    body = {"name": "Portable", "launch_type": "exe", "target": "D:\\Downloads\\portable.exe"}
    response = client.post("/api/apps", json=body)
    assert response.status_code == 409 and response.json()["error"] == "untrusted_location"
    created = client.post("/api/apps", json={**body, "confirm_untrusted": True}).json()
    assert created["process_name"] == "portable.exe"
    updated = client.put(f"/api/apps/{created['id']}", json={"aliases": ["портативка"], "pinned": True}).json()
    assert updated["pinned"]
    launched = client.post(f"/api/apps/{created['id']}/launch").json()
    assert launched["status"] == "done"
    assert client.delete(f"/api/apps/{created['id']}").json() == {"deleted": created["id"]}
    assert client.delete(f"/api/apps/{created['id']}").status_code == 404
    controller.assume_paths_exist = False
    missing = client.post("/api/apps", json={**body, "confirm_untrusted": True})
    assert missing.status_code == 400


def test_admin_launch_from_button_requires_confirmation(client, apps):
    response = client.post(f"/api/apps/{apps['Admin Tool']}/launch").json()
    assert response["status"] == "needs_confirmation" and response["risk"] == "C"


def test_ollama_not_running(client, no_network):
    client.put("/api/settings", json={"ai": {"ollama_url": "http://127.0.0.1:9"}})
    status = client.get("/api/ai/status?force=true").json()
    assert status["state"] == "offline"
    # assistant keeps working without the local model
    assert client.post("/api/command", json={"text": "открой телеграм"}).json()["status"] == "done"


def test_remote_ollama_requires_online(client):
    client.put("/api/settings", json={"ai": {"ollama_url": "http://192.0.2.10:11434"}})
    assert client.get("/api/ai/status?force=true").json()["state"] == "blocked"


def test_local_ai_can_be_disabled(client):
    client.put("/api/settings", json={"devices": {"local_ai_enabled": False}})
    assert client.get("/api/ai/status").json()["state"] == "disabled"


def test_emergency_stop_endpoint(client):
    client.post("/api/emergency-stop", json={"engaged": True})
    assert client.get("/api/state").json()["emergency_stop"] is True
    assert client.post("/api/command", json={"text": "открой телеграм"}).json()["status"] == "denied"
    client.post("/api/emergency-stop", json={"engaged": False})
    assert client.post("/api/command", json={"text": "открой телеграм"}).json()["status"] == "done"


def test_journal_endpoints(client):
    client.post("/api/command", json={"text": "сверни окна"})
    assert client.get("/api/history?limit=5").json()[0]["input"] == "сверни окна"
    assert client.get("/api/audit").json()[0]["action"] == "window.minimize_all"
    export = client.get("/api/audit/export?format=csv").json()
    assert export["filename"].endswith(".csv") and "window.minimize_all" in export["content"]
    assert client.delete("/api/history").json()["deleted"] >= 1


def test_scenarios_endpoints(client):
    data = client.get("/api/scenarios").json()
    assert "power.shutdown" not in data["allowed_actions"]
    bad = client.post("/api/scenarios", json={"name": "x", "steps": [{"action": "power.shutdown", "params": {}}]})
    assert bad.status_code == 422
    created = client.post("/api/scenarios", json={"name": "Кино", "aliases": ["режим кино"],
                                                  "steps": [{"action": "volume.set", "params": {"level": 80}}]}).json()
    assert client.post(f"/api/scenarios/{created['id']}/run").json()["status"] == "done"


def test_diagnostics_and_misc(client):
    diag = client.get("/api/diagnostics").json()
    names = {c["name"] for c in diag["checks"]}
    assert {"Backend", "База данных", "Локальный ИИ (Ollama)", "Камера / жесты"} <= names
    assert client.get("/api/system/stats").json()["ram"]["total_gb"] > 0
    assert any(a["name"] == "power.shutdown" and a["risk"] == "C" for a in client.get("/api/actions").json())
    assert "desktop" in client.get("/api/folders").json()["known"]
