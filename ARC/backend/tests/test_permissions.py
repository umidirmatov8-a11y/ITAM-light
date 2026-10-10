import pytest

from arc_backend.models import ActionRequest, Risk, Source
from arc_backend.permissions.catalog import CATALOG
from arc_backend.permissions.manager import ConfirmationError, PermissionManager
from arc_backend.storage.settings import Settings


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def pm(settings, clock):
    return PermissionManager(lambda: settings, clock)


def req(action, source=Source.TEXT, **params):
    return ActionRequest(action=action, params=params, source=source)


def test_catalog_categories():
    assert CATALOG["app.launch"].risk == Risk.A
    assert CATALOG["files.create_folder"].risk == Risk.B
    assert CATALOG["process.terminate"].risk == Risk.B
    assert CATALOG["power.shutdown"].risk == Risk.C
    assert CATALOG["app.launch_admin"].risk == Risk.C
    # nothing in the catalog runs arbitrary commands or changes permissions
    assert not [name for name in CATALOG if "shell" in name or "command" in name or "settings" in name]


def test_safe_action_allowed(pm):
    assert pm.evaluate(req("volume.set", level=30)).verdict == "allow"


def test_unknown_action_denied(pm):
    decision = pm.evaluate(req("system.run_powershell", script="Remove-Item C:\\ -Recurse"))
    assert decision.verdict == "deny"
    assert "каталог" in decision.reason


def test_invalid_params_denied(pm):
    assert pm.evaluate(req("volume.set", level=500)).verdict == "deny"
    assert pm.evaluate(req("volume.set", level=10, extra="x")).verdict == "deny"
    assert pm.evaluate(req("browser.open_url", url="file:///C:/Windows/System32/cmd.exe")).verdict == "deny"
    assert pm.evaluate(req("browser.open_url", url="javascript:alert(1)")).verdict == "deny"
    assert pm.evaluate(req("app.launch", app_id="../../etc")).verdict == "deny"


def test_state_changing_and_critical_need_confirmation(pm):
    assert pm.evaluate(req("files.create_folder", name="x", parent="desktop")).verdict == "confirm"
    assert pm.evaluate(req("power.shutdown", delay_s=60)).verdict == "confirm"


def test_module_switch(pm, settings):
    settings.safety.modules["volume"] = False
    decision = pm.evaluate(req("volume.set", level=10))
    assert decision.verdict == "deny" and "volume" in decision.reason


def test_online_actions_need_online_mode(pm, settings):
    assert pm.evaluate(req("web.search", query="погода")).verdict == "deny"
    settings.network.mode = "ONLINE"
    assert pm.evaluate(req("web.search", query="погода")).verdict == "allow"
    settings.network.online_allowed = False
    decision = pm.evaluate(req("web.search", query="погода"))
    assert decision.verdict == "deny" and "отключены" in decision.reason
    assert pm.evaluate(req("mode.set", mode="ONLINE")).verdict == "deny"
    assert pm.evaluate(req("mode.set", mode="LOCAL")).verdict == "allow"


def test_gestures_limited_to_safe_whitelist(pm):
    assert pm.evaluate(req("volume.mute", Source.GESTURE, muted=True)).verdict == "allow"
    assert pm.evaluate(req("files.search", Source.GESTURE, query="x")).verdict == "deny"
    assert pm.evaluate(req("power.shutdown", Source.GESTURE, delay_s=60)).verdict == "deny"
    assert pm.evaluate(req("files.create_folder", Source.GESTURE, name="x", parent="desktop")).verdict == "deny"


def test_ai_cannot_switch_mode(pm):
    assert pm.evaluate(req("mode.set", Source.AI, mode="ONLINE")).verdict == "deny"


def test_emergency_stop_blocks_everything(pm):
    pending = pm.request_confirmation(req("power.shutdown", delay_s=60), CATALOG["power.shutdown"], "выключение")
    pm.set_emergency_stop(True)
    assert pm.evaluate(req("volume.set", level=10)).verdict == "deny"
    assert pm.pending() == []
    with pytest.raises(ConfirmationError):
        pm.resolve(pending.id, source=Source.UI, acknowledge=True)
    pm.set_emergency_stop(False)
    assert pm.evaluate(req("volume.set", level=10)).verdict == "allow"


def test_critical_confirmation_requires_ui_and_acknowledge(pm):
    item = pm.request_confirmation(req("power.shutdown", delay_s=60), CATALOG["power.shutdown"], "выключение")
    assert item.info().requires_acknowledge
    for source, ack in ((Source.VOICE, True), (Source.GESTURE, True), (Source.UI, False), (Source.AI, True)):
        with pytest.raises(ConfirmationError):
            pm.resolve(item.id, source=source, acknowledge=ack)
    assert pm.resolve(item.id, source=Source.UI, acknowledge=True).id == item.id
    with pytest.raises(ConfirmationError):  # single use
        pm.resolve(item.id, source=Source.UI, acknowledge=True)


def test_b_category_can_be_confirmed_by_voice_but_not_gesture(pm):
    spec = CATALOG["files.create_folder"]
    item = pm.request_confirmation(req("files.create_folder", name="x", parent="desktop"), spec, "папка")
    with pytest.raises(ConfirmationError):
        pm.resolve(item.id, source=Source.GESTURE)
    assert pm.resolve(item.id, source=Source.VOICE).id == item.id


def test_confirmation_expires(pm, clock, settings):
    item = pm.request_confirmation(req("power.shutdown", delay_s=60), CATALOG["power.shutdown"], "выключение")
    clock.t += settings.safety.confirmation_ttl_s + 1
    with pytest.raises(ConfirmationError):
        pm.resolve(item.id, source=Source.UI, acknowledge=True)
