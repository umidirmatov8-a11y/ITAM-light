"""Ollama (local LLM). Data stays on the analyst's machine / local network."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from app.ai.providers.base import AIProvider
from app.core.errors import ProviderResponseError


class _OllamaMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str = ""


class _OllamaChat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: _OllamaMessage


class OllamaProvider(AIProvider):
    name = "Ollama"
    is_external = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        host = self.ai.ollama_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
        # A remote Ollama server outside localhost is still "your" infrastructure, but data leaves the PC.
        self.is_external = host not in ("localhost", "127.0.0.1", "::1") and not _is_private(host)

    @property
    def model(self) -> str:
        return self.ai.ollama_model

    @property
    def base(self) -> str:
        return self.ai.ollama_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": "json",
            "options": {"temperature": self.ai.temperature, "num_predict": self.ai.max_tokens},
        }
        data = self._post_json(f"{self.base}/api/chat", payload, local=True)
        try:
            parsed = _OllamaChat.model_validate(data)
        except ValidationError as exc:
            raise ProviderResponseError("Ollama: unexpected response structure") from exc
        if not parsed.message.content:
            raise ProviderResponseError("Ollama: empty answer")
        return parsed.message.content

    def list_models(self) -> list[str]:
        data = self._get_json(f"{self.base}/api/tags", local=True)
        models = data.get("models", []) if isinstance(data, dict) else []
        return sorted(str(m.get("name")) for m in models if isinstance(m, dict) and m.get("name"))

    def test_connection(self) -> str:
        models = self.list_models()
        if self.model not in models and f"{self.model}:latest" not in models:
            return (f"Ollama reachable, but model '{self.model}' is not installed. "
                    f"Run: ollama pull {self.model}. Installed: {', '.join(models[:8]) or 'none'}")
        return f"connected ({self.model})"


def _is_private(host: str) -> bool:
    import ipaddress
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return host.endswith(".local") or "." not in host
