"""User settings stored in %APPDATA%\\AgentLoop\\config.json (~/.config/AgentLoop on other systems)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

PROVIDER_LOCAL = "local"  # llama.cpp + GGUF weights bundled with the installer
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OLLAMA = "ollama"


# Small open-weight models available through Ollama: (name, approximate download size, note).
OLLAMA_PRESETS = [
    ("qwen2.5:0.5b", "0.4 ГБ", "самая быстрая, для проверки что всё работает; качество низкое"),
    ("qwen2.5:1.5b", "1 ГБ", "быстрая, простые задачи"),
    ("qwen2.5:3b", "1.9 ГБ", "рекомендуется для теста: хороший русский, работает на CPU"),
    ("llama3.2:3b", "2 ГБ", "Meta Llama 3.2, лучше в английском"),
    ("gemma3:4b", "3.3 ГБ", "Google Gemma 3"),
    ("qwen2.5:7b", "4.7 ГБ", "заметно умнее, желательна видеокарта или 16 ГБ ОЗУ"),
]
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"


@dataclass
class Settings:
    provider: str = PROVIDER_LOCAL
    # Built-in model: a .gguf file name from the models folder (empty = the bundled one) or a full path.
    local_model: str = ""
    num_ctx: int = 8192  # context window; 2-4K is too small for prompt + result + review
    gpu_mode: str = "auto"  # auto: Vulkan GPU if available (falls back to CPU); cpu: never use the GPU
    # Claude API. Empty key -> the SDK reads ANTHROPIC_API_KEY from the environment.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    effort: str = "high"  # low | medium | high | xhigh | max
    # Local models via Ollama (https://ollama.com), no internet / key required.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    # Pipeline
    max_iterations: int = 3
    language: str = "русский"

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "AgentLoop"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or config_path()
    try:
        return Settings.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
