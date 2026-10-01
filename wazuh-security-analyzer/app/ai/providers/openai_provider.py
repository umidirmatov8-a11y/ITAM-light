"""OpenAI Chat Completions API and OpenAI-compatible endpoints (LM Studio, vLLM, LocalAI...)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.ai.providers.base import AIProvider
from app.core.errors import ProviderResponseError, ProviderUnavailableError


class _Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str | None = None


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: _Message


class _ChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    choices: list[_Choice]


class OpenAIProvider(AIProvider):
    name = "OpenAI"
    is_external = True
    base_url = "https://api.openai.com/v1"
    json_mode = True

    @property
    def model(self) -> str:
        return self.ai.openai_model

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderUnavailableError(f"{self.name}: API key is not configured")
        return {"Authorization": f"Bearer {self.api_key}"}

    def _local(self) -> bool:
        return False

    def complete(self, system: str, user: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.ai.temperature,
            "max_tokens": self.ai.max_tokens,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = self._post_json(f"{self.base_url.rstrip('/')}/chat/completions", payload, self._headers(),
                               local=self._local())
        try:
            parsed = _ChatResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderResponseError(f"{self.name}: unexpected response structure") from exc
        if not parsed.choices or not parsed.choices[0].message.content:
            raise ProviderResponseError(f"{self.name}: empty answer")
        return parsed.choices[0].message.content

    def list_models(self) -> list[str]:
        data = self._get_json(f"{self.base_url.rstrip('/')}/models", self._headers(), local=self._local())
        items = data.get("data", []) if isinstance(data, dict) else []
        return sorted(str(m.get("id")) for m in items if isinstance(m, dict) and m.get("id"))

    def test_connection(self) -> str:
        models = self.list_models()
        if models and self.model not in models:
            return f"connected, but model '{self.model}' was not listed ({len(models)} models available)"
        return f"connected ({self.model})"


class GenericOpenAICompatibleProvider(OpenAIProvider):
    name = "OpenAI-compatible"
    json_mode = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = self.ai.compatible_base_url
        host = self.base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
        self._is_local = host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local")
        self.is_external = not self._is_local

    @property
    def model(self) -> str:
        return self.ai.compatible_model

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _local(self) -> bool:
        return self._is_local
