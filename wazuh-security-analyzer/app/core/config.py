"""Typed application configuration.

The effective configuration is the bundled ``config/default_config.yaml`` deep-merged
with the user's ``config.yaml``.  Secrets (API keys) are never part of this model:
they live in :mod:`app.core.secrets` (Windows Credential Manager via ``keyring``).
"""

from __future__ import annotations

import copy
import re
import ipaddress
import logging
import threading
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core import paths

log = logging.getLogger(__name__)

Criticality = Literal["low", "medium", "high", "critical"]

# Keys that must never be persisted to YAML even if a user adds them by hand.
_FORBIDDEN_KEY = re.compile(r"(?:^|_)(?:api_?key|password|passwd|secret|token|credentials?)$", re.I)


class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class RiskThresholds(_Section):
    critical: int = 80
    high: int = 60
    medium: int = 40
    low: int = 20

    @model_validator(mode="after")
    def _ascending(self) -> "RiskThresholds":
        if not (0 <= self.low < self.medium < self.high < self.critical <= 100):
            raise ValueError("risk thresholds must satisfy 0 <= low < medium < high < critical <= 100")
        return self


class RiskWeights(_Section):
    """Points contributed by each factor of the risk score (final score is clamped to 0-100)."""

    wazuh_level_max: float = 40.0
    asset_criticality: dict[str, float] = Field(
        default_factory=lambda: {"low": 0.0, "medium": 5.0, "high": 10.0, "critical": 15.0}
    )
    frequency_max: float = 10.0
    frequency_saturation: int = 1000
    external_source: float = 8.0
    bruteforce_pattern: float = 10.0
    successful_auth_after_failures: float = 20.0
    successful_auth_external: float = 5.0
    ioc_malicious: float = 20.0
    ioc_suspicious: float = 8.0
    cve_max: float = 15.0
    cve_known_exploited: float = 10.0
    mitre_max: float = 10.0
    correlation_chain: float = 15.0
    correlation_chain_per_extra_stage: float = 5.0
    correlation_campaign: float = 6.0
    category_bonus: dict[str, float] = Field(
        default_factory=lambda: {
            "malware": 12.0,
            "impact": 15.0,
            "credential_access": 12.0,
            "defense_evasion": 8.0,
            "network_c2": 8.0,
            "lateral_movement": 8.0,
            "persistence": 6.0,
            "privilege_escalation": 4.0,
            "execution": 6.0,
            "account_change": 4.0,
            "web_attack": 4.0,
            "brute_force": 6.0,
            "auth_failure": 2.0,
            "system": -10.0,
            "policy": -5.0,
            "process_activity": -5.0,
        }
    )
    mitre_tactic_weight: dict[str, float] = Field(
        default_factory=lambda: {
            "impact": 1.0,
            "exfiltration": 1.0,
            "credential-access": 0.9,
            "command-and-control": 0.9,
            "lateral-movement": 0.9,
            "initial-access": 0.8,
            "privilege-escalation": 0.8,
            "execution": 0.7,
            "persistence": 0.7,
            "defense-evasion": 0.7,
            "collection": 0.6,
            "discovery": 0.4,
            "reconnaissance": 0.3,
            "resource-development": 0.2,
        }
    )
    mitre_confidence_factor: dict[str, float] = Field(
        default_factory=lambda: {"high": 1.0, "medium": 0.7, "low": 0.4}
    )
    false_positive_dampening: float = Field(default=0.3, ge=0.0, le=1.0)


class AssetRule(_Section):
    pattern: str
    criticality: Criticality = "medium"
    description: str = ""


class WazuhConfig(_Section):
    internal_networks: list[str] = Field(default_factory=list)
    known_scanners: list[str] = Field(default_factory=list)
    asset_criticality: list[AssetRule] = Field(default_factory=list)
    default_asset_criticality: Criticality = "medium"

    @field_validator("internal_networks", "known_scanners")
    @classmethod
    def _valid_networks(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            value = str(value).strip()
            if not value:
                continue
            try:
                ipaddress.ip_network(value, strict=False)
            except ValueError as exc:
                raise ValueError(f"invalid network/IP {value!r}") from exc
            cleaned.append(value)
        return cleaned


class CorrelationConfig(_Section):
    chain_window_minutes: int = Field(default=60, ge=1, le=7 * 24 * 60)
    min_chain_stages: int = Field(default=3, ge=2, le=8)
    bruteforce_threshold: int = Field(default=5, ge=2)
    success_after_failure_window_minutes: int = Field(default=60, ge=1)
    campaign_min_events: int = Field(default=10, ge=2)
    max_groups: int = Field(default=200_000, ge=1000)
    max_incidents: int = Field(default=2000, ge=10)
    significant_risk: int = Field(default=40, ge=0, le=100)


class AIConfig(_Section):
    provider: Literal["none", "openai", "anthropic", "ollama", "openai_compatible"] = "none"
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-sonnet-5-5"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    compatible_base_url: str = "http://localhost:1234/v1"
    compatible_model: str = "local-model"
    timeout_seconds: int = Field(default=120, ge=5, le=900)
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2000, ge=256, le=16000)
    # Data sent to cloud providers (OpenAI, Anthropic) is ALWAYS sanitized.
    anonymize_local: bool = False
    max_related_events: int = Field(default=20, ge=1, le=200)
    auto_analyze_top_n: int = Field(default=0, ge=0, le=50)

    @property
    def is_enabled(self) -> bool:
        return self.provider != "none"

    @property
    def is_external(self) -> bool:
        return self.provider in ("openai", "anthropic")


class ThreatIntelConfig(_Section):
    virustotal_enabled: bool = False
    abuseipdb_enabled: bool = False
    otx_enabled: bool = False
    nvd_enabled: bool = True
    cisa_kev_enabled: bool = True
    max_ioc_lookups: int = Field(default=50, ge=0, le=5000)
    max_cve_lookups: int = Field(default=25, ge=0, le=2000)
    cache_ttl_hours: int = Field(default=24, ge=0)
    concurrency: int = Field(default=4, ge=1, le=32)
    active_domain_checks: bool = False


class NetworkConfig(_Section):
    mode: Literal["offline", "online"] = "offline"
    proxy: str = ""
    timeout_seconds: float = Field(default=15.0, ge=1.0, le=300.0)
    verify_tls: bool = True
    ca_bundle: str = ""
    max_response_mb: int = Field(default=25, ge=1, le=200)

    @property
    def online(self) -> bool:
        return self.mode == "online"


class PrivacyConfig(_Section):
    mask_usernames: bool = True
    mask_emails: bool = True
    mask_internal_ips: bool = True
    mask_external_ips: bool = False
    mask_hostnames: bool = True
    mask_domains: bool = True
    mask_personal_data: bool = True
    internal_domains: list[str] = Field(default_factory=list)


class LimitsConfig(_Section):
    max_file_size_mb: int = Field(default=4096, ge=1)
    max_archive_total_mb: int = Field(default=8192, ge=1)
    max_archive_entries: int = Field(default=10_000, ge=1)
    max_compression_ratio: int = Field(default=200, ge=2)
    max_files: int = Field(default=10_000, ge=1)
    max_line_mb: int = Field(default=16, ge=1)
    batch_size: int = Field(default=5000, ge=100, le=100_000)


class StorageConfig(_Section):
    state_database_url: str = ""
    store_raw_events: bool = True
    max_raw_event_kb: int = Field(default=16, ge=1, le=1024)
    deduplicate: bool = True
    keep_workspaces: int = Field(default=5, ge=1, le=100)


class LoggingConfig(_Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    max_file_mb: int = Field(default=10, ge=1)
    backup_count: int = Field(default=5, ge=0)


class UIConfig(_Section):
    first_run: bool = True
    language: Literal["auto", "en", "ru"] = "auto"
    page_size: int = Field(default=500, ge=50, le=5000)


class AppConfig(_Section):
    risk_thresholds: RiskThresholds = Field(default_factory=RiskThresholds)
    risk_weights: RiskWeights = Field(default_factory=RiskWeights)
    wazuh: WazuhConfig = Field(default_factory=WazuhConfig)
    correlation: CorrelationConfig = Field(default_factory=CorrelationConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    threat_intel: ThreatIntelConfig = Field(default_factory=ThreatIntelConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    @property
    def language(self) -> str:
        """Effective UI/report language ('auto' resolves to the operating-system language)."""
        if self.ui.language == "auto":
            from app.i18n import detect_system_language
            return detect_system_language()
        return self.ui.language


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def strip_secret_like_keys(data: Any, path: str = "") -> Any:
    """Remove keys that look like credentials so they are never loaded from / written to YAML."""
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            if _FORBIDDEN_KEY.search(str(key)):
                log.warning("Ignoring secret-like configuration key %s%s; store secrets in Settings > API keys",
                            path, key)
                continue
            cleaned[key] = strip_secret_like_keys(value, f"{path}{key}.")
        return cleaned
    if isinstance(data, list):
        return [strip_secret_like_keys(v, path) for v in data]
    return data


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        log.error("Failed to read configuration %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        log.error("Configuration %s is not a mapping; ignoring it", path)
        return {}
    return strip_secret_like_keys(data)


class ConfigManager:
    """Loads, validates and persists :class:`AppConfig`. Thread-safe."""

    def __init__(self, user_path: Path | None = None, default_path: Path | None = None):
        self.user_path = user_path or paths.user_config_path()
        self.default_path = default_path or paths.default_config_path()
        self._lock = threading.RLock()
        self._config = self._load()

    def _load(self) -> AppConfig:
        defaults = _read_yaml(self.default_path)
        user = _read_yaml(self.user_path)
        merged = deep_merge(defaults, user)
        try:
            return AppConfig.model_validate(merged)
        except Exception as exc:  # pydantic.ValidationError and friends
            log.error("User configuration is invalid (%s); falling back to defaults", exc)
            try:
                return AppConfig.model_validate(defaults)
            except Exception:
                return AppConfig()

    @property
    def config(self) -> AppConfig:
        with self._lock:
            return self._config

    def reload(self) -> AppConfig:
        with self._lock:
            self._config = self._load()
            return self._config

    def update(self, new_config: AppConfig) -> None:
        with self._lock:
            self._config = AppConfig.model_validate(new_config.model_dump())
            self.save()

    def save(self) -> None:
        with self._lock:
            data = strip_secret_like_keys(self._config.model_dump(mode="json"))
            self.user_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.user_path.with_suffix(".yaml.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
            tmp.replace(self.user_path)
