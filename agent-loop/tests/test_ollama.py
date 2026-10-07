import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.config import Settings
from app.pipeline import AgentPipeline
from app.providers import OllamaProvider, ProviderError


class FakeOllama(BaseHTTPRequestHandler):
    models = ["qwen2.5:0.5b"]
    requests = []

    def log_message(self, *_args):
        pass

    def _send(self, code, body):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, {"models": [{"name": m} for m in self.models]})

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.requests.append((self.path, payload))
        if self.path == "/api/pull":
            FakeOllama.models.append(payload["model"])
            lines = [{"status": "pulling manifest"}, {"status": "downloading", "total": 100, "completed": 50},
                     {"status": "success"}]
            self._send(200, b"".join(json.dumps(x).encode() + b"\n" for x in lines))
            return
        if payload["model"] not in self.models:
            self._send(404, {"error": f"model '{payload['model']}' not found"})
            return
        system = payload["messages"][0]["content"]
        if "Проверяющий" in system:
            content = json.dumps({"approved": True, "score": 8, "issues": [], "feedback": ""})
        else:
            content = "ответ"
        self._send(200, {"message": {"role": "assistant", "content": content}})


@pytest.fixture
def server():
    FakeOllama.models = ["qwen2.5:0.5b"]
    FakeOllama.requests = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def provider(url, model="qwen2.5:0.5b"):
    return OllamaProvider(Settings(ollama_url=url, ollama_model=model))


def test_full_loop_against_ollama_api(server):
    run = AgentPipeline(provider(server), 2).run("задача")
    assert run.approved
    chat = [p for path, p in FakeOllama.requests if path == "/api/chat"]
    assert len(chat) == 3
    assert all(p["options"]["num_ctx"] == 8192 for p in chat)
    assert "format" in chat[2] and "format" not in chat[0]


def test_has_model_and_pull(server):
    p = provider(server, "qwen2.5:3b")
    assert not p.has_model()
    seen = []
    p.pull(lambda status, fraction: seen.append((status, fraction)))
    assert ("downloading", 0.5) in seen and p.has_model()


def test_missing_model_message(server):
    with pytest.raises(ProviderError, match="не скачана"):
        provider(server, "nope:1b").complete("s", "u")


def test_ollama_not_running():
    with pytest.raises(ProviderError, match="не отвечает"):
        OllamaProvider(Settings(ollama_url="http://127.0.0.1:9"), timeout=2).list_models()
