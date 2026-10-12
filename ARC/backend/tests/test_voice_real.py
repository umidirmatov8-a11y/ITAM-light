"""End-to-end voice test with real local models (runs in Windows CI).

Set ARC_TEST_MODELS to a directory; missing models are downloaded there first (this is the
only place where a download happens without a click: it is the test's explicit purpose).
Chain: Piper speaks a Russian phrase → audio is fed frame by frame into the real VoiceEngine
(real VAD + faster-whisper) → Assistant → MockController records the action.
"""
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from arc_backend.automation.controller import MockController
from arc_backend.services import Services
from arc_backend.voice.audio import FRAME_SAMPLES, SAMPLE_RATE, resample
from arc_backend.voice.models import ModelManager
from arc_backend.voice.stt import WhisperRecognizer
from arc_backend.voice.tts import PiperSynthesizer

MODELS = os.environ.get("ARC_TEST_MODELS")
STT = os.environ.get("ARC_TEST_STT", "whisper-small")
pytestmark = [pytest.mark.skipif(not MODELS, reason="ARC_TEST_MODELS not set"),
              pytest.mark.skipif(sys.platform != "win32", reason="Piper runtime is downloaded for Windows")]


@pytest.fixture(scope="module")
def models():
    mm = ModelManager(Path(MODELS))
    for model_id in (STT, "piper-runtime", "piper-ru-irina"):
        if not mm.installed(model_id):
            mm.start_download(model_id, online_allowed=True)
            job = mm.wait(model_id, timeout=1200)
            assert job.state == "done", f"{model_id}: {job.message}"
    return mm


@pytest.fixture(scope="module")
def piper(models):
    return PiperSynthesizer(models.path("piper-runtime"), models.path("piper-ru-irina"))


class SignalAudio:
    """Feeds prepared audio into the engine as if it came from a microphone."""

    def __init__(self):
        self.callback = None
        self.signal = np.zeros(0, dtype=np.int16)

    @property
    def active(self):
        return self.callback is not None

    def start(self, on_frame):
        self.callback = on_frame

    def stop(self):
        self.callback = None

    def play(self):
        for i in range(0, self.signal.size - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            if self.callback is None:
                break
            self.callback(self.signal[i:i + FRAME_SAMPLES])
            time.sleep(0.002)


def say(piper, text):
    audio = resample(piper.synthesize(text), piper.sample_rate, SAMPLE_RATE)
    pad = np.zeros(SAMPLE_RATE // 2, dtype=np.int16)
    noise = (np.random.default_rng(0).normal(0, 30, pad.size)).astype(np.int16)
    return np.concatenate([noise, audio, noise, pad, pad])


@pytest.mark.parametrize("phrase,check", [
    ("Открой блокнот.", lambda c: any(a[0].lower().endswith("notepad.exe") for a in c.called("launch_exe"))),
    ("Сверни все окна.", lambda c: bool(c.called("minimize_all"))),
    ("Увеличь громкость на двадцать процентов.", lambda c: c.called("volume_step") == [(20,)]),
])
def test_spoken_command_is_executed(tmp_path, models, piper, phrase, check):
    audio = SignalAudio()
    spoken = []

    class Recorder:
        name = "recorder"

        def speak(self, text, rate=1.0, volume=80):
            spoken.append(text)

        def stop(self):
            pass

        def voices(self):
            return []

    controller = MockController()
    svc = Services.create(tmp_path / "data", controller=controller, models_dir=Path(MODELS),
                          folders=lambda: {"desktop": str(tmp_path)},
                          voice_options={"audio_factory": lambda d: audio,
                                         "recognizer_factory": lambda p, d: WhisperRecognizer(p, "cpu"),
                                         "synth_factory": lambda e, v, d: (Recorder(), None)})
    try:
        svc.settings.update({"voice": {"stt_model": STT}})
        audio.signal = say(piper, phrase)
        svc.voice.start_ptt()
        audio.play()
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not spoken:
            time.sleep(0.1)
        transcript = svc.voice.last_transcript
        print(f"\n{phrase!r} -> {transcript} -> {spoken}")
        assert transcript and transcript["text"], "nothing recognized"
        assert check(controller), f"command not executed; heard {transcript['text']!r}, replied {spoken}"
    finally:
        svc.close()


def test_piper_wav_and_sapi_voices(tmp_path, piper):
    wav = piper.synthesize_wav("Проверка голоса.", tmp_path / "check.wav")
    assert wav.stat().st_size > 10_000
    # kept for the CI step that runs the frozen arc-backend.exe --transcribe on it
    piper.synthesize_wav("Открой блокнот.", Path(MODELS) / "check-command.wav")
    from arc_backend.voice.tts import SapiSynthesizer
    voices = SapiSynthesizer().voices()
    print("SAPI voices:", voices)
    assert isinstance(voices, list)
