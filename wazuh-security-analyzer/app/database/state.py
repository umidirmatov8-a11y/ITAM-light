"""Application state database (incident triage status, threat-intel cache).

SQLite by default (``state.db`` in the user data directory).  Set
``storage.state_database_url`` to a SQLAlchemy URL such as
``postgresql+psycopg://user@host/wsa`` to share triage state through PostgreSQL.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from sqlalchemy import Column, Float, MetaData, String, Table, Text, create_engine, delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core import paths

log = logging.getLogger(__name__)

metadata = MetaData()

incident_status = Table(
    "incident_status", metadata,
    Column("fingerprint", String(64), primary_key=True),
    Column("status", String(32), nullable=False),
    Column("note", Text, default=""),
    Column("updated_at", Float, nullable=False),
)

ti_cache = Table(
    "ti_cache", metadata,
    Column("key", String(512), primary_key=True),
    Column("value", Text, nullable=False),
    Column("expires_at", Float, nullable=False),
)


class StateStore:
    def __init__(self, url: str | None = None):
        self.url = url or f"sqlite:///{paths.state_db_path()}"
        connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(self.url, future=True, pool_pre_ping=True, connect_args=connect_args)
        self._lock = threading.Lock()
        metadata.create_all(self.engine)

    # -------------------------------------------------------------- incident status
    def get_status(self, fingerprint: str) -> str | None:
        try:
            with self.engine.connect() as conn:
                row = conn.execute(select(incident_status.c.status).where(
                    incident_status.c.fingerprint == fingerprint)).first()
                return row[0] if row else None
        except SQLAlchemyError as exc:
            log.error("State DB read failed: %s", exc)
            return None

    def all_statuses(self) -> dict[str, str]:
        try:
            with self.engine.connect() as conn:
                return {r[0]: r[1] for r in conn.execute(select(incident_status.c.fingerprint,
                                                                incident_status.c.status))}
        except SQLAlchemyError as exc:
            log.error("State DB read failed: %s", exc)
            return {}

    def set_status(self, fingerprint: str, status: str, note: str = "") -> None:
        with self._lock, self.engine.begin() as conn:
            exists = conn.execute(select(incident_status.c.fingerprint).where(
                incident_status.c.fingerprint == fingerprint)).first()
            values = {"status": status, "note": note, "updated_at": time.time()}
            if exists:
                conn.execute(update(incident_status).where(incident_status.c.fingerprint == fingerprint).values(**values))
            else:
                conn.execute(incident_status.insert().values(fingerprint=fingerprint, **values))

    # -------------------------------------------------------------- TI cache
    def cache_get(self, key: str) -> Any | None:
        try:
            with self.engine.connect() as conn:
                row = conn.execute(select(ti_cache.c.value, ti_cache.c.expires_at).where(ti_cache.c.key == key)).first()
        except SQLAlchemyError as exc:
            log.warning("TI cache read failed: %s", exc)
            return None
        if not row or row[1] < time.time():
            return None
        try:
            return json.loads(row[0])
        except ValueError:
            return None

    def cache_set(self, key: str, value: Any, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        payload = json.dumps(value, default=str)
        try:
            with self._lock, self.engine.begin() as conn:
                conn.execute(delete(ti_cache).where(ti_cache.c.key == key))
                conn.execute(ti_cache.insert().values(key=key, value=payload, expires_at=time.time() + ttl_seconds))
        except SQLAlchemyError as exc:
            log.warning("TI cache write failed: %s", exc)

    def purge_expired(self) -> None:
        try:
            with self._lock, self.engine.begin() as conn:
                conn.execute(delete(ti_cache).where(ti_cache.c.expires_at < time.time()))
        except SQLAlchemyError as exc:
            log.warning("TI cache purge failed: %s", exc)

    def dispose(self) -> None:
        self.engine.dispose()
