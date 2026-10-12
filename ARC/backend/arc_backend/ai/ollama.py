"""Ollama: availability check and the single place that talks to /api/chat."""
from __future__ import annotations

import ipaddress
import time
from typing import Any, Optional
from urllib.parse import urlparse

import httpx


def is_loopback_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_ollama(url: str, model: str, *, timeout: float = 1.5, allow_remote: bool = False) -> dict[str, Any]:
    """Returns {"state": "ready"|"model_missing"|"offline"|"disabled"|"blocked", ...}. Never raises."""
    started = time.monotonic()
    result: dict[str, Any] = {"url": url, "model": model, "models": [], "remote": not is_loopback_url(url)}
    if result["remote"] and not allow_remote:
        result.update(state="blocked", message="Адрес Ollama вне этого компьютера: нужен режим ONLINE")
        return result
    try:
        response = httpx.get(f"{url}/api/tags", timeout=timeout, trust_env=False)
        response.raise_for_status()
        models = [m.get("name", "") for m in response.json().get("models", []) if isinstance(m, dict)]
    except (httpx.HTTPError, ValueError) as exc:
        result.update(state="offline", message=f"Ollama недоступна ({type(exc).__name__}). "
                                               "Запустите Ollama или отключите локальный ИИ.")
        return result
    result["models"] = models
    wanted = model if ":" in model else model + ":latest"
    present = model in models or wanted in models
    result["latency_ms"] = round((time.monotonic() - started) * 1000)
    if present:
        result.update(state="ready", message=f"Модель {model} готова")
    else:
        result.update(state="model_missing",
                      message=f"Ollama работает, но модель {model} не загружена. Выполните: ollama pull {model}")
    return result


class OllamaError(RuntimeError):
    """User-facing reason why the local model could not answer."""


def chat(url: str, model: str, messages: list[dict[str, str]], *, timeout_s: float, temperature: float = 0.2,
         num_ctx: int = 4096, schema: Optional[dict[str, Any]] = None,
         transport: Optional[httpx.BaseTransport] = None) -> str:
    """One non-streaming chat call. Returns the message content (JSON text when `schema` is given)."""
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": False, "keep_alive": "15m",
                            "options": {"temperature": temperature, "num_ctx": num_ctx}}
    if schema is not None:
        body["format"] = schema
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_s, connect=3.0), trust_env=False,
                          transport=transport) as client:
            response = client.post(f"{url}/api/chat", json=body)
    except httpx.TimeoutException:
        raise OllamaError(f"Локальная модель не ответила за {timeout_s:g} с")
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama недоступна ({type(exc).__name__})")
    if response.status_code == 404:
        raise OllamaError(f"Модель {model} не загружена в Ollama (ollama pull {model})")
    if response.status_code != 200:
        raise OllamaError(f"Ollama вернула ошибку {response.status_code}")
    try:
        content = response.json()["message"]["content"]
    except (ValueError, KeyError, TypeError):
        raise OllamaError("Ollama вернула ответ неверного формата")
    if not isinstance(content, str):
        raise OllamaError("Ollama вернула ответ неверного формата")
    return content
