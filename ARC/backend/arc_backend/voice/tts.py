"""Text-to-speech: Windows SAPI (built in, offline) or Piper (optional local program)."""
from __future__ import annotations

import json
import logging
import math
import subprocess
import sys
import threading
import wave
from pathlib import Path
from typing import Optional, Protocol

import numpy as np

log = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class TtsError(RuntimeError):
    pass


class Synthesizer(Protocol):
    name: str

    def speak(self, text: str, rate: float = 1.0, volume: int = 80) -> None: ...
    def stop(self) -> None: ...
    def voices(self) -> list[dict]: ...


class NullSynthesizer:
    name = "off"

    def speak(self, text: str, rate: float = 1.0, volume: int = 80) -> None:
        return None

    def stop(self) -> None:
        return None

    def voices(self) -> list[dict]:
        return []


# --------------------------------------------------------------------------- SAPI
class SapiSynthesizer:
    """Microsoft Speech API via COM. Russian voice (e.g. "Microsoft Irina") comes with the ru-RU speech pack."""

    name = "sapi"
    RU_LCID = "419"

    def __init__(self, voice_name: str = ""):
        if sys.platform != "win32":
            raise TtsError("SAPI доступен только в Windows")
        self.voice_name = voice_name
        self._stop = threading.Event()
        self._lock = threading.Lock()

    @staticmethod
    def _com():
        import comtypes  # type: ignore
        import comtypes.client  # type: ignore
        return comtypes, comtypes.client

    def voices(self) -> list[dict]:
        comtypes, client = self._com()
        comtypes.CoInitialize()
        try:
            sp = client.CreateObject("SAPI.SpVoice", dynamic=True)
            tokens = sp.GetVoices()
            result = []
            for i in range(tokens.Count):
                token = tokens.Item(i)
                lang = str(token.GetAttribute("Language") or "")
                result.append({"name": token.GetDescription(), "language": lang,
                               "russian": self.RU_LCID in lang.lower().split(";")})
            return result
        finally:
            comtypes.CoUninitialize()

    def speak(self, text: str, rate: float = 1.0, volume: int = 80) -> None:
        comtypes, client = self._com()
        with self._lock:
            self._stop.clear()
            comtypes.CoInitialize()
            try:
                sp = client.CreateObject("SAPI.SpVoice", dynamic=True)
                tokens = sp.GetVoices()
                chosen = None
                for i in range(tokens.Count):
                    token = tokens.Item(i)
                    desc = token.GetDescription()
                    lang = str(token.GetAttribute("Language") or "").lower().split(";")
                    if (self.voice_name and desc == self.voice_name) or (not self.voice_name and self.RU_LCID in lang):
                        chosen = token
                        break
                if chosen is not None:
                    sp.Voice = chosen
                sp.Rate = max(-10, min(10, round(10 * math.log2(rate))))
                sp.Volume = max(0, min(100, volume))
                sp.Speak(text, 1)  # SVSFlagsAsync
                while not sp.WaitUntilDone(100):
                    if self._stop.is_set():
                        sp.Speak("", 3)  # purge
                        break
            finally:
                comtypes.CoUninitialize()

    def stop(self) -> None:
        self._stop.set()


# --------------------------------------------------------------------------- Piper
class PiperSynthesizer:
    """Runs piper.exe (separate MIT-licensed program) with the text on stdin; never through a shell."""

    name = "piper"

    def __init__(self, runtime_dir: Path, voice_dir: Path):
        exe_name = "piper.exe" if sys.platform == "win32" else "piper"
        self.exe = Path(runtime_dir) / "piper" / exe_name
        self.model = Path(voice_dir) / "voice.onnx"
        config = Path(voice_dir) / "voice.onnx.json"
        if not self.exe.is_file():
            raise TtsError("Piper не установлен. Загрузите «Piper — программа» в настройках голоса.")
        if not self.model.is_file() or not config.is_file():
            raise TtsError("Голос Piper не установлен")
        self.sample_rate = int(json.loads(config.read_text(encoding="utf-8")).get("audio", {}).get("sample_rate", 22050))
        self._stop = threading.Event()

    def voices(self) -> list[dict]:
        return [{"name": self.model.parent.name, "language": "ru", "russian": True}]

    def _args(self, rate: float, extra: list[str]) -> list[str]:
        return [str(self.exe), "--model", str(self.model), "--length_scale", f"{1.0 / rate:.2f}", *extra]

    def synthesize(self, text: str, rate: float = 1.0) -> np.ndarray:
        proc = subprocess.run(self._args(rate, ["--output_raw"]), input=text.encode("utf-8"), capture_output=True,
                              timeout=60, creationflags=_NO_WINDOW, cwd=str(self.exe.parent))
        if proc.returncode != 0:
            raise TtsError(f"Piper завершился с ошибкой: {proc.stderr.decode('utf-8', 'replace')[-300:]}")
        return np.frombuffer(proc.stdout, dtype=np.int16)

    def synthesize_wav(self, text: str, path: Path, rate: float = 1.0) -> Path:
        audio = self.synthesize(text, rate)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio.tobytes())
        return path

    def speak(self, text: str, rate: float = 1.0, volume: int = 80) -> None:
        self._stop.clear()
        audio = self.synthesize(text, rate)
        if self._stop.is_set() or audio.size == 0:
            return
        audio = (audio.astype(np.float32) * (volume / 100.0)).astype(np.int16)
        try:
            import sounddevice as sd  # type: ignore
        except (ImportError, OSError) as exc:
            raise TtsError(f"Нет устройства вывода звука: {exc}")
        sd.play(audio, self.sample_rate)
        duration = audio.size / self.sample_rate
        if self._stop.wait(timeout=duration + 0.3):
            sd.stop()

    def stop(self) -> None:
        self._stop.set()


def create_synthesizer(engine: str, voice: str, models_dir: Path) -> tuple[Synthesizer, Optional[str]]:
    """Returns (synthesizer, warning). Falls back to silence with a reason instead of failing."""
    if engine == "off":
        return NullSynthesizer(), None
    try:
        if engine == "piper":
            voice_id = voice if voice.startswith("piper-ru-") else "piper-ru-irina"
            return PiperSynthesizer(models_dir / "piper-runtime", models_dir / voice_id), None
        return SapiSynthesizer(voice), None
    except TtsError as exc:
        return NullSynthesizer(), str(exc)
