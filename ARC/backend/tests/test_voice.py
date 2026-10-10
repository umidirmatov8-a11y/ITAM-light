"""Voice Engine with fake microphone, recognizer and synthesizer (no audio hardware, no models)."""
import threading
import time

import numpy as np
import pytest

from arc_backend.automation.controller import MockController
from arc_backend.models import Status
from arc_backend.services import Services
from arc_backend.voice.audio import FRAME_SAMPLES, SAMPLE_RATE, AudioError, resample, rms_level
from arc_backend.voice.engine import VoiceError, VoiceState
from arc_backend.voice.stt import Transcript, is_hallucination, segment_confidence
from arc_backend.voice.vad import EnergyVAD, VadConfig


# ----------------------------------------------------------------------------- signals
def silence(ms: int, amp: float = 0.001) -> np.ndarray:
    rng = np.random.default_rng(1)
    return (rng.normal(0, amp, SAMPLE_RATE * ms // 1000) * 32767).astype(np.int16)


def speech(ms: int, amp: float = 0.3) -> np.ndarray:
    t = np.arange(SAMPLE_RATE * ms // 1000) / SAMPLE_RATE
    wave = np.sin(2 * np.pi * 220 * t) * 0.6 + np.sin(2 * np.pi * 530 * t) * 0.4
    return (wave * amp * 32767).astype(np.int16)


def frames(signal: np.ndarray):
    for i in range(0, signal.size - FRAME_SAMPLES + 1, FRAME_SAMPLES):
        yield signal[i:i + FRAME_SAMPLES]


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# ----------------------------------------------------------------------------- fakes
class FakeAudio:
    def __init__(self, fail: str = ""):
        self.fail = fail
        self.callback = None
        self.opened = 0

    @property
    def active(self):
        return self.callback is not None

    def start(self, on_frame):
        if self.fail:
            raise AudioError(self.fail)
        self.callback = on_frame
        self.opened += 1

    def stop(self):
        self.callback = None

    def feed(self, signal: np.ndarray):
        for frame in frames(signal):
            if self.callback is None:
                return
            self.callback(frame)


class FakeRecognizer:
    device = "cpu"
    loaded = True

    def __init__(self):
        self.script: list[Transcript] = []
        self.calls: list[int] = []
        self.hints: list[str] = []

    def transcribe(self, audio, hints=()):
        self.calls.append(audio.size)
        self.hints = list(hints)
        return self.script.pop(0) if self.script else Transcript("", 0.0)


class FakeSynth:
    name = "fake"

    def __init__(self):
        self.spoken: list[str] = []

    def speak(self, text, rate=1.0, volume=80):
        self.spoken.append(text)

    def stop(self):
        pass

    def voices(self):
        return [{"name": "Fake", "language": "419", "russian": True}]


@pytest.fixture
def voice_env(tmp_path, folders):
    audio, rec, synth = FakeAudio(), FakeRecognizer(), FakeSynth()
    models_dir = tmp_path / "models"
    (models_dir / "whisper-small").mkdir(parents=True)
    (models_dir / "whisper-small" / "model.bin").write_bytes(b"x")
    controller = MockController()
    svc = Services.create(tmp_path / "data", controller=controller, folders=lambda: folders, models_dir=models_dir,
                          voice_options={"audio_factory": lambda device: audio,
                                         "recognizer_factory": lambda path, device: rec,
                                         "synth_factory": lambda engine, voice, d: (synth, None),
                                         "device_lister": lambda: [{"index": 0, "name": "Fake Mic", "default": True}]})
    yield svc, audio, rec, synth, controller
    svc.close()


# ----------------------------------------------------------------------------- unit: audio / vad / stt
def test_levels_and_resample():
    assert rms_level(silence(30)) < 0.1
    assert rms_level(speech(30)) > 0.7
    assert resample(np.ones(480, dtype=np.int16), 48000).size == 160


def test_vad_detects_one_utterance():
    vad = EnergyVAD(VadConfig(silence_ms=600))
    out = []
    for frame in frames(np.concatenate([silence(1000), speech(900), silence(900)])):
        result = vad.process(frame)
        if result is not None:
            out.append(result)
    assert len(out) == 1
    duration_ms = out[0].size * 1000 / SAMPLE_RATE
    assert 900 <= duration_ms <= 900 + 600 + 300  # speech + trailing silence + preroll


def test_vad_ignores_clicks_and_limits_length():
    vad = EnergyVAD(VadConfig(silence_ms=500, max_utterance_s=3))
    results = [vad.process(f) for f in frames(np.concatenate([silence(600), speech(90), silence(700)]))]
    assert all(r is None for r in results)  # 90 ms click is not speech
    results = [vad.process(f) for f in frames(np.concatenate([silence(300), speech(5000)]))]
    cut = [r for r in results if r is not None]
    assert len(cut) == 1 and cut[0].size <= 3.4 * SAMPLE_RATE


def test_vad_adapts_to_noise():
    vad = EnergyVAD(VadConfig(sensitivity=0.5))
    for f in frames(silence(2000, amp=0.02)):  # steady fan noise
        vad.process(f)
    assert not vad.in_speech
    assert vad.noise_db > -40


def test_confidence_and_hallucinations():
    class Seg:
        def __init__(self, text, logprob, nsp=0.0):
            self.text, self.avg_logprob, self.no_speech_prob = text, logprob, nsp
    assert segment_confidence([Seg("открой блокнот", -0.1)]) > 0.85
    assert segment_confidence([Seg("ээ", -1.5)]) < 0.3
    assert segment_confidence([Seg("открой", -0.1, nsp=0.9)]) < 0.5
    assert segment_confidence([]) == 0.0
    assert is_hallucination("Субтитры сделал DimaTorzok")
    assert is_hallucination("Продолжение следует...")
    assert not is_hallucination("Сверни все окна")


# ----------------------------------------------------------------------------- engine
def test_push_to_talk_executes_command_and_speaks(voice_env):
    svc, audio, rec, synth, controller = voice_env
    rec.script.append(Transcript("Открой блокнот", 0.9))
    status = svc.voice.start_ptt()
    assert status["state"] == "listening" and status["capturing"]
    audio.feed(np.concatenate([silence(300), speech(800), silence(1000)]))
    assert wait_until(lambda: synth.spoken)
    assert synth.spoken == ["Запускаю «Блокнот»."]
    assert controller.called("launch_exe")[0][0].endswith("notepad.exe")
    assert wait_until(lambda: svc.voice.status()["state"] == "idle")
    assert not audio.active, "microphone must be closed after push-to-talk"
    entry = svc.journal.audit_entries(1)[0]
    assert entry["source"] == "voice" and entry["action"] == "app.launch"
    assert "Блокнот" in rec.hints  # registry names bias recognition


def test_ptt_second_press_finishes_utterance(voice_env):
    svc, audio, rec, synth, controller = voice_env
    rec.script.append(Transcript("сверни все окна", 0.8))
    svc.voice.toggle_ptt()
    audio.feed(np.concatenate([silence(200), speech(700)]))  # still talking, no trailing silence
    svc.voice.toggle_ptt()
    assert wait_until(lambda: controller.called("minimize_all"))
    assert wait_until(lambda: synth.spoken == ["Окна свёрнуты."])


def test_continuous_requires_wake_word(voice_env):
    svc, audio, rec, synth, controller = voice_env
    svc.voice.set_continuous(True)
    rec.script += [Transcript("открой блокнот", 0.95), Transcript("АРК, открой блокнот", 0.95)]
    audio.feed(np.concatenate([silence(300), speech(700), silence(1000)]))
    assert wait_until(lambda: len(rec.calls) == 1)
    time.sleep(0.1)
    assert controller.called("launch_exe") == []  # background speech without the wake word
    assert synth.spoken == []
    audio.feed(np.concatenate([speech(700), silence(1000)]))
    assert wait_until(lambda: controller.called("launch_exe"))
    assert audio.active and svc.voice.status()["continuous"]
    svc.voice.set_continuous(False)
    assert not audio.active


def test_low_confidence(voice_env):
    svc, audio, rec, synth, controller = voice_env
    rec.script.append(Transcript("открой блокнот", 0.2))
    svc.voice.start_ptt()
    audio.feed(np.concatenate([speech(700), silence(1000)]))
    assert wait_until(lambda: synth.spoken)
    assert synth.spoken == ["Не расслышал команду. Повторите, пожалуйста."]
    assert controller.called("launch_exe") == []


def test_silent_mode_mutes_replies(voice_env):
    svc, audio, rec, synth, controller = voice_env
    svc.settings.update({"profile": {"silent": True}})
    rec.script.append(Transcript("который час", 0.9))
    svc.voice.start_ptt()
    audio.feed(np.concatenate([speech(700), silence(1000)]))
    assert wait_until(lambda: svc.voice.last_transcript is not None)
    assert wait_until(lambda: svc.voice.status()["state"] == "idle")
    assert synth.spoken == []
    assert svc.journal.history(1)[0]["intent"] == "system.info"


def test_microphone_disabled_is_never_opened(voice_env):
    svc, audio, rec, synth, controller = voice_env
    svc.settings.update({"devices": {"microphone_enabled": False}})
    with pytest.raises(VoiceError, match="выключен"):
        svc.voice.start_ptt()
    assert audio.opened == 0
    assert svc.voice.status()["state"] == VoiceState.DISABLED.value


def test_disabling_microphone_closes_it(voice_env):
    svc, audio, rec, synth, controller = voice_env
    svc.voice.set_continuous(True)
    assert audio.active
    svc.settings.update({"devices": {"microphone_enabled": False}})
    assert wait_until(lambda: not audio.active, timeout=3)


def test_no_microphone_keeps_text_commands_working(tmp_path, folders):
    models_dir = tmp_path / "models"
    (models_dir / "whisper-small").mkdir(parents=True)
    (models_dir / "whisper-small" / "model.bin").write_bytes(b"x")
    svc = Services.create(tmp_path / "d", controller=MockController(), folders=lambda: folders, models_dir=models_dir,
                          voice_options={"audio_factory": lambda d: FakeAudio(fail="Микрофон не найден."),
                                         "recognizer_factory": lambda p, d: FakeRecognizer(),
                                         "synth_factory": lambda e, v, d: (FakeSynth(), None),
                                         "device_lister": lambda: []})
    try:
        with pytest.raises(VoiceError, match="Микрофон не найден"):
            svc.voice.start_ptt()
        assert svc.voice.status()["state"] == "error"
        assert svc.assistant.handle_text("открой блокнот").status == Status.DONE
    finally:
        svc.close()


def test_model_not_installed_is_reported_not_downloaded(tmp_path, folders, monkeypatch):
    svc = Services.create(tmp_path / "d", controller=MockController(), folders=lambda: folders,
                          models_dir=tmp_path / "empty-models",
                          voice_options={"audio_factory": lambda d: FakeAudio()})
    downloads = []
    monkeypatch.setattr(svc.models, "start_download", lambda *a, **k: downloads.append(a))
    try:
        assert svc.voice.status()["state"] == "not_installed"
        with pytest.raises(VoiceError, match="не установлена"):
            svc.voice.start_ptt()
        assert downloads == []
    finally:
        svc.close()


def test_half_duplex_ignores_audio_while_speaking(voice_env):
    svc, audio, rec, synth, controller = voice_env
    gate = threading.Event()

    class SlowSynth(FakeSynth):
        def speak(self, text, rate=1.0, volume=80):
            super().speak(text)
            # A.R.C.'s own voice reaches the microphone while speaking
            audio.feed(np.concatenate([speech(800), silence(1000)]))
            gate.set()

    slow = SlowSynth()
    svc.voice._synth_factory = lambda e, v, d: (slow, None)
    svc.voice._synth = None
    svc.voice.set_continuous(True)
    rec.script.append(Transcript("арк который час", 0.9))
    audio.feed(np.concatenate([speech(700), silence(1000)]))
    assert gate.wait(5)
    time.sleep(0.3)
    assert len(rec.calls) == 1, "speech captured during the reply must not be recognized"


def test_shutdown_stops_worker(voice_env):
    svc, audio, rec, synth, controller = voice_env
    svc.voice.set_continuous(True)
    worker = svc.voice._worker
    svc.voice.shutdown()
    assert not audio.active
    assert worker is not None and not worker.is_alive()


def test_voice_status_in_api_state(voice_env):
    from fastapi.testclient import TestClient
    from arc_backend.api.server import create_app
    svc, audio, rec, synth, controller = voice_env
    token = "v" * 40
    with TestClient(create_app(svc, token, allowed_hosts=("testserver",))) as client:
        client.headers["X-ARC-Token"] = token
        assert client.get("/api/state").json()["voice"]["state"] == "idle"
        assert client.post("/api/voice/ptt", json={"action": "start"}).json()["state"] == "listening"
        assert client.post("/api/voice/ptt", json={"action": "stop"}).status_code == 200
        assert client.post("/api/voice/listen", json={"enabled": True}).json()["continuous"] is True
        assert client.post("/api/voice/listen", json={"enabled": False}).json()["continuous"] is False
        assert client.get("/api/voice/devices").json()["inputs"][0]["name"] == "Fake Mic"
        assert client.post("/api/voice/tts-test").json()["spoken"] is True
        client.put("/api/settings", json={"devices": {"microphone_enabled": False}})
        response = client.post("/api/voice/ptt", json={"action": "start"})
        assert response.status_code == 409 and "выключен" in response.json()["detail"]
        assert client.post("/api/voice/models/download", json={"id": "whisper-tiny"}).status_code == 400  # no confirm
