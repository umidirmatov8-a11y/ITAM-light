"""Temporal gesture logic: a gesture fires only after it is held steadily, never repeats while
still held (it must be released first), respects a per-gesture cooldown and a global minimum
interval between commands, and ignores far-away hands (people in the background)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .gestures import Observation, in_zone

JITTER_MS = 200  # short tracking drop-outs do not reset a hold


@dataclass
class GestureConfig:
    confidence: float = 0.7
    hold_ms: int = 600
    cooldown_ms: int = 1500
    min_interval_ms: int = 800
    zone: list[float] = field(default_factory=lambda: [0.65, 0.0, 1.0, 0.4])
    zone_hold_ms: int = 1500
    min_palm_scale: float = 0.0


@dataclass
class GestureStateMachine:
    config: GestureConfig = field(default_factory=GestureConfig)
    candidate: str = "none"
    since_ms: float = 0.0
    latched: Optional[str] = None          # fired and still held
    last_fire: dict[str, float] = field(default_factory=dict)
    last_any_ms: float = -1e12
    _mismatch_since: Optional[float] = None
    progress: float = 0.0

    def effective(self, obs: Optional[Observation]) -> str:
        cfg = self.config
        if obs is None or obs.gesture == "none" or obs.confidence < cfg.confidence:
            return "none"
        if obs.palm_scale < cfg.min_palm_scale:
            return "none"  # hand too far from the camera
        if obs.gesture == "open_palm" and in_zone(obs.center, cfg.zone):
            return "palm_zone"
        return obs.gesture

    def feed(self, obs: Optional[Observation], now_ms: float, allowed: Optional[set[str]] = None) -> Optional[str]:
        """Returns the gesture that fires on this frame, if any."""
        gesture = self.effective(obs)
        if gesture != self.candidate:
            if self._mismatch_since is None:
                self._mismatch_since = now_ms
            if now_ms - self._mismatch_since < JITTER_MS and self.candidate != "none":
                return None  # tolerate a flicker
            self.candidate, self.since_ms, self._mismatch_since = gesture, now_ms, None
            if self.latched is not None and gesture != self.latched:
                self.latched = None  # released
        else:
            self._mismatch_since = None
        if self.candidate == "none":
            self.progress = 0.0
            return None
        hold = self.config.zone_hold_ms if self.candidate == "palm_zone" else self.config.hold_ms
        held = now_ms - self.since_ms
        self.progress = min(1.0, held / hold)
        if held < hold or self.latched == self.candidate:
            return None
        if allowed is not None and self.candidate not in allowed:
            return None
        if now_ms - self.last_fire.get(self.candidate, -1e12) < self.config.cooldown_ms:
            return None
        if now_ms - self.last_any_ms < self.config.min_interval_ms:
            return None
        self.latched = self.candidate
        self.last_fire[self.candidate] = now_ms
        self.last_any_ms = now_ms
        return self.candidate

    def reset(self) -> None:
        self.candidate, self.since_ms, self.latched, self._mismatch_since, self.progress = "none", 0.0, None, None, 0.0
