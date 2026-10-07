import json
import os
import stat
import sys
import textwrap

import pytest

from app.config import Settings
from app.local_runtime import (_DEVICE_CACHE, LlamaServer, LocalModelProvider, describe_device, list_local_models,
                               resolve_model)
from app.pipeline import AgentPipeline
from app.providers import ProviderError

FAKE_SERVER = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer
    args = sys.argv[1:]
    if args == ["--list-devices"]:
        print("Available devices:")
        if os.environ.get("FAKE_GPU"):
            print("  Vulkan0: Fake Radeon 9000 (8176 MiB, 8000 MiB free)")
        sys.exit(0)
    port = int(args[args.index("--port") + 1])
    log = open(args[args.index("-m") + 1] + ".requests", "a", encoding="utf-8")
    gpu = "999" in args
    if gpu and os.environ.get("FAKE_GPU") == "broken":
        print("ggml_vulkan: device lost", flush=True); sys.exit(1)
    if "--device" in args and os.environ.get("FAKE_OLD_BUILD"):
        print("error: invalid argument: --device", flush=True); sys.exit(1)
    if gpu and os.environ.get("FAKE_GPU") in ("ok", "crash-on-chat", "garbage"):
        print("ggml_vulkan: 0 = Fake Radeon 9000 (AMD proprietary driver) | uma: 0 | fp16: 1", flush=True)
        print("load_tensors: offloaded 37/37 layers to GPU", flush=True)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, body):
            data = json.dumps(body).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers()
            self.wfile.write(data)
        def do_GET(self):
            self._send({{"status": "ok"}})
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if gpu and os.environ.get("FAKE_GPU") == "crash-on-chat" and "Repeat this number" not in str(payload):
                os._exit(3)
            log.write(json.dumps({{"args": args, "payload": payload}}) + "\\n"); log.flush()
            if "Repeat this number" in payload["messages"][-1]["content"]:
                content = "an an cl" if gpu and os.environ.get("FAKE_GPU") == "garbage" else "4096"
            elif "response_format" in payload:
                content = json.dumps({{"approved": True, "score": 9, "issues": [], "feedback": ""}})
            else:
                content = "готово"
            self._send({{"choices": [{{"message": {{"content": content}}}}]}})

    HTTPServer(("127.0.0.1", port), H).serve_forever()
''')


@pytest.fixture
def home(tmp_path):
    (tmp_path / "runtime").mkdir()
    (tmp_path / "models").mkdir()
    server = tmp_path / "runtime" / "llama-server"
    server.write_text(FAKE_SERVER.format(python=sys.executable), encoding="utf-8")
    server.chmod(server.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "models" / "tiny-q4.gguf").write_bytes(b"GGUF")
    LlamaServer.gpu_failed = False
    LlamaServer.gpu_problem = ""
    _DEVICE_CACHE.clear()
    yield tmp_path
    LlamaServer.shutdown()
    LlamaServer.gpu_failed = False


@pytest.mark.skipif(os.name == "nt", reason="fake server is a POSIX script")
def test_bundled_model_runs_the_agent_loop(home):
    provider = LocalModelProvider(Settings(), home=home)
    assert provider.model == "tiny-q4.gguf"
    run = AgentPipeline(provider, 2).run("задача")
    assert run.approved and run.best.result == "готово"
    calls = requests_log(home)
    assert len(calls) == 3
    assert calls[0]["args"][calls[0]["args"].index("-c") + 1] == "8192"
    assert calls[2]["payload"]["response_format"]["type"] == "json_schema"
    first = LlamaServer._instance
    provider.complete("s", "u")
    assert LlamaServer._instance is first  # the server is reused, not restarted per request


def test_missing_runtime_or_model(tmp_path):
    with pytest.raises(ProviderError, match="движок"):
        LocalModelProvider(Settings(), home=tmp_path)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "llama-server").write_text("")
    with pytest.raises(ProviderError, match="gguf"):
        LocalModelProvider(Settings(), home=tmp_path)


def test_model_selection(home):
    (home / "models" / "another.gguf").write_bytes(b"GGUF")
    assert [p.name for p in list_local_models(home)] == ["another.gguf", "tiny-q4.gguf"]
    assert resolve_model(Settings(local_model="tiny-q4.gguf"), home).name == "tiny-q4.gguf"
    assert resolve_model(Settings(local_model="missing.gguf"), home) is None


@pytest.mark.skipif(os.name == "nt", reason="fake server is a POSIX script")
def test_server_crash_is_reported(home):
    (home / "runtime" / "llama-server").write_text("#!/bin/sh\necho 'error: model is corrupted' >&2\nexit 1\n")
    with pytest.raises(ProviderError, match="corrupted"):
        LocalModelProvider(Settings(), home=home).complete("s", "u")


posix_only = pytest.mark.skipif(os.name == "nt", reason="fake server is a POSIX script")


def requests_log(home):
    """Agent requests (the GPU self-test probe is left out)."""
    calls = [json.loads(line) for line in (home / "models" / "tiny-q4.gguf.requests").read_text().splitlines()]
    return [c for c in calls if "Repeat this number" not in str(c["payload"])]


@posix_only
def test_gpu_used_when_available(home, monkeypatch):
    monkeypatch.setenv("FAKE_GPU", "ok")
    provider = LocalModelProvider(Settings(), home=home)
    assert provider.complete("s", "u") == "готово"
    assert LlamaServer._instance.device() == "видеокарта Fake Radeon 9000 (37/37 слоёв)"
    assert "999" in requests_log(home)[0]["args"]


@posix_only
def test_broken_gpu_falls_back_to_cpu(home, monkeypatch):
    monkeypatch.setenv("FAKE_GPU", "broken")
    provider = LocalModelProvider(Settings(), home=home)
    assert provider.complete("s", "u") == "готово"
    args = requests_log(home)[0]["args"]
    assert "999" not in args and args[args.index("--device") + 1] == "none"
    assert LlamaServer._instance.device() == "процессор" and LlamaServer.gpu_failed


@posix_only
def test_gpu_crash_during_answer_retries_on_cpu(home, monkeypatch):
    monkeypatch.setenv("FAKE_GPU", "crash-on-chat")
    provider = LocalModelProvider(Settings(), home=home)
    assert provider.complete("s", "u") == "готово"
    assert not LlamaServer._instance.uses_gpu and LlamaServer.gpu_failed


@posix_only
def test_cpu_mode_and_old_build_without_device_none(home, monkeypatch):
    monkeypatch.setenv("FAKE_GPU", "ok")
    monkeypatch.setenv("FAKE_OLD_BUILD", "1")
    provider = LocalModelProvider(Settings(gpu_mode="cpu"), home=home)
    assert provider.complete("s", "u") == "готово"
    args = requests_log(home)[0]["args"]
    assert "999" not in args and "--device" not in args and args[args.index("-ngl") + 1] == "0"


@posix_only
def test_no_gpu_skips_the_gpu_attempt(home):
    provider = LocalModelProvider(Settings(), home=home)
    assert provider.complete("s", "u") == "готово"
    assert "999" not in requests_log(home)[0]["args"] and not LlamaServer.gpu_failed
    assert LlamaServer._instance.device() == "процессор"


def test_describe_device():
    assert describe_device("load_tensors: offloaded 0/37 layers to GPU", ["RTX"]) == "процессор"
    assert describe_device("", []) == "процессор"
    assert describe_device("", ["NVIDIA GeForce RTX 3060"]) == "видеокарта NVIDIA GeForce RTX 3060"
    log = "ggml_vulkan: 0 = Intel(R) Iris(R) Xe Graphics (Intel Corporation) | uma: 1\noffloaded 29/37 layers to GPU"
    assert describe_device(log, ["x"]) == "видеокарта Intel(R) Iris(R) Xe Graphics (29/37 слоёв)"


@posix_only
def test_gpu_with_wrong_results_is_dropped_by_the_self_test(home, monkeypatch):
    monkeypatch.setenv("FAKE_GPU", "garbage")
    provider = LocalModelProvider(Settings(), home=home)
    assert provider.complete("s", "u") == "готово"
    assert not LlamaServer._instance.uses_gpu and LlamaServer.gpu_failed
    assert "самопроверка" in LlamaServer.gpu_problem and "Fake Radeon 9000" in LlamaServer.gpu_problem
