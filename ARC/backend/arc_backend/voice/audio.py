"""Microphone input. Frames are 16 kHz mono int16, FRAME_MS long."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, Protocol

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000

FrameCallback = Callable[[np.ndarray], None]


class AudioError(RuntimeError):
    """User-facing (Russian) message about the microphone."""


class AudioInput(Protocol):
    def start(self, on_frame: FrameCallback) -> None: ...
    def stop(self) -> None: ...
    @property
    def active(self) -> bool: ...


def rms_level(frame: np.ndarray) -> float:
    """0..1 loudness for the UI meter (log scale, -60 dBFS → 0)."""
    if frame.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean((frame.astype(np.float32) / 32768.0) ** 2)))
    if rms <= 1e-6:
        return 0.0
    db = 20 * np.log10(rms)
    return float(min(1.0, max(0.0, (db + 60.0) / 60.0)))


def resample(audio: np.ndarray, src_rate: int, dst_rate: int = SAMPLE_RATE) -> np.ndarray:
    if src_rate == dst_rate or audio.size == 0:
        return audio
    n = int(round(audio.size * dst_rate / src_rate))
    x_old = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio.astype(np.float32)).astype(np.int16)


def _sounddevice():
    try:
        import sounddevice as sd  # type: ignore
    except (ImportError, OSError) as exc:
        raise AudioError(f"Аудиосистема недоступна: {exc}") from exc
    return sd


def list_input_devices() -> list[dict]:
    """Input devices of the default host API. Empty list if audio is unavailable."""
    try:
        sd = _sounddevice()
        devices = sd.query_devices()
        default_api = sd.default.hostapi
        default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
    except (AudioError, Exception) as exc:  # PortAudioError is not exported when PortAudio is missing
        log.info("no audio devices: %s", exc)
        return []
    result = []
    for index, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0 and dev.get("hostapi") == default_api:
            result.append({"index": index, "name": dev["name"], "default": index == default_in,
                           "sample_rate": int(dev.get("default_samplerate") or SAMPLE_RATE)})
    return result


class SoundDeviceInput:
    """PortAudio capture via sounddevice. Resamples when the device refuses 16 kHz."""

    def __init__(self, device_name: Optional[str] = None):
        self._device_name = device_name
        self._stream = None
        self._lock = threading.Lock()
        self._rest = np.zeros(0, dtype=np.int16)

    @property
    def active(self) -> bool:
        return self._stream is not None

    def _device_index(self, sd) -> Optional[int]:
        if not self._device_name:
            return None
        for dev in list_input_devices():
            if dev["name"] == self._device_name:
                return dev["index"]
        raise AudioError(f"Микрофон «{self._device_name}» не найден. Выберите другой в настройках голоса.")

    def start(self, on_frame: FrameCallback) -> None:
        sd = _sounddevice()
        with self._lock:
            if self._stream is not None:
                return
            if not list_input_devices():
                raise AudioError("Микрофон не найден. Подключите микрофон или используйте текстовые команды.")
            index = self._device_index(sd)
            rate = SAMPLE_RATE
            try:
                sd.check_input_settings(device=index, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
            except Exception:
                rate = int(sd.query_devices(index if index is not None else sd.default.device[0])["default_samplerate"])
            self._rest = np.zeros(0, dtype=np.int16)
            block = rate * FRAME_MS // 1000

            def callback(indata, frames, _time, status):
                if status:
                    log.debug("audio status: %s", status)
                mono = indata[:, 0].copy()
                if rate != SAMPLE_RATE:
                    mono = resample(mono, rate)
                data = np.concatenate([self._rest, mono])
                while data.size >= FRAME_SAMPLES:
                    on_frame(data[:FRAME_SAMPLES])
                    data = data[FRAME_SAMPLES:]
                self._rest = data

            try:
                stream = sd.InputStream(device=index, samplerate=rate, channels=1, dtype="int16", blocksize=block,
                                        callback=callback)
                stream.start()
            except Exception as exc:
                raise AudioError(f"Не удалось открыть микрофон: {exc}. Проверьте «Конфиденциальность → Микрофон».") \
                    from exc
            self._stream = stream
            log.info("microphone opened (device=%s, rate=%s)", self._device_name or "default", rate)

    def stop(self) -> None:
        with self._lock:
            stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                log.warning("closing microphone: %s", exc)
