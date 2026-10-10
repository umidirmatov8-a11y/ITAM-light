"""Typed user settings persisted in SQLite (one JSON document per section)."""
from __future__ import annotations

import json
import threading
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field, field_validator, model_validator

from .db import Database


class NetworkMode(str, Enum):
    LOCAL = "LOCAL"
    ONLINE = "ONLINE"


class GeneralSettings(BaseModel):
    language: str = "ru"
    wake_word: str = "арк"
    autostart: bool = False
    start_minimized: bool = False
    # Text typed into the UI is explicit, so the wake word is only required for voice.
    require_wake_word_for_voice: bool = True
    min_confidence: float = Field(0.6, ge=0.0, le=1.0)


class NetworkSettings(BaseModel):
    mode: NetworkMode = NetworkMode.LOCAL
    online_allowed: bool = True  # master switch: False blocks ONLINE mode entirely
    search_url: str = "https://duckduckgo.com/?q={query}"

    @field_validator("search_url")
    @classmethod
    def _search_url(cls, value: str) -> str:
        if not value.startswith("https://") or "{query}" not in value:
            raise ValueError("search_url must be https:// and contain {query}")
        return value


class DevicesSettings(BaseModel):
    microphone_enabled: bool = True
    camera_enabled: bool = False
    local_ai_enabled: bool = True


class AISettings(BaseModel):
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5-coder:7b"
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    timeout_s: float = Field(60.0, gt=0, le=600)

    @field_validator("ollama_url")
    @classmethod
    def _url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("ollama_url must start with http:// or https://")
        return value.rstrip("/")


MODULES = ("apps", "volume", "windows", "system_info", "files", "processes",
           "power", "browser", "web_search", "scenarios", "modes")


class SafetySettings(BaseModel):
    # Category B/C actions are simulated (logged, not executed) while this is on.
    dry_run: bool = True
    allowed_dirs: list[str] = Field(default_factory=list)
    confirmation_ttl_s: int = Field(60, ge=10, le=600)
    modules: dict[str, bool] = Field(default_factory=lambda: {m: True for m in MODULES})
    action_timeout_s: float = Field(15.0, gt=0, le=300)

    @field_validator("modules")
    @classmethod
    def _modules(cls, value: dict[str, bool]) -> dict[str, bool]:
        merged = {m: True for m in MODULES}
        merged.update({k: bool(v) for k, v in value.items() if k in MODULES})
        return merged


class UISettings(BaseModel):
    theme: str = "amber"
    scale: float = Field(1.0, ge=0.75, le=1.5)
    animations: bool = True
    scanlines: bool = True

    @field_validator("theme")
    @classmethod
    def _theme(cls, value: str) -> str:
        if value not in ("amber", "phosphor", "ice"):
            raise ValueError("unknown theme")
        return value


class ProfileSettings(BaseModel):
    silent: bool = False


class Settings(BaseModel):
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    devices: DevicesSettings = Field(default_factory=DevicesSettings)
    ai: AISettings = Field(default_factory=AISettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    ui: UISettings = Field(default_factory=UISettings)
    profile: ProfileSettings = Field(default_factory=ProfileSettings)

    @model_validator(mode="after")
    def _online_switch(self) -> "Settings":
        # Turning the online master switch off always brings A.R.C. back to LOCAL.
        if not self.network.online_allowed and self.network.mode == NetworkMode.ONLINE:
            self.network.mode = NetworkMode.LOCAL
        return self


SECTIONS = tuple(Settings.model_fields)


class SettingsStore:
    """Loads settings once, validates every update, persists per section."""

    def __init__(self, db: Database, default_allowed_dirs: Callable[[], list[str]] | None = None):
        self._db = db
        self._lock = threading.RLock()
        self._settings = self._load(default_allowed_dirs)

    def _load(self, default_allowed_dirs: Callable[[], list[str]] | None) -> Settings:
        rows = self._db.query("SELECT key, value FROM settings")
        stored: dict[str, Any] = {}
        for row in rows:
            if row["key"] in SECTIONS:
                try:
                    stored[row["key"]] = json.loads(row["value"])
                except json.JSONDecodeError:
                    continue
        first_run = not stored
        settings = Settings()
        for section, value in stored.items():
            try:
                model = type(getattr(settings, section))
                setattr(settings, section, model.model_validate(value))
            except ValueError:
                pass  # damaged section falls back to defaults
        if first_run and default_allowed_dirs:
            settings.safety.allowed_dirs = default_allowed_dirs()
        if first_run:
            for section in SECTIONS:
                self._save_section(settings, section)
        return settings

    def _save_section(self, settings: Settings, section: str) -> None:
        value = getattr(settings, section).model_dump(mode="json")
        self._db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (section, json.dumps(value, ensure_ascii=False)),
        )

    def get(self) -> Settings:
        with self._lock:
            return self._settings.model_copy(deep=True)

    def update(self, patch: dict[str, Any]) -> Settings:
        """Apply a partial update {section: {field: value}}; raises ValueError on invalid data."""
        with self._lock:
            current = self._settings.model_dump(mode="json")
            for section, values in patch.items():
                if section not in SECTIONS:
                    raise ValueError(f"unknown settings section: {section}")
                if not isinstance(values, dict):
                    raise ValueError(f"section {section} must be an object")
                unknown = set(values) - set(current[section])
                if unknown:
                    raise ValueError(f"unknown fields in {section}: {', '.join(sorted(unknown))}")
                current[section].update(values)
            new = Settings.model_validate(current)
            for section in patch:
                self._save_section(new, section)
            self._settings = new
            return new.model_copy(deep=True)
