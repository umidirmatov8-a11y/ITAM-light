"""Command history and the audit log of executed / denied operations."""
from __future__ import annotations

import csv
import io
import json
import time
from typing import Any

from .db import Database


class Journal:
    def __init__(self, db: Database, max_rows: int = 20000):
        self._db = db
        self._max_rows = max_rows

    # --- history -------------------------------------------------------
    def add_history(self, *, source: str, input: str, intent: str | None, action: str | None,
                    status: str, message: str) -> None:
        self._db.execute(
            "INSERT INTO history(ts, source, input, intent, action, status, message) VALUES(?,?,?,?,?,?,?)",
            (time.time(), source, input[:2000], intent, action, status, message[:4000]),
        )
        self._trim("history")

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.query("SELECT * FROM history ORDER BY id DESC LIMIT ?", (max(1, min(limit, 1000)),))
        return [dict(row) for row in rows]

    def clear_history(self) -> int:
        return self._db.execute("DELETE FROM history").rowcount

    # --- audit -----------------------------------------------------------
    def audit(self, *, action: str, params: dict[str, Any], risk: str, source: str, decision: str,
              status: str, message: str, dry_run: bool = False) -> None:
        self._db.execute(
            "INSERT INTO audit(ts, action, params, risk, source, decision, status, message, dry_run)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (time.time(), action, json.dumps(params, ensure_ascii=False, default=str)[:4000], risk,
             source, decision, status, message[:4000], int(dry_run)),
        )
        self._trim("audit")

    def audit_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.query("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (max(1, min(limit, 5000)),))
        result = []
        for row in rows:
            item = dict(row)
            item["params"] = json.loads(item["params"])
            item["dry_run"] = bool(item["dry_run"])
            result.append(item)
        return result

    def clear_audit(self) -> int:
        return self._db.execute("DELETE FROM audit").rowcount

    def export(self, fmt: str = "json") -> str:
        entries = self.audit_entries(limit=5000)
        entries.reverse()
        history = self.history(limit=1000)
        history.reverse()
        if fmt == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["time", "action", "params", "risk", "source", "decision", "status", "dry_run", "message"])
            for item in entries:
                writer.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item["ts"])), item["action"],
                    json.dumps(item["params"], ensure_ascii=False), item["risk"], item["source"],
                    item["decision"], item["status"], item["dry_run"], item["message"],
                ])
            return buffer.getvalue()
        return json.dumps({"exported_at": time.time(), "audit": entries, "history": history},
                          ensure_ascii=False, indent=2)

    def _trim(self, table: str) -> None:
        self._db.execute(
            f"DELETE FROM {table} WHERE id <= (SELECT MAX(id) FROM {table}) - ?", (self._max_rows,)
        )
