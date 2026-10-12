"""Gesture control with synthetic hands, a fake camera and a fake tracker (no hardware, no model)."""
import importlib.util
import time

import numpy as np
import pytest

from arc_backend.automation.controller import MockController
from arc_backend.models import ActionRequest, Source, Status
from arc_backend.services import Services
from arc_backend.storage.settings import Settings
from arc_backend.vision.camera import CameraError
from arc_backend.vision.engine import VisionError
from arc_backend.vision.gestures import classify, largest_hand
from arc_backend.vision.state import GestureConfig, GestureStateMachine


# ----------------------------------------------------------------------------- synthetic hands
def make_hand(fingers="11111", thumb="out", angle_deg=0.0, scale=1.0, offset=(0.0, 0.0), pinch=False):
    """Upright right hand (wrist at the bottom). fingers: index..pinky, '1' = extended."""
    wrist = np.array([0.5, 0.8])
    p = np.zeros((21, 3))
    p[0, :2] = wrist
    xs = [0.44, 0.49, 0.54, 0.585]
    for i, x in enumerate(xs):
        base = 5 + 4 * i
        mcp = np.array([x, 0.6 + (0.01 if i == 3 else 0.0)])
        p[base, :2] = mcp
        if fingers[i] == "1":
            for k in range(1, 4):
                p[base + k, :2] = mcp + [0, -0.045 * k]
        else:
            p[base + 1, :2] = mcp + [0, -0.04]
            p[base + 2, :2] = mcp + [0.002, -0.01]
            p[base + 3, :2] = mcp + [0.004, 0.02]
    if thumb == "out":      # sideways, away from the palm
        pts = [[0.42, 0.75], [0.36, 0.70], [0.31, 0.67], [0.26, 0.64]]
    elif thumb == "up":     # pointing up
        pts = [[0.42, 0.76], [0.37, 0.69], [0.355, 0.58], [0.34, 0.47]]
    else:                   # tucked over the folded fingers
        pts = [[0.42, 0.76], [0.43, 0.70], [0.45, 0.66], [0.46, 0.63]]
    p[1:5, :2] = pts
    if pinch:               # "OK": index tip touches thumb tip
        p[1:5, :2] = [[0.42, 0.76], [0.38, 0.70], [0.37, 0.64], [0.385, 0.585]]
        p[6, :2] = [0.43, 0.555]
        p[7, :2] = [0.41, 0.55]
        p[8, :2] = [0.39, 0.575]
    a = np.radians(angle_deg)
    rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    p[:, :2] = (p[:, :2] - wrist) @ rot.T * scale + wrist + offset
    return p


@pytest.mark.parametrize("kwargs,expected", [
    (dict(fingers="11111", thumb="out"), "open_palm"),
    (dict(fingers="00000", thumb="tucked"), "fist"),
    (dict(fingers="00000", thumb="up"), "thumbs_up"),
    (dict(fingers="10000", thumb="tucked"), "index_up"),
    (dict(fingers="11000", thumb="tucked"), "victory"),
    (dict(fingers="01111", thumb="out", pinch=True), "ok"),
])
def test_classify_synthetic(kwargs, expected):
    obs = classify(make_hand(**kwargs), 0.95)
    assert obs.gesture == expected, obs
    assert obs.confidence > 0.7


@pytest.mark.parametrize("angle", [-60, 45, 90, 180])
def test_open_palm_and_fist_are_rotation_invariant(angle):
    assert classify(make_hand("11111", "out", angle_deg=angle)).gesture == "open_palm"
    assert classify(make_hand("00000", "tucked", angle_deg=angle)).gesture == "fist"


def test_direction_matters_for_pointing_and_thumb():
    assert classify(make_hand("10000", "tucked", angle_deg=180)).gesture != "index_up"   # pointing down
    assert classify(make_hand("00000", "up", angle_deg=180)).gesture != "thumbs_up"     # thumbs down


def test_scale_invariance_and_largest_hand():
    small = make_hand("11111", "out", scale=0.4, offset=(0.2, 0.1))
    big = make_hand("00000", "tucked", scale=1.2)
    assert classify(small).gesture == "open_palm"
    chosen = largest_hand([(small, 0.9), (big, 0.9)])
    assert chosen is not None and classify(*chosen).gesture == "fist"
    assert largest_hand([]) is None


def test_ambiguous_hand_is_none():
    half = make_hand("11000", "out")
    half[13:17, :2] = half[13, :2] + np.array([[0, 0], [0, -0.03], [0, -0.045], [0.002, -0.05]])  # ring half bent
    obs = classify(half)
    assert obs.gesture in ("none", "victory") and (obs.gesture == "none" or obs.confidence < 0.9)
    with pytest.raises(ValueError):
        classify(np.zeros((5, 3)))


# ----------------------------------------------------------------------------- state machine
def feed(sm, gesture_kwargs, start_ms, duration_ms, step=50, allowed=None):
    fired = []
    obs = classify(make_hand(**gesture_kwargs), 0.95) if gesture_kwargs else None
    t = start_ms
    while t < start_ms + duration_ms:
        result = sm.feed(obs, t, allowed)
        if result:
            fired.append((result, t))
        t += step
    return fired, t


FIST = dict(fingers="00000", thumb="tucked")
PALM = dict(fingers="11111", thumb="out")
POINT = dict(fingers="10000", thumb="tucked")


def test_hold_then_fire_once_while_held():
    sm = GestureStateMachine(GestureConfig(hold_ms=600, cooldown_ms=1000, min_interval_ms=500))
    fired, _ = feed(sm, FIST, 0, 3000)
    assert [g for g, _ in fired] == ["fist"]
    assert 550 <= fired[0][1] <= 700


def test_release_and_cooldown():
    sm = GestureStateMachine(GestureConfig(hold_ms=300, cooldown_ms=2000, min_interval_ms=100))
    fired1, t = feed(sm, FIST, 0, 500)
    _, t = feed(sm, None, t, 400)            # released
    fired2, t = feed(sm, FIST, t, 600)       # within cooldown → nothing
    _, t = feed(sm, None, t, 400)
    fired3, t = feed(sm, FIST, t + 1500, 600)
    assert len(fired1) == 1 and fired2 == [] and len(fired3) == 1


def test_short_dropout_does_not_reset_hold():
    sm = GestureStateMachine(GestureConfig(hold_ms=600))
    _, t = feed(sm, FIST, 0, 400)
    _, t = feed(sm, None, t, 100)            # 100 ms tracking loss
    fired, _ = feed(sm, FIST, t, 300)
    assert [g for g, _ in fired] == ["fist"]


def test_min_interval_between_different_gestures():
    sm = GestureStateMachine(GestureConfig(hold_ms=200, cooldown_ms=100, min_interval_ms=3000))
    fired1, t = feed(sm, FIST, 0, 400)
    fired2, t = feed(sm, POINT, t, 1000)
    assert len(fired1) == 1 and fired2 == []


def test_low_confidence_and_far_hands_are_ignored():
    sm = GestureStateMachine(GestureConfig(hold_ms=200, confidence=0.99))
    assert feed(sm, FIST, 0, 1000)[0] == []
    sm = GestureStateMachine(GestureConfig(hold_ms=200, min_palm_scale=0.5))
    assert feed(sm, FIST, 0, 1000)[0] == []  # synthetic palm scale is 0.2


def test_palm_zone_differs_from_open_palm():
    cfg = GestureConfig(hold_ms=200, zone_hold_ms=1000, zone=[0.0, 0.0, 1.0, 1.0])
    sm = GestureStateMachine(cfg)
    fired, _ = feed(sm, PALM, 0, 1500)
    assert [g for g, _ in fired] == ["palm_zone"] and fired[0][1] >= 1000
    sm = GestureStateMachine(GestureConfig(hold_ms=200, zone=[0.9, 0.0, 1.0, 0.1]))
    assert [g for g, _ in feed(sm, PALM, 0, 500)[0]] == ["open_palm"]


def test_paused_allows_only_pause_gesture():
    sm = GestureStateMachine(GestureConfig(hold_ms=200, zone=[0.9, 0.9, 1.0, 1.0]))
    assert feed(sm, FIST, 0, 600, allowed={"open_palm"})[0] == []
    _, t = feed(sm, None, 600, 300)
    assert [g for g, _ in feed(sm, PALM, t, 600, allowed={"open_palm"})[0]] == ["open_palm"]


# ----------------------------------------------------------------------------- engine
class FakeCamera:
    def __init__(self, fail=False):
        self.fail = fail
        self.opened = 0
        self.is_open = False
        self.broken = False

    def open(self):
        if self.fail:
            raise CameraError("Камера 0 не найдена или занята другой программой.")
        self.opened += 1
        self.is_open = True

    def read(self):
        if not self.is_open or self.broken:
            return None
        return np.full((48, 64, 3), 120, dtype=np.uint8)

    def close(self):
        self.is_open = False


class FakeTracker:
    def __init__(self):
        self.hand = None
        self.closed = False

    def detect(self, rgb, ts):
        return [(self.hand, 0.95)] if self.hand is not None else []

    def close(self):
        self.closed = True


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def vision_env(tmp_path, folders):
    camera, tracker = FakeCamera(), FakeTracker()
    models_dir = tmp_path / "models"
    (models_dir / "mediapipe-hand").mkdir(parents=True)
    (models_dir / "mediapipe-hand" / "hand_landmarker.task").write_bytes(b"x")
    controller = MockController()
    svc = Services.create(tmp_path / "data", controller=controller, folders=lambda: folders, models_dir=models_dir,
                          vision_options={"camera_factory": lambda index: camera,
                                          "tracker_factory": lambda path: tracker})
    svc.settings.update({"devices": {"camera_enabled": True},
                         "vision": {"hold_ms": 150, "cooldown_ms": 300, "min_interval_ms": 200, "zone_hold_ms": 500,
                                    "fps": 30, "zone": [0.95, 0.95, 1.0, 1.0]}})
    yield svc, camera, tracker, controller
    svc.close()


def test_camera_disabled_is_never_opened(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.settings.update({"devices": {"camera_enabled": False}})
    with pytest.raises(VisionError, match="выключена"):
        svc.vision.start()
    assert camera.opened == 0
    assert svc.vision.status()["state"] == "disabled"


def test_model_not_installed(tmp_path, folders):
    svc = Services.create(tmp_path / "d", controller=MockController(), folders=lambda: folders,
                          models_dir=tmp_path / "empty", vision_options={"camera_factory": lambda i: FakeCamera()})
    try:
        svc.settings.update({"devices": {"camera_enabled": True}})
        assert svc.vision.status()["state"] == "not_installed"
        with pytest.raises(VisionError, match="не установлена"):
            svc.vision.start()
    finally:
        svc.close()


def test_no_camera_reports_error_and_rest_works(tmp_path, folders):
    models_dir = tmp_path / "models"
    (models_dir / "mediapipe-hand").mkdir(parents=True)
    (models_dir / "mediapipe-hand" / "hand_landmarker.task").write_bytes(b"x")
    tracker = FakeTracker()
    svc = Services.create(tmp_path / "d", controller=MockController(), folders=lambda: folders, models_dir=models_dir,
                          vision_options={"camera_factory": lambda i: FakeCamera(fail=True),
                                          "tracker_factory": lambda p: tracker})
    try:
        svc.settings.update({"devices": {"camera_enabled": True}})
        with pytest.raises(VisionError, match="не найдена"):
            svc.vision.start()
        assert svc.vision.status()["state"] == "error"
        assert tracker.closed
        assert svc.assistant.handle_text("сверни все окна").status == Status.DONE
    finally:
        svc.close()


def test_gesture_runs_bound_action_through_permissions(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.settings.update({"vision": {"zone": [0.0, 0.0, 1.0, 1.0]}})  # palm anywhere = palm zone
    svc.vision.start()
    tracker.hand = make_hand(**PALM)
    assert wait_until(lambda: controller.called("minimize_all"))
    assert wait_until(lambda: svc.vision.status()["events"])
    tracker.hand = None
    event = svc.vision.status()["events"][-1]
    assert event["gesture"] == "palm_zone" and event["status"] == "done"
    audit = svc.journal.audit_entries(1)[0]
    assert audit["action"] == "window.minimize_all" and audit["source"] == "gesture"
    assert svc.journal.history(1)[0]["input"] == "жест: Ладонь в зоне"


def test_fist_cancels_open_question(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.assistant.handle_text("запусти")  # A.R.C. asks what to launch
    assert svc.assistant.state()["dialog"] is not None
    svc.vision.start()
    tracker.hand = make_hand(**FIST)
    assert wait_until(lambda: svc.assistant.state()["dialog"] is None)


def test_gesture_cannot_confirm_or_run_dangerous_things(vision_env):
    svc, camera, tracker, controller = vision_env
    with pytest.raises(ValueError):
        svc.settings.update({"vision": {"bindings": {"fist": {"action": "power.shutdown", "params": {"delay_s": 5}}}}})
    with pytest.raises(ValueError):
        svc.settings.update({"vision": {"bindings": {"fist": {"action": "files.create_folder",
                                                               "params": {"name": "x", "parent": "desktop"}}}}})
    response = svc.assistant.handle_text("выключи компьютер")
    from arc_backend.permissions.manager import ConfirmationError
    with pytest.raises(ConfirmationError):
        svc.permissions.resolve(response.confirmation.id, source=Source.GESTURE, acknowledge=True)
    # even a catalog action requested with a gesture source is checked again
    denied = svc.assistant.run_action(ActionRequest(action="power.shutdown", params={"delay_s": 5},
                                                    source=Source.GESTURE))
    assert denied.status == Status.DENIED and controller.called("power") == []


def test_emergency_stop_blocks_gestures(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.settings.update({"vision": {"bindings": {"victory": {"enabled": True, "action": "volume.mute",
                                                              "params": {"muted": True}}}}})
    svc.permissions.set_emergency_stop(True)
    svc.vision.start()
    tracker.hand = make_hand(fingers="11000", thumb="tucked")
    assert wait_until(lambda: svc.vision.status()["events"])
    assert svc.vision.status()["events"][-1]["status"] == "denied"
    assert controller.called("mute_set") == []


def test_open_palm_pauses_and_resumes(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.settings.update({"vision": {"bindings": {"victory": {"enabled": True, "action": "volume.mute",
                                                              "params": {"muted": True}}}}})
    svc.vision.start()
    tracker.hand = make_hand(**PALM)
    assert wait_until(lambda: svc.vision.status()["paused"])
    tracker.hand = make_hand(fingers="11000", thumb="tucked")  # victory while paused → ignored
    time.sleep(0.6)
    assert controller.called("mute_set") == []
    tracker.hand = None
    time.sleep(0.3)
    tracker.hand = make_hand(**PALM)
    assert wait_until(lambda: not svc.vision.status()["paused"])
    tracker.hand = None
    time.sleep(0.4)
    tracker.hand = make_hand(fingers="11000", thumb="tucked")
    assert wait_until(lambda: controller.called("mute_set"))


def test_index_up_requests_ui_toggle(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.vision.start()
    tracker.hand = make_hand(**POINT)
    assert wait_until(lambda: any(e.get("ui") == "toggle_compact" for e in svc.vision.status()["events"]))


def test_disabling_camera_stops_engine(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.vision.start()
    assert camera.is_open
    svc.settings.update({"devices": {"camera_enabled": False}})
    assert wait_until(lambda: not camera.is_open, timeout=4)
    assert wait_until(lambda: not svc.vision.running)


def test_broken_camera_recovers_to_error(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.vision.start()
    camera.broken = True
    assert wait_until(lambda: svc.vision.status()["state"] == "error" and not svc.vision.running, timeout=8)
    assert wait_until(lambda: not camera.is_open and tracker.closed)
    assert "перестала" in svc.vision.status()["message"]


def test_preview_only_in_setup_mode(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.vision.start()
    tracker.hand = make_hand(**PALM)
    time.sleep(0.3)
    assert svc.vision.preview_jpeg() is None
    svc.vision.set_preview(True)
    if importlib.util.find_spec("cv2"):
        assert wait_until(lambda: svc.vision.preview_jpeg() is not None)
        assert svc.vision.preview_jpeg()[:2] == b"\xff\xd8"
    svc.vision.set_preview(False)
    assert svc.vision.preview_jpeg() is None


def test_calibration_ignores_far_hands_afterwards(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.vision.start()
    tracker.hand = make_hand(**PALM, scale=1.5)
    svc.vision.set_paused(True)  # calibration must not trigger the pause gesture
    svc.vision.calibrate()
    assert wait_until(lambda: svc.settings.get().vision.calibration is not None, timeout=6)
    assert abs(svc.settings.get().vision.calibration.palm_scale - 0.3) < 0.02
    svc.vision.set_paused(False)
    tracker.hand = make_hand(**FIST, scale=0.5)        # far away person
    time.sleep(0.6)
    assert svc.vision.status()["gesture"] == "none"


def test_shutdown_releases_camera(vision_env):
    svc, camera, tracker, controller = vision_env
    svc.vision.start()
    thread = svc.vision._thread
    svc.vision.shutdown()
    assert not camera.is_open and tracker.closed
    assert thread is not None and not thread.is_alive()


def test_vision_api(vision_env):
    from fastapi.testclient import TestClient
    from arc_backend.api.server import create_app
    svc, camera, tracker, controller = vision_env
    token = "g" * 40
    with TestClient(create_app(svc, token, allowed_hosts=("testserver",))) as client:
        client.headers["X-ARC-Token"] = token
        assert client.post("/api/vision/start").json()["running"] is True
        assert client.get("/api/state").json()["camera"]["running"] is True
        assert client.post("/api/vision/pause", json={"paused": True}).json()["paused"] is True
        assert client.post("/api/vision/setup", json={"enabled": True}).json()["preview"] is True
        assert "image" in client.get("/api/vision/preview").json()
        actions = client.get("/api/vision/actions").json()["actions"]
        assert "window.minimize_all" in actions and "power.shutdown" not in actions
        assert client.post("/api/vision/stop").json()["running"] is False
        client.put("/api/settings", json={"devices": {"camera_enabled": False}})
        response = client.post("/api/vision/start")
        assert response.status_code == 409 and "выключена" in response.json()["detail"]
        bad = client.put("/api/settings", json={"vision": {"bindings": {"ok": {"action": "app.launch_admin",
                                                                              "params": {"app_id": "x"}}}}})
        assert bad.status_code == 400


def test_default_bindings_are_safe():
    from arc_backend.vision.actions import INTERNAL_ACTIONS
    from arc_backend.permissions.catalog import CATALOG
    for gesture, binding in Settings().vision.bindings.items():
        assert binding.action in INTERNAL_ACTIONS or (CATALOG[binding.action].risk.value == "A"
                                                      and CATALOG[binding.action].gesture_allowed)
