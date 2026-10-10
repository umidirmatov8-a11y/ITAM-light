"""Local SQLite storage: settings, connection profiles (without passwords), saved/historical LDAP queries,
saved table filters, user/offboarding templates and the application operation journal.

Secrets are never written here. Every value passing through :meth:`Database.set_setting` and the journal is masked.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..security.masking import mask_mapping, mask_text

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS profiles (
    name TEXT PRIMARY KEY, data TEXT NOT NULL, last_used TEXT
);
CREATE TABLE IF NOT EXISTS saved_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, base_dn TEXT, scope TEXT NOT NULL,
    filter TEXT NOT NULL, attributes TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS query_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, base_dn TEXT, scope TEXT NOT NULL, filter TEXT NOT NULL,
    attributes TEXT NOT NULL, result_count INTEGER, error TEXT
);
CREATE TABLE IF NOT EXISTS saved_filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT, view TEXT NOT NULL, name TEXT NOT NULL, data TEXT NOT NULL,
    UNIQUE(view, name)
);
CREATE TABLE IF NOT EXISTS templates (
    kind TEXT NOT NULL, name TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(kind, name)
);
CREATE TABLE IF NOT EXISTS operation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, windows_user TEXT, ldap_identity TEXT, domain TEXT,
    dc TEXT, operation TEXT NOT NULL, target TEXT, result TEXT NOT NULL, error TEXT, details TEXT, batch_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_oplog_ts ON operation_log(ts);
"""


def default_data_dir() -> Path:
    override = os.environ.get("ADTOOLKIT_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return Path(base) / "ADAdminToolkit"
    return Path(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")) / "ADAdminToolkit"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path | None = None):
        if path is None:
            data_dir = default_data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            path = data_dir / "toolkit.db"
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL" if self.path != ":memory:" else "PRAGMA journal_mode=MEMORY")
            self._conn.executescript(SCHEMA)
            self._conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))

    def close(self):
        with self._lock:
            self._conn.close()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    # --- settings -------------------------------------------------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        rows = self._all("SELECT value FROM settings WHERE key=?", (key,))
        if not rows:
            return default
        try:
            return json.loads(rows[0]["value"])
        except json.JSONDecodeError:
            return default

    def set_setting(self, key: str, value: Any) -> None:
        if any(s in key.lower() for s in ("password", "secret", "token")):
            raise ValueError("Секретные значения не сохраняются в базе настроек")
        self._exec("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, json.dumps(value, ensure_ascii=False)))

    # --- profiles -------------------------------------------------------------------------------------------------
    def save_profile(self, profile_dict: dict) -> None:
        data = {k: v for k, v in profile_dict.items() if "password" not in k.lower()}
        self._exec("INSERT INTO profiles(name, data, last_used) VALUES(?, ?, ?) "
                   "ON CONFLICT(name) DO UPDATE SET data=excluded.data, last_used=excluded.last_used",
                   (data["name"], json.dumps(data, ensure_ascii=False), _now()))

    def list_profiles(self) -> list[dict]:
        return [json.loads(r["data"]) for r in self._all("SELECT data FROM profiles ORDER BY last_used DESC")]

    def delete_profile(self, name: str) -> None:
        self._exec("DELETE FROM profiles WHERE name=?", (name,))

    # --- LDAP queries ---------------------------------------------------------------------------------------------
    def add_query_history(self, base_dn: str, scope: str, flt: str, attributes: list[str], count: int | None,
                          error: str | None = None, keep: int = 500) -> None:
        self._exec("INSERT INTO query_history(ts, base_dn, scope, filter, attributes, result_count, error) "
                   "VALUES(?,?,?,?,?,?,?)", (_now(), base_dn, scope, flt, json.dumps(attributes), count,
                                             mask_text(error) if error else None))
        self._exec("DELETE FROM query_history WHERE id NOT IN (SELECT id FROM query_history ORDER BY id DESC LIMIT ?)",
                   (keep,))

    def query_history(self, limit: int = 200) -> list[dict]:
        rows = self._all("SELECT * FROM query_history ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) | {"attributes": json.loads(r["attributes"])} for r in rows]

    def clear_query_history(self) -> None:
        self._exec("DELETE FROM query_history")

    def save_query(self, name: str, base_dn: str, scope: str, flt: str, attributes: list[str]) -> None:
        self._exec("INSERT INTO saved_queries(name, base_dn, scope, filter, attributes, created) VALUES(?,?,?,?,?,?) "
                   "ON CONFLICT(name) DO UPDATE SET base_dn=excluded.base_dn, scope=excluded.scope, "
                   "filter=excluded.filter, attributes=excluded.attributes",
                   (name, base_dn, scope, flt, json.dumps(attributes), _now()))

    def saved_queries(self) -> list[dict]:
        rows = self._all("SELECT * FROM saved_queries ORDER BY name")
        return [dict(r) | {"attributes": json.loads(r["attributes"])} for r in rows]

    def delete_query(self, name: str) -> None:
        self._exec("DELETE FROM saved_queries WHERE name=?", (name,))

    # --- saved table filters ------------------------------------------------------------------------------------
    def save_filter(self, view: str, name: str, data: dict) -> None:
        self._exec("INSERT INTO saved_filters(view, name, data) VALUES(?,?,?) "
                   "ON CONFLICT(view, name) DO UPDATE SET data=excluded.data", (view, name, json.dumps(data, ensure_ascii=False)))

    def saved_filters(self, view: str) -> list[dict]:
        rows = self._all("SELECT name, data FROM saved_filters WHERE view=? ORDER BY name", (view,))
        return [{"name": r["name"], **json.loads(r["data"])} for r in rows]

    def delete_filter(self, view: str, name: str) -> None:
        self._exec("DELETE FROM saved_filters WHERE view=? AND name=?", (view, name))

    # --- templates ------------------------------------------------------------------------------------------------
    def save_template(self, kind: str, name: str, data: dict) -> None:
        clean = mask_mapping(data)
        self._exec("INSERT INTO templates(kind, name, data) VALUES(?,?,?) ON CONFLICT(kind, name) DO UPDATE SET data=excluded.data",
                   (kind, name, json.dumps(clean, ensure_ascii=False)))

    def templates(self, kind: str) -> list[dict]:
        rows = self._all("SELECT name, data FROM templates WHERE kind=? ORDER BY name", (kind,))
        return [{"name": r["name"], **json.loads(r["data"])} for r in rows]

    def delete_template(self, kind: str, name: str) -> None:
        self._exec("DELETE FROM templates WHERE kind=? AND name=?", (kind, name))

    # --- operation journal -------------------------------------------------------------------------------------
    def add_operation(self, *, windows_user: str, ldap_identity: str, domain: str, dc: str, operation: str,
                      target: str, result: str, error: str | None, details: dict | None, batch_id: str | None) -> int:
        cur = self._exec(
            "INSERT INTO operation_log(ts, windows_user, ldap_identity, domain, dc, operation, target, result, error, "
            "details, batch_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (_now(), windows_user, ldap_identity, domain, dc, operation, mask_text(target), result,
             mask_text(error) if error else None,
             json.dumps(mask_mapping(details or {}), ensure_ascii=False, default=str), batch_id))
        return int(cur.lastrowid)

    def operations(self, limit: int = 500, text: str = "", result: str = "") -> list[dict]:
        sql = "SELECT * FROM operation_log"
        cond, params = [], []
        if text:
            cond.append("(operation LIKE ? OR target LIKE ? OR error LIKE ?)")
            like = f"%{text}%"
            params += [like, like, like]
        if result:
            cond.append("result=?")
            params.append(result)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._all(sql, tuple(params))]
