"""Credential storage in Windows Credential Manager (via ``keyring``) — only with explicit consent.

Passwords are never written to SQLite, logs, CSV, reports or dumps. If no secure backend is available the feature is
reported as unavailable instead of falling back to an insecure store.
"""
from __future__ import annotations

import logging

from ..core.errors import UnsupportedFeatureError

log = logging.getLogger(__name__)
SERVICE = "ADAdminToolkit"


def _keyring():
    try:
        import keyring
    except ImportError:
        return None
    try:
        backend = keyring.get_keyring()
    except Exception:  # noqa: BLE001
        return None
    name = type(backend).__module__ + "." + type(backend).__name__
    # refuse insecure / null backends (plaintext files, chained-with-nothing, fail)
    if any(bad in name.lower() for bad in ("fail", "null", "plaintext", "file", "chainer")):
        try:
            from keyring.backends.chainer import ChainerBackend
            if isinstance(backend, ChainerBackend) and backend.backends:
                return keyring
        except Exception:  # noqa: BLE001
            pass
        return None
    return keyring


def available() -> tuple[bool, str]:
    kr = _keyring()
    if kr is None:
        return False, "Безопасное хранилище учётных данных недоступно (Windows Credential Manager)"
    try:
        backend = kr.get_keyring()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    return True, type(backend).__name__


class CredentialStore:
    def __init__(self, service: str = SERVICE):
        self.service = service

    def save(self, target: str, username: str, password: str, *, consent: bool) -> None:
        if not consent:
            raise UnsupportedFeatureError("Пароль сохраняется только с явного согласия администратора")
        kr = _keyring()
        if kr is None:
            raise UnsupportedFeatureError("Диспетчер учётных данных Windows недоступен — пароль не сохранён")
        kr.set_password(self.service, target, password)
        log.info("Учётные данные сохранены в хранилище ОС для %s", target)

    def load(self, target: str) -> str | None:
        kr = _keyring()
        if kr is None:
            return None
        try:
            return kr.get_password(self.service, target)
        except Exception:  # noqa: BLE001
            log.warning("Не удалось прочитать учётные данные из хранилища ОС для %s", target)
            return None

    def delete(self, target: str) -> None:
        kr = _keyring()
        if kr is None:
            return
        try:
            kr.delete_password(self.service, target)
        except Exception:  # noqa: BLE001 - absent entry
            pass
