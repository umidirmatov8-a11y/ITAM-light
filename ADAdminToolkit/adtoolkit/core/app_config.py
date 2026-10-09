"""Application settings.

Layering: built-in defaults <- organisation config file (``config/settings.json`` next to the EXE or the path in
``ADTOOLKIT_CONFIG``) <- per-user values stored in SQLite. Secrets are never part of the settings.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class OsRule:
    pattern: str            # case-insensitive substring of operatingSystem
    note: str


DEFAULT_OUTDATED_OS = [
    {"pattern": "Windows XP", "note": "Поддержка прекращена в 2014 г."},
    {"pattern": "Windows Vista", "note": "Поддержка прекращена в 2017 г."},
    {"pattern": "Windows 7", "note": "Поддержка прекращена в 2020 г. (без ESU)"},
    {"pattern": "Windows 8", "note": "Поддержка прекращена в 2016/2023 г."},
    {"pattern": "Windows Server 2003", "note": "Поддержка прекращена в 2015 г."},
    {"pattern": "Windows Server 2008", "note": "Поддержка прекращена в 2020 г. (без ESU)"},
    {"pattern": "Windows Server 2012", "note": "Поддержка прекращена в октябре 2023 г. (без ESU)"},
    {"pattern": "Windows 10", "note": "Поддержка основной линейки прекращена 14.10.2025 (кроме LTSC/ESU) — проверьте редакцию"},
]


@dataclass
class AppSettings:
    theme: str = "dark"                          # dark | light
    stale_user_days: int = 90
    stale_computer_days: int = 90
    password_expiring_days: int = 14
    recent_days: int = 14
    required_user_attributes: list[str] = field(default_factory=lambda: ["department", "title", "mail"])
    standard_groups: list[str] = field(default_factory=list)          # sAMAccountName of groups every user should be in
    extra_privileged_groups: list[str] = field(default_factory=lambda: ["DnsAdmins", "Cert Publishers"])
    outdated_os: list[dict] = field(default_factory=lambda: [dict(r) for r in DEFAULT_OUTDATED_OS])
    require_account_expiry_ous: list[str] = field(default_factory=list)  # OUs where accountExpires must be set
    bulk_max_items: int = 500
    bulk_rate_per_second: float = 5.0
    bulk_allow_privileged: bool = False
    search_debounce_ms: int = 450
    search_result_limit: int = 5000
    events_max: int = 500
    events_timeout_s: int = 60
    network_timeout_s: float = 3.0
    clipboard_clear_s: int = 30
    upn_suffix: str = ""
    offboarding_ou: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        names = {f.name for f in fields(cls)}
        obj = cls()
        for k, v in (data or {}).items():
            if k in names and v is not None:
                setattr(obj, k, v)
        obj.validate()
        return obj

    def validate(self) -> None:
        self.stale_user_days = max(1, int(self.stale_user_days))
        self.stale_computer_days = max(1, int(self.stale_computer_days))
        self.password_expiring_days = max(1, int(self.password_expiring_days))
        self.recent_days = max(1, int(self.recent_days))
        self.bulk_max_items = max(1, min(int(self.bulk_max_items), 10000))
        self.bulk_rate_per_second = max(0.2, min(float(self.bulk_rate_per_second), 50.0))
        self.search_debounce_ms = max(100, min(int(self.search_debounce_ms), 3000))
        self.search_result_limit = max(100, int(self.search_result_limit))
        if self.theme not in ("dark", "light"):
            self.theme = "dark"


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def org_config_path() -> Path | None:
    env = os.environ.get("ADTOOLKIT_CONFIG")
    if env:
        return Path(env)
    candidate = app_base_dir() / "config" / "settings.json"
    return candidate if candidate.exists() else None


def load_org_config() -> dict:
    path = org_config_path()
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Не удалось прочитать файл конфигурации %s: %s", path, exc)
        return {}
    for key in list(data.get("profiles", []) or []):
        if isinstance(key, dict):
            for secret in [k for k in key if "password" in k.lower()]:
                log.warning("В файле конфигурации найден пароль (%s) — значение проигнорировано", secret)
                key.pop(secret)
    return data


class SettingsManager:
    KEY = "app_settings"

    def __init__(self, db):
        self.db = db
        self.org = load_org_config()
        merged = dict(self.org.get("settings") or {})
        merged.update(db.get_setting(self.KEY, {}) or {})
        self.settings = AppSettings.from_dict(merged)

    def save(self, settings: AppSettings | None = None) -> None:
        if settings is not None:
            settings.validate()
            self.settings = settings
        self.db.set_setting(self.KEY, self.settings.to_dict())

    def org_profiles(self) -> list[dict]:
        return [p for p in (self.org.get("profiles") or []) if isinstance(p, dict)]
