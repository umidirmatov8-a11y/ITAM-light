"""LLM back-ends. Every agent talks to a provider through `complete(system, user, schema)`."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Callable, Protocol

from app.config import PROVIDER_ANTHROPIC, PROVIDER_LOCAL, PROVIDER_OLLAMA, Settings


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

    def __init__(self, settings: Settings, timeout: float = 900.0):
        self.url = settings.ollama_url.rstrip("/")
        self.model = settings.ollama_model
        self.num_ctx = settings.num_ctx
        self.timeout = timeout

    def _open(self, path: str, payload: dict | None = None, timeout: float | None = None):
        request = urllib.request.Request(
            f"{self.url}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            return urllib.request.urlopen(request, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ProviderError(f"Ollama вернул ошибку {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError(
                f"Ollama не отвечает по адресу {self.url}. Установите его с https://ollama.com и запустите."
            ) from exc

    def list_models(self) -> list[str]:
        """Names of the models already downloaded to this computer."""
        try:
            with self._open("/api/tags", timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except ValueError as exc:
            raise ProviderError("Ollama вернул некорректный ответ") from exc
        return sorted(str(m.get("name")) for m in data.get("models", []) if isinstance(m, dict) and m.get("name"))

    def has_model(self) -> bool:
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        return wanted in self.list_models()

    def pull(self, on_progress: Callable[[str, float | None], None] | None = None,
             cancel: threading.Event | None = None) -> None:
        """Download the model (resumable). on_progress(status, fraction 0..1 or None)."""
        report = on_progress or (lambda _s, _f: None)
        with self._open("/api/pull", {"model": self.model, "stream": True}) as resp:
            for line in resp:
                if cancel is not None and cancel.is_set():
                    raise ProviderError("Загрузка модели остановлена")
                try:
                    item = json.loads(line.decode("utf-8"))
                except ValueError:
                    continue
                if item.get("error"):
                    raise ProviderError(f"Не удалось скачать модель {self.model}: {item['error']}")
                total, done = item.get("total"), item.get("completed")
                report(str(item.get("status", "")), done / total if total and done is not None else None)
                if item.get("status") == "success":
                    return
        raise ProviderError(f"Загрузка модели {self.model} прервалась")

    def complete(self, system: str, user: str, schema: dict | None = None) -> str:
        payload: dict = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"num_ctx": self.num_ctx},
        }
        if schema is not None:
            payload["format"] = schema
            payload["options"]["temperature"] = 0
        try:
            with self._open("/api/chat", payload) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except ValueError as exc:
            raise ProviderError("Ollama вернул некорректный ответ") from exc
        except ProviderError as exc:
            if "404" in str(exc):
                raise ProviderError(f"Модель {self.model} не скачана — нажмите «Скачать модель» в настройках") from exc
            raise
        text = str((data.get("message") or {}).get("content") or "").strip()
        if not text:
            raise ProviderError("Пустой ответ модели")
        return text


def create_provider(settings: Settings) -> Provider:
    if settings.provider == PROVIDER_LOCAL:
        from app.local_runtime import LocalModelProvider
        return LocalModelProvider(settings)
    if settings.provider == PROVIDER_ANTHROPIC:
        return AnthropicProvider(settings)
    if settings.provider == PROVIDER_OLLAMA:
        return OllamaProvider(settings)
    raise ProviderError(f"Неизвестный провайдер: {settings.provider}")
