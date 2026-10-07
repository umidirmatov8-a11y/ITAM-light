import json
import os
import stat
import sys
import textwrap

import pytest

from app.config import Settings
from app.local_runtime import LlamaServer, LocalModelProvider, list_local_models, resolve_model
from app.pipeline import AgentPipeline
from app.providers import ProviderError

FAKE_SERVER = textwrap.dedent('''\
    #!{python}
    import json, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1])
    log = open(args[args.index("-m") + 1] + ".requests", "a", encoding="utf-8")

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
            log.write(json.dumps({{"args": args, "payload": payload}}) + "\\n"); log.flush()
            if "response_format" in payload:
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
    yield tmp_path
    LlamaServer.shutdown()


@pytest.mark.skipif(os.name == "nt", reason="fake server is a POSIX script")
def test_bundled_model_runs_the_agent_loop(home):
    provider = LocalModelProvider(Settings(), home=home)
    assert provider.model == "tiny-q4.gguf"
    run = AgentPipeline(provider, 2).run("задача")
    assert run.approved and run.best.result == "готово"
    calls = [json.loads(line) for line in (home / "models" / "tiny-q4.gguf.requests").read_text().splitlines()]
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
