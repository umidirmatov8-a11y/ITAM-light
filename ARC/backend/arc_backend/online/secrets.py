"""API keys of online providers.

On Windows keys live in the Windows Credential Manager (generic credentials, encrypted with DPAPI
for the current user). They are never written to arc.db, logs or API responses — the API only
reports whether a key is set. Elsewhere (development on Linux) an in-memory store is used.
"""
from __future__ import annotations

import ctypes
import re
import sys
import threading
from typing import Optional, Protocol

TARGET_PREFIX = "ARC/online/"
_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")


class SecretError(RuntimeError):
    pass


def validate_secret(name: str, value: str) -> str:
    if not _NAME.match(name):
        raise SecretError("Недопустимое имя ключа")
    value = value.strip()
    if not 8 <= len(value) <= 512 or any(ch.isspace() or not ch.isprintable() for ch in value):
        raise SecretError("Ключ должен быть строкой из 8–512 видимых символов без пробелов")
    return value


class SecretStore(Protocol):
    backend: str
    persistent: bool

    def get(self, name: str) -> Optional[str]: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> bool: ...


class MemorySecretStore:
    backend = "memory"
    persistent = False

    def __init__(self) -> None:
        self._items: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> Optional[str]:
        with self._lock:
            return self._items.get(name)

    def set(self, name: str, value: str) -> None:
        value = validate_secret(name, value)
        with self._lock:
            self._items[name] = value

    def delete(self, name: str) -> bool:
        with self._lock:
            return self._items.pop(name, None) is not None


if sys.platform == "win32":
    from ctypes import wintypes

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class _CREDENTIALW(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", _FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                    ("UserName", wintypes.LPWSTR)]

    _PCRED = ctypes.POINTER(_CREDENTIALW)


class WindowsCredentialStore:
    backend = "windows-credential-manager"
    persistent = True

    def __init__(self) -> None:
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)  # type: ignore[attr-defined]
        self._write = advapi.CredWriteW
        self._write.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        self._write.restype = wintypes.BOOL
        self._read = advapi.CredReadW
        self._read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_PCRED)]
        self._read.restype = wintypes.BOOL
        self._delete = advapi.CredDeleteW
        self._delete.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._delete.restype = wintypes.BOOL
        self._free = advapi.CredFree
        self._free.argtypes = [ctypes.c_void_p]
        self._free.restype = None

    def get(self, name: str) -> Optional[str]:
        if not _NAME.match(name):
            return None
        pcred = _PCRED()
        if not self._read(TARGET_PREFIX + name, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
            if ctypes.get_last_error() == ERROR_NOT_FOUND:  # type: ignore[attr-defined]
                return None
            raise SecretError(f"Диспетчер учётных данных: ошибка {ctypes.get_last_error()}")  # type: ignore[attr-defined]
        try:
            cred = pcred.contents
            data = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            return data.decode("utf-8")
        finally:
            self._free(pcred)

    def set(self, name: str, value: str) -> None:
        value = validate_secret(name, value)
        blob = value.encode("utf-8")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        cred = _CREDENTIALW()
        cred.Type = CRED_TYPE_GENERIC
        cred.TargetName = TARGET_PREFIX + name
        cred.Comment = "A.R.C. online provider key"
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = "arc"
        if not self._write(ctypes.byref(cred), 0):
            raise SecretError(f"Не удалось сохранить ключ: ошибка {ctypes.get_last_error()}")  # type: ignore[attr-defined]

    def delete(self, name: str) -> bool:
        if not _NAME.match(name):
            return False
        if self._delete(TARGET_PREFIX + name, CRED_TYPE_GENERIC, 0):
            return True
        if ctypes.get_last_error() == ERROR_NOT_FOUND:  # type: ignore[attr-defined]
            return False
        raise SecretError(f"Не удалось удалить ключ: ошибка {ctypes.get_last_error()}")  # type: ignore[attr-defined]


def create_secret_store() -> SecretStore:
    if sys.platform == "win32":
        try:
            return WindowsCredentialStore()
        except (OSError, AttributeError):
            pass
    return MemorySecretStore()
