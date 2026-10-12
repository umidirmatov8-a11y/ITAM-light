"""Energy-based voice activity detector with an adaptive noise floor (no extra dependencies)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .audio import FRAME_MS

CALIBRATION_FRAMES = 6
MAX_CALIBRATED_NOISE_DB = -35.0


def frame_db(frame: np.ndarray) -> float:
    if frame.size == 0:
        return -100.0
    rms = float(np.sqrt(np.mean((frame.astype(np.float32) / 32768.0) ** 2)))
    return 20.0 * np.log10(max(rms, 1e-7))


@dataclass
class VadConfig:
    sensitivity: float = 0.5        # 0 = needs loud speech, 1 = reacts to quiet speech
    silence_ms: int = 800           # end of utterance after this much silence
    min_speech_ms: int = 240        # shorter bursts (clicks, coughs) are dropped
    max_utterance_s: float = 12.0
    preroll_ms: int = 240           # audio kept before the speech onset

    @property
    def margin_db(self) -> float:
        # how far above the noise floor speech must be: 16 dB (insensitive) .. 6 dB (sensitive)
        return 16.0 - 10.0 * self.sensitivity


@dataclass
class EnergyVAD:
    config: VadConfig = field(default_factory=VadConfig)
    noise_db: float = -60.0
    calibrated: bool = False
    _calibration: list[float] = field(default_factory=list)
    _speech: list[np.ndarray] = field(default_factory=list)
    _preroll: list[np.ndarray] = field(default_factory=list)
    _in_speech: bool = False
    _speech_frames: int = 0
    _silence_frames: int = 0

    def reset(self) -> None:
        self._speech, self._preroll = [], []
        self._in_speech = False
        self._speech_frames = self._silence_frames = 0

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def is_speech(self, db: float) -> bool:
        return db > max(self.noise_db + self.config.margin_db, -55.0)

    def process(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Feed one frame; returns a complete utterance (int16) when one ends, else None."""
        db = frame_db(frame)
        if not self.calibrated:
            # the first ~180 ms after opening the microphone are taken as background noise
            self._calibration.append(db)
            if len(self._calibration) >= CALIBRATION_FRAMES:
                # a loud start means the user is already talking: rooms are rarely louder than -35 dBFS
                self.noise_db = min(float(np.median(self._calibration)), MAX_CALIBRATED_NOISE_DB)
                self.calibrated = True
            self._preroll.append(frame)
            return None
        speech = self.is_speech(db)
        if db < self.noise_db:
            self.noise_db += (db - self.noise_db) * 0.3      # follow quieter rooms quickly
        elif not speech:
            self.noise_db += (db - self.noise_db) * 0.05
        else:
            self.noise_db += (db - self.noise_db) * 0.004    # steady noise eventually stops counting as speech
        cfg = self.config
        if not self._in_speech:
            self._preroll.append(frame)
            if len(self._preroll) > max(1, cfg.preroll_ms // FRAME_MS):
                self._preroll.pop(0)
            if speech:
                self._in_speech = True
                self._speech = list(self._preroll)
                self._preroll = []
                self._speech_frames = 1
                self._silence_frames = 0
            return None
        self._speech.append(frame)
        if speech:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._silence_frames += 1
        total_ms = len(self._speech) * FRAME_MS
        if self._silence_frames * FRAME_MS >= cfg.silence_ms or total_ms >= cfg.max_utterance_s * 1000:
            return self._finish()
        return None

    def flush(self) -> Optional[np.ndarray]:
        """Ends the current utterance (push-to-talk released)."""
        return self._finish() if self._in_speech else None

    def _finish(self) -> Optional[np.ndarray]:
        frames, voiced = self._speech, self._speech_frames
        self.reset()
        if voiced * FRAME_MS < self.config.min_speech_ms:
            return None
        return np.concatenate(frames)
