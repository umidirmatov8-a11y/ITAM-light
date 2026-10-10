"""ModelManager against a local HTTP server: consent, progress, atomic install, cancel, zip safety."""
import http.server
import io
import os
import threading
import zipfile
from functools import partial

import pytest

from arc_backend.voice.models import CATALOG, DownloadError, ModelManager, ModelSpec


class Handler(http.server.SimpleHTTPRequestHandler):
    slow = False

    def log_message(self, *args):
        pass

    def copyfile(self, source, outputfile):
        if self.slow:
            while chunk := source.read(4096):
                outputfile.write(chunk)
                threading.Event().wait(0.01)
        else:
            super().copyfile(source, outputfile)


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "www"
    root.mkdir()
    (root / "model.bin").write_bytes(os.urandom(300_000))
    (root / "config.json").write_text("{}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("piper/piper.exe", b"MZfake")
        zf.writestr("piper/espeak-ng-data/ru_dict", b"x")
    (root / "runtime.zip").write_bytes(buf.getvalue())
    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../escape.txt", b"pwned")
    (root / "evil.zip").write_bytes(evil.getvalue())
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(root)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def catalog(base):
    return {
        "stt-test": ModelSpec("stt-test", "STT", "stt", 1, ((f"{base}/model.bin", "model.bin"),
                                                         (f"{base}/config.json", "config.json")), marker="model.bin"),
        "zip-test": ModelSpec("zip-test", "ZIP", "tts_runtime", 1, ((f"{base}/runtime.zip", "r.zip"),),
                              archive=True, marker="piper/piper.exe"),
        "evil": ModelSpec("evil", "Evil", "tts_runtime", 1, ((f"{base}/evil.zip", "e.zip"),), archive=True,
                          marker="piper/piper.exe"),
        "missing": ModelSpec("missing", "404", "stt", 1, ((f"{base}/nope.bin", "model.bin"),), marker="model.bin"),
        "win-only": ModelSpec("win-only", "W", "tts_runtime", 1, ((f"{base}/model.bin", "x"),), platform="win98",
                              marker="x"),
    }


def test_download_installs_atomically(tmp_path, server):
    mm = ModelManager(tmp_path / "models", catalog(server))
    assert not mm.installed("stt-test")
    mm.start_download("stt-test", online_allowed=True)
    job = mm.wait("stt-test", 30)
    assert job.state == "done", job.message
    assert mm.installed("stt-test")
    assert (mm.path("stt-test") / "model.bin").stat().st_size == 300_000
    assert job.view()["progress"] == 1.0
    assert not any(p.name.startswith(".") for p in (tmp_path / "models").iterdir())
    with pytest.raises(DownloadError, match="уже установлена"):
        mm.start_download("stt-test", online_allowed=True)
    assert mm.remove("stt-test") and not mm.installed("stt-test")


def test_zip_runtime_and_zip_slip(tmp_path, server):
    mm = ModelManager(tmp_path / "models", catalog(server))
    mm.start_download("zip-test", online_allowed=True)
    assert mm.wait("zip-test", 30).state == "done"
    assert (mm.path("zip-test") / "piper" / "piper.exe").read_bytes() == b"MZfake"
    mm.start_download("evil", online_allowed=True)
    job = mm.wait("evil", 30)
    assert job.state == "error" and "Небезопасный путь" in job.message
    assert not (tmp_path / "escape.txt").exists() and not mm.installed("evil")


def test_refusals(tmp_path, server, monkeypatch):
    mm = ModelManager(tmp_path / "models", catalog(server))
    with pytest.raises(DownloadError, match="Онлайн-функции отключены"):
        mm.start_download("stt-test", online_allowed=False)
    with pytest.raises(DownloadError, match="только для Windows"):
        mm.start_download("win-only", online_allowed=True)
    monkeypatch.setattr(mm, "free_mb", lambda: 10)
    with pytest.raises(DownloadError, match="Недостаточно места"):
        mm.start_download("stt-test", online_allowed=True)


def test_http_error_leaves_nothing_installed(tmp_path, server):
    mm = ModelManager(tmp_path / "models", catalog(server))
    mm.start_download("missing", online_allowed=True)
    job = mm.wait("missing", 30)
    assert job.state == "error" and "404" in job.message
    assert not mm.installed("missing")
    assert list((tmp_path / "models").iterdir()) == []


def test_cancel(tmp_path, server, monkeypatch):
    monkeypatch.setattr(Handler, "slow", True)
    mm = ModelManager(tmp_path / "models", catalog(server))
    mm.start_download("stt-test", online_allowed=True)
    assert mm.cancel("stt-test")
    job = mm.wait("stt-test", 30)
    assert job.state == "cancelled"
    assert not mm.installed("stt-test")


def test_real_catalog_is_consistent():
    assert {"whisper-small", "piper-runtime", "piper-ru-irina"} <= set(CATALOG)
    for spec in CATALOG.values():
        assert spec.marker and spec.size_mb > 0
        for url, rel in spec.files:
            assert url.startswith("https://") and ".." not in rel
    whisper = CATALOG["whisper-small"]
    assert [rel for _, rel in whisper.files] == ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
