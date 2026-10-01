"""Secure storage of API keys.

Secrets are stored in the operating system credential vault through ``keyring``
(Windows Credential Manager on Windows, Keychain on macOS, Secret Service on Linux).
They are never written to ``config.yaml`` or to logs.  Environment variables
(``WSA_<NAME>``) are honoured as a read-only fallback for headless/CI use.  When no
secure backend is available, secrets set during the session are kept in memory only.
"""

from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger(__name__)

SERVICE_NAME = "WazuhSecurityAnalyzer"

KNOWN_SECRETS: dict[str, str] = {
    "openai_api_key": "OpenAI API key",
    "anthropic_api_key": "Anthropic API key",
    "compatible_api_key": "OpenAI-compatible endpoint API key",
    "virustotal_api_key": "VirusTotal API key",
    "abuseipdb_api_key": "AbuseIPDB API key",
    "otx_api_key": "AlienVault OTX API key",
    "nvd_api_key": "NVD API key (optional, raises rate limit)",
}


class SecretStore:
    def __init__(self, service: str = SERVICE_NAME, use_keyring: bool = True):
        self.service = service
        self._memory: dict[str, str] = {}
        self._lock = threading.Lock()
        self._keyring = None
        if use_keyring:
            self._keyring = self._init_keyring()

    @staticmethod
    def _init_keyring():
        try:
            import keyring
            from keyring.backends import fail

            backend = keyring.get_keyring()
            if isinstance(backend, fail.Keyring):
                log.warning("No secure credential backend available; API keys will be kept in memory only")
                return None
            # Refuse insecure plaintext backends that may be installed by third-party packages.
            name = type(backend).__module__ + "." + type(backend).__name__
            if "plaintext" in name.lower():
                log.warning("Insecure keyring backend %s ignored; API keys will be kept in memory only", name)
                return None
            return keyring
        except Exception as exc:  # keyring import errors, DBus problems on Linux, etc.
            log.warning("Credential backend unavailable (%s); API keys will be kept in memory only", exc)
            return None

    @property
    def persistent(self) -> bool:
        return self._keyring is not None

    @staticmethod
    def _env_name(name: str) -> str:
        return "WSA_" + name.upper()

    def get(self, name: str) -> str | None:
        with self._lock:
            if name in self._memory:
                return self._memory[name] or None
        if self._keyring is not None:
            try:
                value = self._keyring.get_password(self.service, name)
                if value:
                    return value
            except Exception as exc:
                log.warning("Could not read secret %s from credential store: %s", name, type(exc).__name__)
        value = os.environ.get(self._env_name(name))
        return value or None

    def has(self, name: str) -> bool:
        return bool(self.get(name))

    def set(self, name: str, value: str) -> bool:
        """Store a secret. Returns True when persisted securely, False when kept in memory only."""
        value = (value or "").strip()
        if not value:
            self.delete(name)
            return self.persistent
        if self._keyring is not None:
            try:
                self._keyring.set_password(self.service, name, value)
                with self._lock:
                    self._memory.pop(name, None)
                return True
            except Exception as exc:
                log.warning("Could not persist secret %s (%s); keeping it in memory", name, type(exc).__name__)
        with self._lock:
            self._memory[name] = value
        return False

    def delete(self, name: str) -> None:
        with self._lock:
            self._memory.pop(name, None)
        if self._keyring is not None:
            try:
                self._keyring.delete_password(self.service, name)
            except Exception:
                pass


class MemorySecretStore(SecretStore):
    """Non-persistent store used by tests and the headless CLI."""

    def __init__(self, values: dict[str, str] | None = None):
        super().__init__(use_keyring=False)
        for key, value in (values or {}).items():
            self._memory[key] = value
