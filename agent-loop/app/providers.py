"""LLM back-ends. Every agent talks to a provider through `complete(system, user, schema)`."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol

from app.config import PROVIDER_ANTHROPIC, PROVIDER_OLLAMA, Settings


class ProviderError(RuntimeError):
    """A provider could not produce an answer (network, auth, refusal...)."""


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str, schema: dict | None = None) -> str:
        """Return the model's text answer. With `schema`, the answer is a JSON document matching it."""
        ...


class AnthropicProvider:
    name = "Claude API"

    def __init__(self, settings: Settings):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - packaged with the exe
            raise ProviderError("Пакет 'anthropic' не установлен: pip install anthropic") from exc
        self._anthropic = anthropic
        kwargs = {"api_key": settings.anthropic_api_key} if settings.anthropic_api_key else {}
        try:
            self._client = anthropic.Anthropic(**kwargs)
        except anthropic.AnthropicError as exc:
            raise ProviderError("Не задан API-ключ Claude (Настройки или переменная ANTHROPIC_API_KEY)") from exc
        self.model = settings.anthropic_model
        self.effort = settings.effort

    def complete(self, system: str, user: str, schema: dict | None = None) -> str:
        anthropic = self._anthropic
        output_config: dict = {"effort": self.effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config=output_config,
                # On a safety decline the API re-runs the request on a recommended fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise ProviderError("Неверный API-ключ Claude") from exc
        except anthropic.NotFoundError as exc:
            raise ProviderError(f"Модель '{self.model}' не найдена") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("Превышен лимит запросов Claude API, попробуйте позже") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Ошибка Claude API ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Нет соединения с Claude API") from exc

        if response.stop_reason == "refusal":
            raise ProviderError("Модель отказалась выполнять запрос (ограничения безопасности)")
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            raise ProviderError("Пустой ответ модели")
        return text


class OllamaProvider:
    name = "Ollama (локально)"

    def __init__(self, settings: Settings, timeout: float = 600.0):
        self.url = settings.ollama_url.rstrip("/")
        self.model = settings.ollama_model
        self.timeout = timeout

    def complete(self, system: str, user: str, schema: dict | None = None) -> str:
        payload: dict = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if schema is not None:
            payload["format"] = schema
        request = urllib.request.Request(
            f"{self.url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ProviderError(f"Ollama вернул ошибку {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderError(f"Ollama недоступен по адресу {self.url} — он запущен?") from exc
        except ValueError as exc:
            raise ProviderError("Ollama вернул некорректный ответ") from exc
        text = str((data.get("message") or {}).get("content") or "").strip()
        if not text:
            raise ProviderError("Пустой ответ модели")
        return text


def create_provider(settings: Settings) -> Provider:
    if settings.provider == PROVIDER_ANTHROPIC:
        return AnthropicProvider(settings)
    if settings.provider == PROVIDER_OLLAMA:
        return OllamaProvider(settings)
    raise ProviderError(f"Неизвестный провайдер: {settings.provider}")
