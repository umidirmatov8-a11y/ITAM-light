"""Ollama availability check (stage 1). Planning with a local LLM is added in stage 4."""
from __future__ import annotations

import ipaddress
import time
from typing import Any
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
