"""Provider selection from configuration."""

from __future__ import annotations

from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import AIProvider
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.providers.openai_provider import GenericOpenAICompatibleProvider, OpenAIProvider
from app.core.config import AppConfig
from app.core.secrets import SecretStore

PROVIDER_LABELS = {
    "none": "None (AI disabled)",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "ollama": "Ollama (local LLM)",
    "openai_compatible": "Local LLM / OpenAI-compatible endpoint",
}

_SECRET = {"openai": "openai_api_key", "anthropic": "anthropic_api_key", "openai_compatible": "compatible_api_key"}


def create_provider(config: AppConfig, secrets: SecretStore, transport=None) -> AIProvider | None:
    name = config.ai.provider
    if name == "none":
        return None
    key = secrets.get(_SECRET[name]) if name in _SECRET else None
    cls = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "ollama": OllamaProvider,
           "openai_compatible": GenericOpenAICompatibleProvider}[name]
    return cls(config.ai, config.network, key, transport)
