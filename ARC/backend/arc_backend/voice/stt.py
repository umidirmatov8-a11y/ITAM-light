"""Speech-to-text with faster-whisper (CTranslate2), fully local."""
from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Protocol

import numpy as np

from .audio import SAMPLE_RATE

log = logging.getLogger(__name__)

BASE_PROMPT = "АРК, открой Telegram. Запусти Steam. Увеличь громкость на двадцать процентов. Сверни все окна."


# Phrases Whisper produces on noise/silence (subtitle credits from its training data).
_HALLUCINATIONS = ("субтитр", "продолжение следует", "спасибо за просмотр", "редактор субтитров", "dimatorzok",
                   "подписывайтесь на канал", "amara.org")


def is_hallucination(text: str) -> bool:
    low = text.lower().strip(" .!?…")
    if not low:
        return True
    if any(h in low for h in _HALLUCINATIONS):
        return True
    # the prompt echoed back instead of real speech
    sentences = [x.strip().lower() for x in BASE_PROMPT.split(".") if x.strip()]
    return sum(1 for x in sentences if x in low) >= 2


@dataclass
class Transcript:
    text: str
    confidence: float
    language: str = "ru"
    duration_s: float = 0.0
    elapsed_s: float = 0.0


class Recognizer(Protocol):
    def transcribe(self, audio: np.ndarray, hints: Iterable[str] = ()) -> Transcript: ...
    @property
    def device(self) -> str: ...


def segment_confidence(segments: list) -> float:
    """exp(mean avg_logprob) weighted by text length, reduced when Whisper thinks it heard no speech."""
    if not segments:
        return 0.0
    total = sum(max(1, len(s.text.strip())) for s in segments)
    logprob = sum(s.avg_logprob * max(1, len(s.text.strip())) for s in segments) / total
    no_speech = max(getattr(s, "no_speech_prob", 0.0) for s in segments)
    return float(max(0.0, min(1.0, math.exp(logprob) * (1.0 - 0.6 * no_speech))))


def cuda_available() -> bool:
    try:
        import ctranslate2  # type: ignore
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class WhisperRecognizer:
    """Loads the model lazily from a local directory; never downloads anything itself."""

    def __init__(self, model_dir: Path, device: str = "auto", language: str = "ru"):
        self.model_dir = Path(model_dir)
        self.requested_device = device
        self.language = language
        self._model = None
        self._device = "cpu"
        self._lock = threading.Lock()
        self.load_error: Optional[str] = None

    @property
    def device(self) -> str:
        return self._device

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            if not (self.model_dir / "model.bin").is_file():
                raise RuntimeError("Модель распознавания речи не установлена. Загрузите её в «Настройки → Голос».")
            from faster_whisper import WhisperModel  # type: ignore
            want_cuda = self.requested_device == "cuda" or (self.requested_device == "auto" and cuda_available())
            attempts = [("cuda", "float16"), ("cpu", "int8")] if want_cuda else [("cpu", "int8")]
            last: Optional[Exception] = None
            for device, compute in attempts:
                try:
                    started = time.monotonic()
                    self._model = WhisperModel(str(self.model_dir), device=device, compute_type=compute,
                                               local_files_only=True)
                    self._device = device
                    self.load_error = None
                    log.info("whisper loaded from %s on %s/%s in %.1fs", self.model_dir, device, compute,
                             time.monotonic() - started)
                    return
                except Exception as exc:  # CUDA libraries missing → fall back to CPU
                    last = exc
                    log.warning("whisper on %s failed: %s", device, exc)
            self.load_error = str(last)
            raise RuntimeError(f"Не удалось загрузить модель распознавания: {last}")

    def transcribe(self, audio: np.ndarray, hints: Iterable[str] = ()) -> Transcript:
        self.load()
        started = time.monotonic()
        samples = audio.astype(np.float32) / 32768.0 if audio.dtype == np.int16 else audio.astype(np.float32)
        prompt = BASE_PROMPT
        extra = ", ".join(h for h in hints if h)[:300]
        if extra:
            prompt += " " + extra + "."
        assert self._model is not None
        segments, info = self._model.transcribe(
            samples, language=self.language, beam_size=5, vad_filter=False, condition_on_previous_text=False,
            initial_prompt=prompt, without_timestamps=True, temperature=0.0)
        segments = list(segments)
        text = " ".join(s.text.strip() for s in segments).strip()
        if is_hallucination(text):
            text = ""
        return Transcript(text=text, confidence=segment_confidence(segments) if text else 0.0,
                          language=getattr(info, "language", self.language),
                          duration_s=samples.size / SAMPLE_RATE, elapsed_s=time.monotonic() - started)
