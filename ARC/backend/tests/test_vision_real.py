"""Real MediaPipe hand landmarks on MediaPipe's own test photos (Apache 2.0, downloaded at test time).

Set ARC_TEST_MODELS to a directory; the hand model and the photos are downloaded there once.
"""
import os
import time
from pathlib import Path

import httpx
import pytest

from arc_backend.automation.controller import MockController
from arc_backend.services import Services
from arc_backend.vision.gestures import classify, largest_hand
from arc_backend.voice.models import ModelManager

MODELS = os.environ.get("ARC_TEST_MODELS")
pytestmark = pytest.mark.skipif(not MODELS, reason="ARC_TEST_MODELS not set")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("mediapipe")

PHOTOS = {"thumb_up.jpg": ["thumbs_up"], "pointing_up.jpg": ["index_up"], "fist.jpg": ["fist"],
          "victory.jpg": ["victory"], "right_hands.jpg": ["open_palm", "open_palm"],
          "left_hands.jpg": ["open_palm", "open_palm"]}


@pytest.fixture(scope="module")
def assets():
    root = Path(MODELS)
    mm = ModelManager(root)
    if not mm.installed("mediapipe-hand"):
        mm.start_download("mediapipe-hand", online_allowed=True)
        assert mm.wait("mediapipe-hand", 300).state == "done"
    photos = root / "hand-photos"
    photos.mkdir(parents=True, exist_ok=True)
    for name in PHOTOS:
        target = photos / name
        if not target.exists():
            data = httpx.get(f"https://storage.googleapis.com/mediapipe-assets/{name}", timeout=60,
                             follow_redirects=True)
            data.raise_for_status()
            target.write_bytes(data.content)
    return mm, photos


def test_real_photos_are_classified(assets):
    from arc_backend.vision.tracker import MediaPipeTracker
    mm, photos = assets
    tracker = MediaPipeTracker(mm.path("mediapipe-hand"), max_hands=2, video=False)
    try:
        for name, expected in PHOTOS.items():
            bgr = cv2.imread(str(photos / name))
            hands = tracker.detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), 0)
            got = sorted(classify(points, score).gesture for points, score in hands)
            print(name, got, [round(classify(p, s).confidence, 2) for p, s in hands])
            assert got == sorted(expected), name
            best = classify(*largest_hand(hands))
            assert best.confidence >= 0.7, (name, best)
    finally:
        tracker.close()


class PhotoCamera:
    """A "camera" that shows a photo (BGR), as OpenCvCamera would deliver it."""

    def __init__(self, frame):
        self.frame = frame
        self.is_open = False

    def open(self):
        self.is_open = True

    def read(self):
        return self.frame.copy() if self.is_open else None

    def close(self):
        self.is_open = False


def test_engine_with_real_tracker(assets, tmp_path):
    mm, photos = assets
    frame = cv2.imread(str(photos / "victory.jpg"))
    camera = PhotoCamera(frame)
    controller = MockController()
    svc = Services.create(tmp_path / "data", controller=controller, models_dir=Path(MODELS),
                          folders=lambda: {"desktop": str(tmp_path)},
                          vision_options={"camera_factory": lambda index: camera})
    try:
        svc.settings.update({"devices": {"camera_enabled": True},
                             "vision": {"bindings": {"victory": {"enabled": True, "action": "volume.mute",
                                                                 "params": {"muted": True}}}}})
        svc.vision.start()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not controller.called("mute_set"):
            time.sleep(0.05)
        status = svc.vision.status()
        print("fps", status["fps"], "gesture", status["gesture"], status["events"])
        assert controller.called("mute_set") == [(True,)]
        assert status["events"][-1]["gesture"] == "victory"
        assert status["landmarks"] and len(status["landmarks"]) == 21
        svc.vision.set_preview(True)
        time.sleep(0.5)
        jpeg = svc.vision.preview_jpeg()
        assert jpeg is not None and jpeg[:2] == b"\xff\xd8"
    finally:
        svc.close()
    assert not camera.is_open
    assert not list(Path(tmp_path).rglob("*.jpg")), "no frames may be written to disk"
