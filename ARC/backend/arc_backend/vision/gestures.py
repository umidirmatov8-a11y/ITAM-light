"""Rule-based hand-gesture classifier on MediaPipe's 21 hand landmarks.

Rotation- and scale-invariant: finger states use joint angles and distances relative to the
palm size, so a hand held sideways or upside down is still recognized. Thresholds were tuned on
MediaPipe's own test photos (see tests/test_vision_real.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

WRIST = 0
FINGERS = {"index": (5, 6, 7, 8), "middle": (9, 10, 11, 12), "ring": (13, 14, 15, 16), "pinky": (17, 18, 19, 20)}
THUMB = (1, 2, 3, 4)

GESTURE_TITLES = {
    "open_palm": "Открытая ладонь",
    "fist": "Кулак",
    "thumbs_up": "Большой палец вверх",
    "index_up": "Указательный палец вверх",
    "ok": "Жест «OK»",
    "victory": "Два пальца (V)",
    "palm_zone": "Ладонь в зоне",
    "none": "—",
}


@dataclass
class FingerState:
    extended: float  # 0..1 how clearly the finger is straight
    folded: float    # 0..1 how clearly the finger is bent


@dataclass
class Observation:
    gesture: str                   # one of GESTURE_TITLES (palm_zone is decided later by the state machine)
    confidence: float
    palm_scale: float              # wrist → middle MCP distance, fraction of the frame
    center: tuple[float, float]    # palm centre in normalized image coordinates
    fingers: dict[str, str] = field(default_factory=dict)


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def finger_state(p: np.ndarray, mcp: int, pip: int, tip: int) -> FingerState:
    straight = _cos(p[pip] - p[mcp], p[tip] - p[pip])
    reach = np.linalg.norm(p[tip, :2] - p[WRIST, :2]) / max(np.linalg.norm(p[pip, :2] - p[WRIST, :2]), 1e-9)
    extended = min(_clip01((straight - 0.5) / 0.4), _clip01((reach - 1.05) / 0.2))
    folded = max(_clip01((0.3 - straight) / 0.5), _clip01((0.95 - reach) / 0.2))
    return FingerState(extended, folded)


def classify(landmarks: np.ndarray, detection_score: float = 1.0) -> Observation:
    p = np.asarray(landmarks, dtype=np.float64)
    if p.shape != (21, 3):
        raise ValueError("expected 21x3 landmarks")
    palm = float(np.linalg.norm(p[9, :2] - p[WRIST, :2]))
    center = (float(np.mean(p[[0, 5, 9, 13, 17], 0])), float(np.mean(p[[0, 5, 9, 13, 17], 1])))
    if palm < 1e-6:
        return Observation("none", 0.0, palm, center)

    fingers = {name: finger_state(p, m, pi, t) for name, (m, pi, _d, t) in FINGERS.items()}
    ext = {n: f.extended for n, f in fingers.items()}
    fold = {n: f.folded for n, f in fingers.items()}

    thumb_straight = _cos(p[3] - p[2], p[4] - p[3])
    thumb_reach = float(np.linalg.norm(p[4, :2] - p[5, :2]) / palm)       # tip ↔ index knuckle
    thumb_out = min(_clip01((thumb_straight - 0.5) / 0.3), _clip01((thumb_reach - 0.5) / 0.2))
    thumb_tucked = _clip01((0.35 - thumb_reach) / 0.15)
    thumb_vec = p[4, :2] - p[2, :2]
    thumb_angle = float(np.degrees(np.arctan2(-thumb_vec[1], thumb_vec[0])))  # image y grows downwards
    thumb_up = _clip01(1.0 - (abs(thumb_angle - 90.0) - 25.0) / 50.0)   # full score within ±25° of vertical
    pinch = float(np.linalg.norm(p[4, :2] - p[8, :2]) / palm)                  # thumb tip ↔ index tip
    index_vec = p[8, :2] - p[5, :2]
    index_up = _clip01(1.0 - (abs(float(np.degrees(np.arctan2(-index_vec[1], index_vec[0]))) - 90.0) - 25.0) / 45.0)

    others_folded = min(fold["middle"], fold["ring"], fold["pinky"])
    candidates = {
        "open_palm": min(ext["index"], ext["middle"], ext["ring"], ext["pinky"], _clip01((thumb_reach - 0.25) / 0.1)),
        "fist": min(fold["index"], others_folded, max(thumb_tucked, 1.0 - thumb_out)),
        "thumbs_up": min(fold["index"], others_folded, thumb_out, thumb_up),
        "index_up": min(ext["index"], others_folded, index_up, 1.0 - thumb_out),
        "victory": min(ext["index"], ext["middle"], fold["ring"], fold["pinky"]),
        "ok": min(_clip01((0.35 - pinch) / 0.15), ext["middle"], ext["ring"], ext["pinky"]),
    }
    best = max(candidates, key=candidates.get)
    score = candidates[best]
    labels = {n: ("вытянут" if f.extended > 0.5 else "согнут" if f.folded > 0.5 else "?") for n, f in fingers.items()}
    labels["thumb"] = "отведён" if thumb_reach > 0.3 else "прижат"
    if score < 0.3:
        return Observation("none", score * detection_score, palm, center, labels)
    return Observation(best, score * detection_score, palm, center, labels)


def in_zone(center: tuple[float, float], zone: list[float]) -> bool:
    x0, y0, x1, y1 = zone
    return x0 <= center[0] <= x1 and y0 <= center[1] <= y1


def largest_hand(hands: list[tuple[np.ndarray, float]]) -> Optional[tuple[np.ndarray, float]]:
    """Several hands in view: the closest (largest) one controls A.R.C."""
    if not hands:
        return None
    return max(hands, key=lambda h: float(np.linalg.norm(h[0][9, :2] - h[0][0, :2])))
