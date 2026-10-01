"""Per-analysis workspace database (SQLite through SQLAlchemy).

Alerts are written in batches during parsing and are never all held in memory; the GUI
reads them page by page.  Groups, incidents, IOC, CVE and entity tables are written once
analysis completes.  Raw events are stored zlib-compressed for the technical view.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import threading
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from app.models.analysis import AlertGroup, AttackChain, AnalysisSummary, CVERecord, Incident, IOCRecord

log = logging.getLogger(__name__)

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY,
        uid TEXT, ts REAL, rule_id TEXT, level INTEGER, description TEXT, category TEXT,
        agent TEXT, agent_ip TEXT, src_ip TEXT, dst_ip TEXT, user TEXT, process TEXT, cve TEXT,
        file_path TEXT, hash TEXT, group_id INTEGER, source_file TEXT, full_log TEXT, raw BLOB)""",
    """CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY, key TEXT, rule_id TEXT, rule_level INTEGER, description TEXT, category TEXT,
        agent TEXT, src_ip TEXT, user TEXT, cve TEXT, file_hash TEXT, count INTEGER, first_ts REAL, last_ts REAL,
        risk_score REAL, severity TEXT, severity_rank INTEGER, confidence REAL, fp_probability REAL,
        assessment TEXT, title TEXT, incident_id TEXT, mitre TEXT, data TEXT)""",
    """CREATE TABLE IF NOT EXISTS incidents (
        id TEXT PRIMARY KEY, fingerprint TEXT, kind TEXT, title TEXT, severity TEXT, risk_score REAL,
        status TEXT, event_count INTEGER, first_ts REAL, data TEXT)""",
    """CREATE TABLE IF NOT EXISTS iocs (
        type TEXT, value TEXT, count INTEGER, internal INTEGER, verdict TEXT, data TEXT,
        PRIMARY KEY (type, value))""",
    """CREATE TABLE IF NOT EXISTS cves (cve TEXT PRIMARY KEY, cvss REAL, kev INTEGER, count INTEGER, data TEXT)""",
    """CREATE TABLE IF NOT EXISTS entities (
        type TEXT, name TEXT, events INTEGER, groups INTEGER, max_risk REAL, severity TEXT, severity_rank INTEGER,
        incidents INTEGER, first_ts REAL, last_ts REAL, data TEXT, PRIMARY KEY (type, name))""",
    """CREATE TABLE IF NOT EXISTS chains (id INTEGER PRIMARY KEY, entity TEXT, data TEXT)""",
    """CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)""",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_alerts_group ON alerts(group_id)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_ts ON alerts(ts)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_src ON alerts(src_ip)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_dst ON alerts(dst_ip)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_user ON alerts(user)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_agent_ts ON alerts(agent, ts)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_rule ON alerts(rule_id)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_hash ON alerts(hash)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_cve ON alerts(cve)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_category ON alerts(category)",
]

GROUP_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_groups_sev ON groups(severity_rank, risk_score)",
    "CREATE INDEX IF NOT EXISTS ix_groups_agent ON groups(agent)",
    "CREATE INDEX IF NOT EXISTS ix_groups_src ON groups(src_ip)",
    "CREATE INDEX IF NOT EXISTS ix_groups_rule ON groups(rule_id)",
    "CREATE INDEX IF NOT EXISTS ix_groups_cat ON groups(category)",
]

_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "informational": 0}
_ALERT_INSERT = ("INSERT INTO alerts (uid, ts, rule_id, level, description, category, agent, agent_ip, src_ip, "
                 "dst_ip, user, process, cve, file_path, hash, group_id, source_file, full_log, raw) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")

_IP_RE = re.compile(r"^[0-9a-fA-F:.]+$")
_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,7}$", re.I)
_MITRE_RE = re.compile(r"^T\d{4}(\.\d{3})?$", re.I)
_HASH_RE = re.compile(r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{40}$|^[0-9a-fA-F]{64}$")


@dataclass
class GroupFilter:
    severities: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    agent: str = ""
    src_ip: str = ""
    user: str = ""
    rule_id: str = ""
    text: str = ""
    incident_id: str = ""
    min_risk: float | None = None
    group_ids: list[int] | None = None


@dataclass
class SearchResult:
    term: str
    kind: str
    alerts: int = 0
    hosts: list[str] = field(default_factory=list)
    users: list[str] = field(default_factory=list)
    rules: list[tuple[str, str, int]] = field(default_factory=list)
    src_ips: list[str] = field(default_factory=list)
    incidents: list[tuple[str, str, str]] = field(default_factory=list)
    group_ids: list[int] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.alerts or self.group_ids or self.incidents)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


class AnalysisStore:
    def __init__(self, path: Path | str, create: bool = True):
        self.path = Path(path)
        self.engine: Engine = create_engine(f"sqlite:///{self.path}", future=True,
                                            connect_args={"check_same_thread": False})
        self._write_lock = threading.Lock()

        @event.listens_for(self.engine, "connect")
        def _pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA temp_store=MEMORY")
            cur.execute("PRAGMA cache_size=-65536")
            cur.close()

        if create:
            with self.engine.begin() as conn:
                for stmt in SCHEMA:
                    conn.exec_driver_sql(stmt)

    def close(self) -> None:
        self.engine.dispose()

    # ------------------------------------------------------------------ writing
    @staticmethod
    def compress_raw(raw: dict[str, Any] | None, max_bytes: int) -> bytes | None:
        if raw is None:
            return None
        data = json.dumps(raw, ensure_ascii=False, default=str).encode("utf-8", "replace")
        if len(data) > max_bytes:
            data = data[:max_bytes]
        return zlib.compress(data, 3)

    def insert_alerts(self, rows: list[tuple]) -> None:
        if not rows:
            return
        with self._write_lock, self.engine.begin() as conn:
            conn.exec_driver_sql(_ALERT_INSERT, rows)

    def create_indexes(self) -> None:
        with self._write_lock, self.engine.begin() as conn:
            for stmt in INDEXES:
                conn.exec_driver_sql(stmt)
            conn.exec_driver_sql("ANALYZE")

    def save_groups(self, groups: Iterable[AlertGroup]) -> None:
        rows = []
        for g in groups:
            rows.append((g.id, g.key, g.rule_id, g.rule_level, g.rule_description, g.category, g.agent_name,
                         g.src_ip, g.user, g.cve, g.file_hash, g.count, g.first_ts, g.last_ts, g.risk_score,
                         g.severity, _SEV_RANK.get(g.severity, 0), g.confidence, g.fp_probability, g.assessment,
                         g.title, g.incident_id, " ".join(g.mitre_ids), _dumps(g.to_dict())))
        with self._write_lock, self.engine.begin() as conn:
            conn.exec_driver_sql("DELETE FROM groups")
            for i in range(0, len(rows), 5000):
                conn.exec_driver_sql("INSERT INTO groups VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                     rows[i:i + 5000])
            for stmt in GROUP_INDEXES:
                conn.exec_driver_sql(stmt)

    def update_group(self, g: AlertGroup) -> None:
        with self._write_lock, self.engine.begin() as conn:
            conn.exec_driver_sql("UPDATE groups SET data=?, risk_score=?, severity=?, severity_rank=?, assessment=?, "
                                 "incident_id=? WHERE id=?",
                                 (_dumps(g.to_dict()), g.risk_score, g.severity, _SEV_RANK.get(g.severity, 0),
                                  g.assessment, g.incident_id, g.id))

    def save_incidents(self, incidents: list[Incident]) -> None:
        with self._write_lock, self.engine.begin() as conn:
            conn.exec_driver_sql("DELETE FROM incidents")
            if incidents:
                conn.exec_driver_sql("INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?)", [
                    (i.id, i.fingerprint, i.kind, i.title, i.severity, i.risk_score, i.status, i.event_count,
                     i.first_ts, _dumps(i.to_dict())) for i in incidents])

    def update_incident(self, incident: Incident) -> None:
        with self._write_lock, self.engine.begin() as conn:
            conn.exec_driver_sql("UPDATE incidents SET status=?, data=? WHERE id=?",
                                 (incident.status, _dumps(incident.to_dict()), incident.id))

    def save_iocs(self, iocs: list[IOCRecord]) -> None:
        with self._write_lock, self.engine.begin() as conn:
            conn.exec_driver_sql("DELETE FROM iocs")
            if iocs:
                conn.exec_driver_sql("INSERT OR REPLACE INTO iocs VALUES (?,?,?,?,?,?)", [
                    (i.type, i.value, i.count, int(i.internal), i.verdict, _dumps(i.to_dict())) for i in iocs])

    def save_cves(self, cves: list[CVERecord]) -> None:
        with self._write_lock, self.engine.begin() as conn:
            conn.exec_driver_sql("DELETE FROM cves")
            if cves:
                conn.exec_driver_sql("INSERT OR REPLACE INTO cves VALUES (?,?,?,?,?)", [
                    (c.cve, c.cvss, int(c.known_exploited), c.count, _dumps(c.to_dict())) for c in cves])

    def save_entities(self, rows: list[dict[str, Any]]) -> None:
        with self._write_lock, self.engine.begin() as conn:
            conn.exec_driver_sql("DELETE FROM entities")
            if rows:
                conn.exec_driver_sql("INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
                    (r["type"], r["name"], r["events"], r["groups"], r["max_risk"], r["severity"],
                     _SEV_RANK.get(r["severity"], 0), r["incidents"], r["first_ts"], r["last_ts"],
                     _dumps(r.get("data", {}))) for r in rows])

    def save_chains(self, chains: list[AttackChain]) -> None:
        with self._write_lock, self.engine.begin() as conn:
            conn.exec_driver_sql("DELETE FROM chains")
            if chains:
                conn.exec_driver_sql("INSERT INTO chains VALUES (?,?,?)",
                                     [(c.id, c.entity, _dumps(c.to_dict())) for c in chains])

    def set_meta(self, key: str, value: Any) -> None:
        with self._write_lock, self.engine.begin() as conn:
            conn.exec_driver_sql("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, _dumps(value)))

    # ------------------------------------------------------------------ reading
    def get_meta(self, key: str, default: Any = None) -> Any:
        with self.engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT value FROM meta WHERE key=?", (key,)).first()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except ValueError:
            return default

    def summary(self) -> AnalysisSummary:
        return AnalysisSummary.from_dict(self.get_meta("summary", {}) or {})

    def iter_chain_rows(self, categories: Iterable[str]) -> Iterator[tuple]:
        cats = list(categories)
        placeholders = ",".join("?" for _ in cats)
        with self.engine.connect() as conn:
            result = conn.exec_driver_sql(
                f"SELECT agent, ts, category, group_id, src_ip, user FROM alerts "
                f"WHERE category IN ({placeholders}) AND ts IS NOT NULL ORDER BY agent, ts", tuple(cats))
            for row in result:
                yield tuple(row)

    def alert_count(self) -> int:
        with self.engine.connect() as conn:
            return conn.exec_driver_sql("SELECT COUNT(*) FROM alerts").scalar() or 0

    @staticmethod
    def _group_where(f: GroupFilter | None) -> tuple[str, list[Any]]:
        if f is None:
            return "", []
        clauses: list[str] = []
        params: list[Any] = []
        if f.severities:
            clauses.append("severity IN (" + ",".join("?" for _ in f.severities) + ")")
            params.extend(f.severities)
        if f.categories:
            clauses.append("category IN (" + ",".join("?" for _ in f.categories) + ")")
            params.extend(f.categories)
        for col, value in (("agent", f.agent), ("src_ip", f.src_ip), ("rule_id", f.rule_id),
                           ("incident_id", f.incident_id)):
            if value:
                clauses.append(f"{col} = ?")
                params.append(value)
        if f.user:
            clauses.append("(user = ? OR data LIKE ?)")
            params.extend([f.user, f'%"users": [%"{f.user}"%'])
        if f.min_risk is not None:
            clauses.append("risk_score >= ?")
            params.append(f.min_risk)
        if f.group_ids is not None:
            ids = [int(i) for i in f.group_ids][:5000] or [-1]
            clauses.append("id IN (" + ",".join(str(i) for i in ids) + ")")
        if f.text:
            like = f"%{f.text}%"
            clauses.append("(description LIKE ? OR title LIKE ? OR agent LIKE ? OR src_ip LIKE ? OR user LIKE ? "
                           "OR rule_id = ? OR cve LIKE ? OR mitre LIKE ?)")
            params.extend([like, like, like, like, like, f.text, like, like])
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def count_groups(self, f: GroupFilter | None = None) -> int:
        where, params = self._group_where(f)
        with self.engine.connect() as conn:
            return conn.exec_driver_sql(f"SELECT COUNT(*) FROM groups{where}", tuple(params)).scalar() or 0

    def query_groups(self, f: GroupFilter | None = None, offset: int = 0, limit: int = 500,
                     order: str = "risk") -> list[AlertGroup]:
        where, params = self._group_where(f)
        order_sql = {"risk": "risk_score DESC, count DESC", "time": "first_ts DESC", "count": "count DESC",
                     "id": "id"}.get(order, "risk_score DESC")
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql(f"SELECT data FROM groups{where} ORDER BY {order_sql} LIMIT ? OFFSET ?",
                                        tuple(params) + (int(limit), int(offset))).fetchall()
        return [AlertGroup.from_dict(json.loads(r[0])) for r in rows]

    def group_rows(self, f: GroupFilter | None = None, offset: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        """Light-weight rows for table views (no JSON decoding)."""
        where, params = self._group_where(f)
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT id, severity, risk_score, title, rule_id, rule_level, category, agent, src_ip, user, count, "
                f"first_ts, last_ts, assessment, confidence, fp_probability, incident_id, mitre FROM groups{where} "
                "ORDER BY risk_score DESC, count DESC LIMIT ? OFFSET ?", tuple(params) + (int(limit), int(offset))
            ).mappings().fetchall()
        return [dict(r) for r in rows]

    def get_group(self, group_id: int) -> AlertGroup | None:
        with self.engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT data FROM groups WHERE id=?", (int(group_id),)).first()
        return AlertGroup.from_dict(json.loads(row[0])) if row else None

    def get_groups(self, group_ids: Iterable[int]) -> list[AlertGroup]:
        ids = [int(i) for i in group_ids]
        result: list[AlertGroup] = []
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            with self.engine.connect() as conn:
                rows = conn.exec_driver_sql("SELECT data FROM groups WHERE id IN (" + ",".join("?" * len(chunk)) + ")",
                                            tuple(chunk)).fetchall()
            result.extend(AlertGroup.from_dict(json.loads(r[0])) for r in rows)
        return result

    def iter_all_groups(self, batch: int = 2000) -> Iterator[AlertGroup]:
        offset = 0
        while True:
            groups = self.query_groups(None, offset, batch, order="id")
            if not groups:
                return
            yield from groups
            offset += batch

    def incidents(self) -> list[Incident]:
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT data FROM incidents ORDER BY risk_score DESC").fetchall()
        return [Incident.from_dict(json.loads(r[0])) for r in rows]

    def get_incident(self, incident_id: str) -> Incident | None:
        with self.engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT data FROM incidents WHERE id=?", (incident_id,)).first()
        return Incident.from_dict(json.loads(row[0])) if row else None

    def iocs(self, include_internal: bool = True, limit: int = 100_000) -> list[IOCRecord]:
        where = "" if include_internal else " WHERE internal = 0"
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql(f"SELECT data FROM iocs{where} ORDER BY "
                                        "CASE verdict WHEN 'malicious' THEN 0 WHEN 'suspicious' THEN 1 ELSE 2 END, "
                                        "count DESC LIMIT ?", (limit,)).fetchall()
        return [IOCRecord.from_dict(json.loads(r[0])) for r in rows]

    def cves(self) -> list[CVERecord]:
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT data FROM cves ORDER BY kev DESC, cvss DESC, count DESC").fetchall()
        return [CVERecord.from_dict(json.loads(r[0])) for r in rows]

    def chains(self) -> list[AttackChain]:
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT data FROM chains ORDER BY id").fetchall()
        return [AttackChain.from_dict(json.loads(r[0])) for r in rows]

    def entities(self, entity_type: str, limit: int = 100_000) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT name, events, groups, max_risk, severity, incidents, first_ts, last_ts, data FROM entities "
                "WHERE type=? ORDER BY severity_rank DESC, max_risk DESC, events DESC LIMIT ?",
                (entity_type, limit)).mappings().fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["data"] = json.loads(item["data"] or "{}")
            result.append(item)
        return result

    def query_alerts(self, group_id: int | None = None, severity: str | None = None, text_filter: str = "",
                     offset: int = 0, limit: int = 500, where_extra: tuple[str, list[Any]] | None = None
                     ) -> list[dict[str, Any]]:
        clauses, params = [], []
        if group_id is not None:
            clauses.append("a.group_id = ?")
            params.append(int(group_id))
        if severity:
            clauses.append("g.severity = ?")
            params.append(severity)
        if text_filter:
            like = f"%{text_filter}%"
            clauses.append("(a.description LIKE ? OR a.agent LIKE ? OR a.src_ip LIKE ? OR a.user LIKE ? "
                           "OR a.rule_id = ?)")
            params.extend([like, like, like, like, text_filter])
        if where_extra:
            clauses.append(where_extra[0])
            params.extend(where_extra[1])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = ("SELECT a.id, a.ts, a.rule_id, a.level, a.description, a.category, a.agent, a.src_ip, a.dst_ip, a.user, "
               "a.process, a.cve, a.file_path, a.group_id, g.severity, g.risk_score FROM alerts a "
               f"LEFT JOIN groups g ON a.group_id = g.id{where} ORDER BY a.ts LIMIT ? OFFSET ?")
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql(sql, tuple(params) + (int(limit), int(offset))).mappings().fetchall()
        return [dict(r) for r in rows]

    def count_alerts(self, group_id: int | None = None, severity: str | None = None, text_filter: str = "") -> int:
        clauses, params = [], []
        if group_id is not None:
            clauses.append("a.group_id = ?")
            params.append(int(group_id))
        if severity:
            clauses.append("g.severity = ?")
            params.append(severity)
        if text_filter:
            like = f"%{text_filter}%"
            clauses.append("(a.description LIKE ? OR a.agent LIKE ? OR a.src_ip LIKE ? OR a.user LIKE ? "
                           "OR a.rule_id = ?)")
            params.extend([like, like, like, like, text_filter])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        join = " LEFT JOIN groups g ON a.group_id = g.id" if severity else ""
        with self.engine.connect() as conn:
            return conn.exec_driver_sql(f"SELECT COUNT(*) FROM alerts a{join}{where}", tuple(params)).scalar() or 0

    def alert_detail(self, alert_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT * FROM alerts WHERE id=?", (int(alert_id),)).mappings().first()
        if not row:
            return None
        item = dict(row)
        raw = item.pop("raw", None)
        if raw:
            try:
                text_raw = zlib.decompress(raw).decode("utf-8", "replace")
                try:
                    item["raw"] = json.loads(text_raw)
                except ValueError:
                    item["raw"] = text_raw + " …(truncated)"
            except zlib.error:
                item["raw"] = None
        return item

    def iter_alert_rows(self, batch: int = 10_000) -> Iterator[dict[str, Any]]:
        last_id = 0
        while True:
            with self.engine.connect() as conn:
                rows = conn.exec_driver_sql(
                    "SELECT a.id, a.ts, a.rule_id, a.level, a.description, a.category, a.agent, a.agent_ip, a.src_ip, "
                    "a.dst_ip, a.user, a.process, a.cve, a.file_path, a.hash, a.group_id, a.source_file, "
                    "g.severity, g.risk_score FROM alerts a LEFT JOIN groups g ON a.group_id = g.id "
                    "WHERE a.id > ? ORDER BY a.id LIMIT ?", (last_id, batch)).mappings().fetchall()
            if not rows:
                return
            for r in rows:
                yield dict(r)
            last_id = rows[-1]["id"]

    # ------------------------------------------------------------------ statistics
    def severity_counts(self) -> dict[str, int]:
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT severity, SUM(count), COUNT(*) FROM groups GROUP BY severity").fetchall()
        return {r[0]: int(r[1] or 0) for r in rows}

    def group_severity_counts(self) -> dict[str, int]:
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT severity, COUNT(*) FROM groups GROUP BY severity").fetchall()
        return {r[0]: int(r[1] or 0) for r in rows}

    def timeline(self, buckets: int = 60) -> dict[str, Any]:
        with self.engine.connect() as conn:
            lo, hi = conn.exec_driver_sql("SELECT MIN(ts), MAX(ts) FROM alerts WHERE ts IS NOT NULL").first() or (None, None)
            if lo is None:
                return {"start": None, "bucket": 0, "series": {}}
            span = max(hi - lo, 60.0)
            nice = [60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800]
            size = next((n for n in nice if span / n <= buckets), 604800)
            start = lo - (lo % size)
            rows = conn.exec_driver_sql(
                "SELECT CAST((a.ts - ?) / ? AS INTEGER) AS b, g.severity, COUNT(*) FROM alerts a "
                "JOIN groups g ON a.group_id = g.id WHERE a.ts IS NOT NULL GROUP BY b, g.severity",
                (start, size)).fetchall()
        n = int((hi - start) // size) + 1
        series: dict[str, list[int]] = {}
        for b, sev, cnt in rows:
            arr = series.setdefault(sev, [0] * n)
            if 0 <= b < n:
                arr[b] += cnt
        return {"start": start, "bucket": size, "series": series, "n": n}

    def top(self, column: str, limit: int = 10, where: str = "") -> list[tuple[str, int]]:
        allowed = {"rule_id", "agent", "src_ip", "user", "category", "cve", "dst_ip", "process"}
        if column not in allowed:
            raise ValueError(column)
        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql(
                f"SELECT {column}, COUNT(*) c FROM alerts WHERE {column} IS NOT NULL AND {column} != '' "
                f"{('AND ' + where) if where else ''} GROUP BY {column} ORDER BY c DESC LIMIT ?", (limit,)).fetchall()
        return [(r[0], int(r[1])) for r in rows]

    # ------------------------------------------------------------------ search
    def search(self, term: str, limit_groups: int = 500) -> SearchResult:
        term = term.strip()
        kind = "text"
        alert_where: tuple[str, list[Any]]
        if _IP_RE.match(term) and self._is_ip(term):
            kind = "ip"
            alert_where = ("(a.src_ip = ? OR a.dst_ip = ? OR a.agent_ip = ?)", [term, term, term])
        elif _CVE_RE.match(term):
            kind, term = "cve", term.upper()
            alert_where = ("a.cve = ?", [term])
        elif _MITRE_RE.match(term):
            kind, term = "mitre", term.upper()
            alert_where = ("a.group_id IN (SELECT id FROM groups WHERE (' ' || mitre || ' ') LIKE ?)",
                           [f"% {term}%"])
        elif _HASH_RE.match(term):
            kind, term = "hash", term.lower()
            alert_where = ("a.hash = ?", [term])
        elif term.isdigit():
            kind = "rule"
            alert_where = ("a.rule_id = ?", [term])
        else:
            like = f"%{term}%"
            alert_where = ("(a.agent = ? OR a.user = ? OR a.src_ip = ? OR a.description LIKE ? OR a.process LIKE ? "
                           "OR a.file_path LIKE ? OR a.full_log LIKE ?)", [term, term, term, like, like, like, like])
            kind = "text"
        result = SearchResult(term=term, kind=kind)
        sql_where = " WHERE " + alert_where[0]
        params = tuple(alert_where[1])
        with self.engine.connect() as conn:
            result.alerts = conn.exec_driver_sql(f"SELECT COUNT(*) FROM alerts a{sql_where}", params).scalar() or 0
            if result.alerts == 0 and kind in ("hash", "text"):
                # IOCs extracted from free text are only in the groups/iocs tables
                like = f"%{term}%"
                gids = [r[0] for r in conn.exec_driver_sql(
                    "SELECT id FROM groups WHERE data LIKE ? LIMIT ?", (like, limit_groups)).fetchall()]
                if gids:
                    sql_where = " WHERE a.group_id IN (" + ",".join(str(g) for g in gids) + ")"
                    params = ()
                    result.alerts = conn.exec_driver_sql(f"SELECT COUNT(*) FROM alerts a{sql_where}").scalar() or 0
            if not result.alerts:
                return result
            result.hosts = [r[0] for r in conn.exec_driver_sql(
                f"SELECT DISTINCT a.agent FROM alerts a{sql_where} AND a.agent != '' LIMIT 200", params)]
            result.users = [r[0] for r in conn.exec_driver_sql(
                f"SELECT DISTINCT a.user FROM alerts a{sql_where} AND a.user != '' LIMIT 200", params)]
            result.src_ips = [r[0] for r in conn.exec_driver_sql(
                f"SELECT DISTINCT a.src_ip FROM alerts a{sql_where} AND a.src_ip != '' LIMIT 200", params)]
            result.rules = [(r[0], r[1], int(r[2])) for r in conn.exec_driver_sql(
                f"SELECT a.rule_id, MAX(a.description), COUNT(*) c FROM alerts a{sql_where} GROUP BY a.rule_id "
                "ORDER BY c DESC LIMIT 100", params)]
            result.group_ids = [r[0] for r in conn.exec_driver_sql(
                f"SELECT DISTINCT a.group_id FROM alerts a{sql_where} LIMIT ?", params + (limit_groups,))]
        gid_set = set(result.group_ids)
        for inc in self.incidents():
            if gid_set & set(inc.group_ids) or term in inc.source_ips or term in inc.cves:
                result.incidents.append((inc.id, inc.title, inc.severity))
        return result

    @staticmethod
    def _is_ip(value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False
