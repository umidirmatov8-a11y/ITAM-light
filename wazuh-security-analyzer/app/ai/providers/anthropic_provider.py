"""Anthropic Messages API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from app.ai.providers.base import AIProvider
from app.core.errors import ProviderResponseError, ProviderUnavailableError

API_URL = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"


class _Block(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    text: str = ""


class _MessageResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: list[_Block]


class AnthropicProvider(AIProvider):
    name = "Anthropic"
    is_external = True

    @property
    def model(self) -> str:
        return self.ai.anthropic_model

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderUnavailableError("Anthropic: API key is not configured")
        return {"x-api-key": self.api_key, "anthropic-version": API_VERSION}

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": self.ai.max_tokens,
            "temperature": self.ai.temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = self._post_json(f"{API_URL}/messages", payload, self._headers())
        try:
            parsed = _MessageResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderResponseError("Anthropic: unexpected response structure") from exc
        text = "".join(block.text for block in parsed.content if block.type == "text")
        if not text:
            raise ProviderResponseError("Anthropic: empty answer")
        return text

    def list_models(self) -> list[str]:
        data = self._get_json(f"{API_URL}/models", self._headers())
        items = data.get("data", []) if isinstance(data, dict) else []
        return sorted(str(m.get("id")) for m in items if isinstance(m, dict) and m.get("id"))

    def test_connection(self) -> str:
        self.list_models()
        return f"connected ({self.model})"
