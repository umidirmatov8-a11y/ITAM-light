"""SQLite access with schema migrations. One connection guarded by a lock (low write volume)."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

MIGRATIONS: list[str] = [
    # v1
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE apps (
        id            TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        kind          TEXT NOT NULL DEFAULT 'app',
        category      TEXT NOT NULL DEFAULT '',
        launch_type   TEXT NOT NULL,
        target        TEXT NOT NULL,
        args          TEXT NOT NULL DEFAULT '[]',
        working_dir   TEXT NOT NULL DEFAULT '',
        aliases       TEXT NOT NULL DEFAULT '[]',
        process_name  TEXT NOT NULL DEFAULT '',
        source        TEXT NOT NULL DEFAULT 'manual',
        run_as_admin  INTEGER NOT NULL DEFAULT 0,
        enabled       INTEGER NOT NULL DEFAULT 1,
        pinned        INTEGER NOT NULL DEFAULT 0,
        created_at    REAL NOT NULL,
        updated_at    REAL NOT NULL,
        last_launched REAL
    );
    CREATE UNIQUE INDEX apps_target ON apps(launch_type, target);
    CREATE TABLE scenarios (
        id         TEXT PRIMARY KEY,
        name       TEXT NOT NULL,
        aliases    TEXT NOT NULL DEFAULT '[]',
        steps      TEXT NOT NULL DEFAULT '[]',
        enabled    INTEGER NOT NULL DEFAULT 1,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE TABLE history (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        ts       REAL NOT NULL,
        source   TEXT NOT NULL,
        input    TEXT NOT NULL,
        intent   TEXT,
        action   TEXT,
        status   TEXT NOT NULL,
        message  TEXT NOT NULL
    );
    CREATE TABLE audit (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        REAL NOT NULL,
        action    TEXT NOT NULL,
        params    TEXT NOT NULL,
        risk      TEXT NOT NULL,
        source    TEXT NOT NULL,
        decision  TEXT NOT NULL,
        status    TEXT NOT NULL,
        message   TEXT NOT NULL,
        dry_run   INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX audit_ts ON audit(ts);
    CREATE INDEX history_ts ON history(ts);
    """,
]


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            for index in range(version, len(MIGRATIONS)):
                self._conn.execute("BEGIN")
                try:
                    for statement in _split(MIGRATIONS[index]):
                        self._conn.execute(statement)
                    self._conn.execute(f"PRAGMA user_version = {index + 1}")
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise

    @property
    def schema_version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, tuple(params))

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _split(script: str) -> list[str]:
    return [part.strip() for part in script.split(";") if part.strip()]
