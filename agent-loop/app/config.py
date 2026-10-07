"""User settings stored in %APPDATA%\\AgentLoop\\config.json (~/.config/AgentLoop on other systems)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OLLAMA = "ollama"


@dataclass
class Settings:
    provider: str = PROVIDER_ANTHROPIC
    # Claude API. Empty key -> the SDK reads ANTHROPIC_API_KEY from the environment.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    effort: str = "high"  # low | medium | high | xhigh | max
    # Local models via Ollama (https://ollama.com), no internet / key required.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b"
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
