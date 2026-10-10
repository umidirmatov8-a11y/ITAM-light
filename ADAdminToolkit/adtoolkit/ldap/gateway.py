"""Directory access layer contract.

Services never talk to ldap3 directly; they use a :class:`DirectoryGateway`. Two implementations exist:

* :class:`adtoolkit.ldap.ldap3_gateway.Ldap3Gateway` — real Active Directory through ldap3;
* :class:`adtoolkit.ldap.memory_gateway.MemoryGateway` — in-memory directory for demo mode and automated tests.

All write methods go through :meth:`DirectoryGateway._guard_write`, so read-only mode is enforced in one place
regardless of which UI path requested a change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Iterator

from ..core.cancel import CancelToken
from ..core.errors import InsecureConnectionError, ReadOnlyModeError
from ..models.connection import DirectoryInfo
from .filters import FilterNode, parse_filter


class Scope(str, Enum):
    BASE = "base"
    ONELEVEL = "onelevel"
    SUBTREE = "subtree"


class ModOp(str, Enum):
    ADD = "add"
    DELETE = "delete"
    REPLACE = "replace"


Changes = dict[str, list[tuple[ModOp, list]]]


class CaseInsensitiveDict(dict):
    """dict with case-insensitive string keys that preserves the original key spelling."""

    def __init__(self, data=None):
        super().__init__()
        self._keys: dict[str, str] = {}
        if data:
            for k, v in data.items():
                self[k] = v

    def __setitem__(self, key, value):
        lk = key.lower()
        if lk in self._keys and self._keys[lk] != key:
            super().__delitem__(self._keys[lk])
        self._keys[lk] = key
        super().__setitem__(key, value)

    def __getitem__(self, key):
        return super().__getitem__(self._keys[key.lower()])

    def __delitem__(self, key):
        real = self._keys.pop(key.lower())
        super().__delitem__(real)

    def __contains__(self, key):
        return isinstance(key, str) and key.lower() in self._keys

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, *default):
        if key in self:
            v = self[key]
            del self[key]
            return v
        if default:
            return default[0]
        raise KeyError(key)

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def update(self, other=(), **kwargs):
        items = other.items() if hasattr(other, "items") else other
        for k, v in items:
            self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def copy(self):
        return CaseInsensitiveDict(dict(self.items()))


@dataclass
class Entry:
    dn: str
    attributes: CaseInsensitiveDict = field(default_factory=CaseInsensitiveDict)

    def __post_init__(self):
        if not isinstance(self.attributes, CaseInsensitiveDict):
            self.attributes = CaseInsensitiveDict(self.attributes)

    def values(self, name: str) -> list:
        return list(self.attributes.get(name) or [])

    def first(self, name: str, default=None):
        vals = self.attributes.get(name)
        return vals[0] if vals else default

    def has(self, name: str) -> bool:
        return bool(self.attributes.get(name))

    def str(self, name: str, default: str = "") -> str:
        v = self.first(name)
        return default if v is None else str(v)

    def int(self, name: str, default: int | None = None) -> int | None:
        v = self.first(name)
        try:
            return int(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    @property
    def object_classes(self) -> list[str]:
        return [str(v).lower() for v in self.values("objectClass")]


@dataclass
class SearchStats:
    entries: int = 0
    pages: int = 0
    truncated: bool = False
    referrals: int = 0


ConnectionListener = Callable[[str, str], None]   # (state, message)


class DirectoryGateway:
    """Abstract directory access. Implementations must be safe to call from worker threads."""

    is_demo = False

    def __init__(self) -> None:
        self.read_only = True
        self.info = DirectoryInfo()
        self._listeners: list[ConnectionListener] = []
        self.default_page_size = 500

    # --- state ----------------------------------------------------------------------------------------------
    def add_listener(self, listener: ConnectionListener) -> None:
        self._listeners.append(listener)

    def _notify(self, state: str, message: str = "") -> None:
        for listener in list(self._listeners):
            try:
                listener(state, message)
            except Exception:  # listeners must never break directory operations
                pass

    @property
    def encrypted(self) -> bool:
        return self.info.encrypted

    @property
    def connected(self) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    def _guard_write(self) -> None:
        if self.read_only:
            raise ReadOnlyModeError(hint="Отключите режим «Только чтение» в верхней панели, если изменение действительно требуется.")

    def _require_encryption(self, what: str) -> None:
        if not self.encrypted:
            raise InsecureConnectionError(
                f"{what} возможна только по зашифрованному соединению (LDAPS или StartTLS)",
                hint="Переподключитесь с режимом безопасности LDAPS или StartTLS.")

    @staticmethod
    def filter_text(flt: FilterNode | str) -> str:
        if isinstance(flt, FilterNode):
            return flt.to_ldap()
        # strings are validated (and re-rendered canonically) before they reach the server
        return parse_filter(flt).to_ldap()

    # --- read ---------------------------------------------------------------------------------------------------
    def search(self, base: str, flt: FilterNode | str, attributes: Iterable[str] | None = None,
               scope: Scope = Scope.SUBTREE, *, page_size: int | None = None, size_limit: int = 0,
               cancel: CancelToken | None = None, stats: SearchStats | None = None,
               sd_flags: int | None = None) -> Iterator[Entry]:  # pragma: no cover - abstract
        raise NotImplementedError

    def search_list(self, *args, **kwargs) -> list[Entry]:
        return list(self.search(*args, **kwargs))

    def get(self, dn: str, attributes: Iterable[str] | None = None, *, sd_flags: int | None = None) -> Entry | None:
        from ..core.errors import ObjectNotFoundError
        try:
            items = list(self.search(dn, "(objectClass=*)", attributes, Scope.BASE, page_size=0, sd_flags=sd_flags))
        except ObjectNotFoundError:
            return None
        return items[0] if items else None

    def count(self, base: str, flt: FilterNode | str, scope: Scope = Scope.SUBTREE,
              cancel: CancelToken | None = None) -> int:
        n = 0
        for _ in self.search(base, flt, ["1.1"], scope, cancel=cancel):
            n += 1
        return n

    def root_dse(self) -> Entry:  # pragma: no cover - abstract
        raise NotImplementedError

    def who_am_i(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def ping(self) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    # --- write ------------------------------------------------------------------------------------------------
    def modify(self, dn: str, changes: Changes) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def add(self, dn: str, object_classes: list[str], attributes: dict) -> None:  # pragma: no cover
        raise NotImplementedError

    def delete(self, dn: str) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def move(self, dn: str, new_parent: str, new_rdn: str | None = None) -> str:  # pragma: no cover
        raise NotImplementedError

    def set_password(self, dn: str, new_password: str) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def reconnect(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def clone_for_host(self, host: str) -> "DirectoryGateway":  # pragma: no cover - optional
        """Separate read-only connection to another DC (used to read non-replicated lastLogon)."""
        raise NotImplementedError
