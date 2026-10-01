"""End-to-end analysis pipeline.

    files -> discovery (ZIP/GZ safety) -> format detection -> streaming parse
          -> normalize -> classify -> group + store (batched)
          -> correlation (success-after-failure, attack chains, campaigns)
          -> MITRE mapping -> IOC/CVE records -> threat intelligence (offline/online)
          -> false-positive analysis -> risk scoring -> explanations -> recommendations
          -> incidents -> entities / dashboard / executive summary

Runs in a background thread in the GUI.  Progress is reported through a callback and the
run can be cancelled through a ``threading.Event``.  Errors in individual records, files or
providers never abort the analysis.
"""

from __future__ import annotations

import hashlib
import io
import logging
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable

from app.analyzers.classifier import AlertClassifier
from app.analyzers.explainer import Explainer
from app.analyzers.false_positive import FalsePositiveAnalyzer
from app.analyzers.normalizer import Normalizer
from app.analyzers.risk_engine import RiskEngine
from app.analyzers.rule_knowledge import default_rule_kb
from app.core import paths
from app.core.config import AppConfig
from app.core.errors import AnalysisCancelled, InputRejectedError
from app.core.secrets import MemorySecretStore, SecretStore
from app.core.severity import SEVERITY_ORDER, Severity
from app.correlation.chains import STAGES, ChainDetector
from app.correlation.grouping import GroupBuilder, peak_in_window
from app.correlation.incidents import IncidentBuilder, mark_campaigns
from app.database.store import AnalysisStore
from app.intelligence.enrichment import EnrichmentService, worst_verdict
from app.intelligence.mitre import default_catalog, map_alert_group
from app.models.analysis import AlertGroup, AnalysisSummary, CVERecord, IOCRecord
from app.parsers.base import ParseContext
from app.parsers.registry import SNIFF_BYTES, decode_head, detect_encoding, detect_parser, open_text
from app.parsers.sources import SourceDiscovery
from app.recommendations.engine import RecommendationEngine
from app.reports.summary import build_executive_summary
from app.services.audit import audit
from app.services.session import AnalysisSession
from app.utils.net import NetworkClassifier

log = logging.getLogger("wsa.analysis")

# Share of the overall progress bar per stage
_STAGE_SPAN = {"parse": (0, 70), "correlate": (70, 78), "enrich": (78, 88), "score": (88, 95), "finalize": (95, 100)}


@dataclass
class Progress:
    stage: str
    message: str
    processed: int = 0
    total: int | None = None
    percent: float = 0.0


class _CountingReader(io.RawIOBase):
    def __init__(self, raw: BinaryIO):
        super().__init__()
        self._raw = raw
        self.count = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        data = self._raw.read(len(buffer))
        n = len(data)
        buffer[:n] = data
        self.count += n
        return n

    def close(self) -> None:
        try:
            self._raw.close()
        finally:
            super().close()


def cleanup_workspaces(keep: int) -> None:
    files = sorted(paths.workspace_dir().glob("analysis_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(str(old) + suffix).unlink(missing_ok=True)
            except OSError:
                pass


class AnalysisPipeline:
    def __init__(self, config: AppConfig, secrets: SecretStore | None = None, state=None,
                 progress: Callable[[Progress], None] | None = None, cancel: threading.Event | None = None,
                 workspace: Path | None = None, http_transport=None, online: bool | None = None):
        self.config = config
        self.secrets = secrets or MemorySecretStore()
        self.state = state
        self._progress_cb = progress or (lambda p: None)
        self.cancel = cancel or threading.Event()
        self.workspace = workspace
        self.http_transport = http_transport
        self.online = config.network.online if online is None else online
        self._last_emit = 0.0

    # ------------------------------------------------------------------ progress
    def _emit(self, stage: str, message: str, fraction: float, processed: int = 0, total: int | None = None,
              force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_emit < 0.15:
            return
        self._last_emit = now
        lo, hi = _STAGE_SPAN.get(stage, (0, 100))
        percent = lo + (hi - lo) * max(0.0, min(1.0, fraction))
        try:
            self._progress_cb(Progress(stage, message, processed, total, round(percent, 1)))
        except Exception:  # a broken UI callback must not kill the analysis
            log.debug("progress callback failed", exc_info=True)

    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise AnalysisCancelled("Analysis cancelled by user")

    # ------------------------------------------------------------------ main entry
    def run(self, inputs: list[str | Path]) -> AnalysisSession:
        started = time.time()
        cfg = self.config
        ws_dir = self.workspace or paths.workspace_dir()
        ws_dir.mkdir(parents=True, exist_ok=True)
        db_path = ws_dir / f"analysis_{time.strftime('%Y%m%d_%H%M%S')}_{int(started * 1000) % 1000:03d}.db"
        store = AnalysisStore(db_path)
        summary = AnalysisSummary(mode="online" if self.online else "offline", analyzed_at=started)
        audit("analysis_started", inputs=len(inputs), mode=summary.mode)
        log.info("Analysis started: %d input(s), mode=%s, workspace=%s", len(inputs), summary.mode, db_path.name)
        try:
            session = self._run(inputs, store, summary)
        except AnalysisCancelled:
            store.close()
            for suffix in ("", "-wal", "-shm"):
                Path(str(db_path) + suffix).unlink(missing_ok=True)
            audit("analysis_cancelled")
            raise
        summary.duration_seconds = round(time.time() - started, 2)
        store.set_meta("summary", summary.to_dict())
        audit("analysis_completed", events=summary.events, incidents=summary.incidents,
              duration=summary.duration_seconds)
        log.info("Analysis completed: %d events, %d groups, %d incidents in %.1fs", summary.events, summary.groups,
                 summary.incidents, summary.duration_seconds)
        if self.workspace is None:
            cleanup_workspaces(cfg.storage.keep_workspaces)
        return session

    def _run(self, inputs: list[str | Path], store: AnalysisStore, summary: AnalysisSummary) -> AnalysisSession:
        cfg = self.config
        network = NetworkClassifier(cfg.wazuh.internal_networks, cfg.wazuh.known_scanners)
        rule_kb = default_rule_kb()
        catalog = default_catalog()

        # ---------------------------------------------------------------- 1. discovery & parsing
        self._emit("parse", "Discovering input files", 0.0, force=True)
        discovery = SourceDiscovery(cfg.limits).discover(inputs)
        summary.rejected_inputs = discovery.rejected
        summary.warnings.extend(discovery.warnings)
        for rejected in discovery.rejected:
            log.warning("Input rejected: %s", rejected)
        normalizer = Normalizer(cfg.storage.store_raw_events, cfg.storage.max_raw_event_kb * 1024,
                                cfg.privacy.internal_domains)
        classifier = AlertClassifier(rule_kb, network)
        builder = GroupBuilder(network, cfg.correlation.max_groups)
        total_bytes = max(discovery.total_bytes, 1)
        done_bytes = 0
        seen: set[bytes] = set()
        batch: list[tuple] = []
        rules: Counter = Counter()
        agents: set[str] = set()
        parsers_used: Counter = Counter()
        events = 0
        max_raw = cfg.storage.max_raw_event_kb * 1024
        batch_size = cfg.limits.batch_size

        for source in discovery.sources:
            self._check_cancel()
            try:
                with source.open() as fh:
                    head = fh.read(SNIFF_BYTES)
            except (InputRejectedError, OSError, EOFError) as exc:
                summary.rejected_inputs.append(f"{source.display_name}: {exc}")
                continue
            encoding = detect_encoding(head)
            parser_cls, score = detect_parser(decode_head(head, encoding), source.display_name)
            parser = parser_cls()
            log.info("%s: detected %s (confidence %.2f, encoding %s)", source.display_name, parser.name, score,
                     encoding)
            ctx = ParseContext(source.display_name, cfg.limits.max_line_mb * 1024 * 1024)
            file_events = 0
            counter: _CountingReader | None = None
            try:
                counter = _CountingReader(source.open())
                with open_text(io.BufferedReader(counter, buffer_size=1 << 20), encoding) as text_stream:
                    for raw in parser.parse(text_stream, ctx):
                        try:
                            alert = normalizer.normalize(raw, source.display_name, parser.name)
                            raw_blob = store.compress_raw(alert.raw, max_raw) if alert.raw is not None else None
                        except (ValueError, TypeError, RecursionError, KeyError, AttributeError) as exc:
                            # one pathological record must never abort the rest of the file
                            ctx.error(f"record could not be normalized: {type(exc).__name__}")
                            continue
                        if cfg.storage.deduplicate:
                            key = hashlib.blake2b(alert.uid.encode("utf-8", "replace"), digest_size=10).digest()
                            if key in seen:
                                summary.duplicates += 1
                                continue
                            seen.add(key)
                        alert.category = classifier.classify(alert)
                        gid = builder.add(alert)
                        events += 1
                        file_events += 1
                        rules[alert.rule_id] += 1
                        if alert.agent_name:
                            agents.add(alert.agent_name)
                        if summary.first_ts is None or (alert.timestamp and alert.timestamp < summary.first_ts):
                            summary.first_ts = alert.timestamp or summary.first_ts
                        if alert.timestamp and (summary.last_ts is None or alert.timestamp > summary.last_ts):
                            summary.last_ts = alert.timestamp
                        batch.append((
                            alert.uid, alert.timestamp, alert.rule_id, alert.rule_level, alert.rule_description,
                            alert.category, alert.agent_name, alert.agent_ip, alert.src_ip, alert.dst_ip, alert.user,
                            alert.process, alert.primary_cve, alert.file_path, alert.primary_hash, gid,
                            source.display_name, alert.full_log[:1024], raw_blob,
                        ))
                        if len(batch) >= batch_size:
                            store.insert_alerts(batch)
                            batch = []
                            self._check_cancel()
                            fraction = (done_bytes + counter.count) / total_bytes
                            est = int(events / fraction) if fraction > 0.01 else None
                            self._emit("parse", f"Analyzing {source.display_name}", fraction, events, est)
            except InputRejectedError as exc:
                summary.rejected_inputs.append(str(exc))
                log.warning("Input rejected while reading: %s", exc)
            except AnalysisCancelled:
                raise
            except Exception as exc:
                summary.rejected_inputs.append(f"{source.display_name}: read error ({type(exc).__name__}: {exc})")
                log.exception("Failed to read %s", source.display_name)
            finally:
                done_bytes += source.size if counter is None else max(counter.count, 0)
            summary.parse_errors += ctx.errors
            if ctx.errors:
                summary.warnings.append(f"{source.display_name}: {ctx.errors} malformed record(s) skipped")
            parsers_used[parser.name] += file_events
            summary.files += 1
            summary.file_names.append(source.display_name)
            log.info("%s: %d events, %d errors", source.display_name, file_events, ctx.errors)
        if batch:
            store.insert_alerts(batch)
        summary.events = events
        summary.agents = len(agents)
        summary.rules = len(rules)
        summary.parsers_used = dict(parsers_used)
        del seen
        if events == 0:
            summary.warnings.append("No events could be extracted from the provided input.")
        self._emit("parse", "Indexing events", 1.0, events, events, force=True)
        store.create_indexes()
        self._check_cancel()

        groups: list[AlertGroup] = list(builder.groups.values())
        by_id = {g.id: g for g in groups}
        window_s = cfg.correlation.chain_window_minutes * 60
        for g in groups:
            g.peak_count = peak_in_window(g.timestamps, window_s, g.count)
        del builder

        # ---------------------------------------------------------------- 2. correlation
        self._emit("correlate", "Correlating events into attack chains", 0.1, force=True)
        detector = ChainDetector(cfg.correlation.chain_window_minutes, cfg.correlation.min_chain_stages,
                                 cfg.correlation.bruteforce_threshold,
                                 cfg.correlation.success_after_failure_window_minutes, network.is_external)
        chains = detector.run(store.iter_chain_rows(STAGES.keys()), by_id)
        mark_campaigns(groups, cfg.correlation.campaign_min_events)
        self._emit("correlate", "Mapping MITRE ATT&CK techniques", 0.7, force=True)
        for g in groups:
            g.mitre = map_alert_group(g, catalog, rule_kb, cfg.correlation.bruteforce_threshold)
        self._check_cancel()

        # ---------------------------------------------------------------- 3. enrichment
        iocs = self._build_iocs(groups, network, cfg.privacy.internal_domains)
        cves = self._build_cves(groups)
        self._emit("enrich", "Threat intelligence enrichment", 0.0, force=True)

        def ti_progress(message: str, done: int, total: int) -> None:
            self._emit("enrich", message, done / total if total else 0.0, done, total)

        enrichment = EnrichmentService(cfg, self.secrets, self.state, ti_progress, self.cancel, self.http_transport)
        report = enrichment.enrich(iocs, cves, online=self.online)
        summary.enrichment_status = report.status
        if report.errors:
            summary.warnings.extend(report.errors[:10])
        self._apply_enrichment(groups, iocs, cves)
        self._check_cancel()

        # ---------------------------------------------------------------- 4. analysis
        self._emit("score", "Scoring risk and building explanations", 0.0, force=True)
        fp = FalsePositiveAnalyzer(network, rule_kb)
        risk = RiskEngine(cfg)
        explainer = Explainer(rule_kb, cfg.correlation.bruteforce_threshold)
        recs = RecommendationEngine(rule_kb, cfg.risk_thresholds.high)
        chain_stage_counts = {c.id: c.distinct_stages for c in chains}
        for idx, g in enumerate(groups):
            g.fp_probability, g.fp_reasons, g.fp_counter_reasons = fp.analyze(g)
            risk.score(g, chain_stage_counts)
            explainer.explain(g)
            g.recommendations = recs.for_group(g)
            if idx % 2000 == 0:
                self._emit("score", "Scoring risk and building explanations", idx / max(len(groups), 1), idx,
                           len(groups))
                self._check_cancel()

        # ---------------------------------------------------------------- 5. incidents & persistence
        self._emit("finalize", "Building incidents", 0.1, force=True)
        status_lookup = self.state.get_status if self.state is not None else None
        incidents = IncidentBuilder(cfg, risk, recs, status_lookup).build(groups, chains)
        store.save_groups(groups)
        store.save_incidents(incidents)
        store.save_chains(chains)
        self._link_iocs(iocs, groups)
        store.save_iocs(iocs)
        store.save_cves(cves)
        self._emit("finalize", "Computing statistics", 0.6, force=True)
        self._save_entities(store, groups, incidents)

        sev_counts = store.severity_counts()
        summary.severity_counts = {s.value: sev_counts.get(s.value, 0) for s in SEVERITY_ORDER}
        summary.group_severity_counts = store.group_severity_counts()
        summary.groups = len(groups)
        summary.incidents = len(incidents)
        summary.chains = len(chains)
        summary.iocs = len(iocs)
        summary.cves = len(cves)
        summary.external_ips = sum(1 for i in iocs if i.type == "ip" and not i.internal)
        summary.affected_hosts = len({g.agent_name for g in groups if g.agent_name and
                                      Severity.parse(g.severity).rank >= Severity.MEDIUM.rank})
        summary.affected_users = len({u for g in groups if Severity.parse(g.severity).rank >= Severity.MEDIUM.rank
                                      for u in g.users})
        mitre_stats = self._mitre_stats(groups)
        summary.mitre_techniques = len(mitre_stats)
        store.set_meta("mitre", mitre_stats)
        store.set_meta("dashboard", self._dashboard(store, groups, iocs))
        store.set_meta("config_snapshot", {"risk_thresholds": cfg.risk_thresholds.model_dump(),
                                           "mode": summary.mode})
        summary.executive_summary = build_executive_summary(summary, incidents)
        self._emit("finalize", "Done", 1.0, events, events, force=True)
        return AnalysisSession(store, summary)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _build_iocs(groups: list[AlertGroup], network: NetworkClassifier, internal_domains: list[str]) -> list[IOCRecord]:
        records: dict[tuple[str, str], IOCRecord] = {}
        agent_ips = {g.agent_ip for g in groups if g.agent_ip}
        agent_names = {g.agent_name.lower() for g in groups if g.agent_name}
        internal_suffixes = tuple("." + d.lower().lstrip(".") for d in internal_domains)
        for g in groups:
            for ioc_type, value, count in g.ioc_items():
                if ioc_type == "ip" and value in agent_ips:
                    continue
                key = (ioc_type, value)
                rec = records.get(key)
                if rec is None:
                    internal = False
                    if ioc_type == "ip":
                        internal = bool(network.is_internal(value))
                    elif ioc_type == "domain":
                        internal = value in agent_names or (bool(internal_suffixes) and value.endswith(internal_suffixes))
                    rec = records[key] = IOCRecord(type=ioc_type, value=value, internal=internal)
                rec.count += count
                if g.first_ts is not None and (rec.first_seen is None or g.first_ts < rec.first_seen):
                    rec.first_seen = g.first_ts
                if g.last_ts is not None and (rec.last_seen is None or g.last_ts > rec.last_seen):
                    rec.last_seen = g.last_ts
                if g.agent_name and g.agent_name not in rec.hosts and len(rec.hosts) < 100:
                    rec.hosts.append(g.agent_name)
                if len(rec.group_ids) < 200:
                    rec.group_ids.append(g.id)
        return sorted(records.values(), key=lambda r: -r.count)

    @staticmethod
    def _build_cves(groups: list[AlertGroup]) -> list[CVERecord]:
        records: dict[str, CVERecord] = {}
        for g in groups:
            for cve in g.cves:
                rec = records.get(cve)
                if rec is None:
                    rec = records[cve] = CVERecord(cve=cve)
                rec.count += g.count
                if g.agent_name and g.agent_name not in rec.hosts and len(rec.hosts) < 500:
                    rec.hosts.append(g.agent_name)
                for pkg in g.packages:
                    if pkg not in rec.packages and len(rec.packages) < 20:
                        rec.packages.append(pkg)
                if g.cvss is not None and g.cve == cve and (rec.cvss is None or g.cvss > rec.cvss):
                    rec.cvss = g.cvss
                    rec.severity = g.vuln_severity or rec.severity
                    if "Wazuh vulnerability detector" not in rec.sources:
                        rec.sources.append("Wazuh vulnerability detector")
                if len(rec.group_ids) < 500:
                    rec.group_ids.append(g.id)
        return list(records.values())

    @staticmethod
    def _apply_enrichment(groups: list[AlertGroup], iocs: list[IOCRecord], cves: list[CVERecord]) -> None:
        verdicts = {(r.type, r.value): r for r in iocs if r.verdict in ("malicious", "suspicious", "clean")}
        cve_map = {c.cve: c for c in cves}
        for g in groups:
            relevant = [verdicts[(t, v)] for t, v, _ in g.ioc_items() if (t, v) in verdicts]
            if relevant:
                verdict = worst_verdict(r.verdict for r in relevant)
                g.ioc_verdict = verdict
                sources: list[str] = []
                for r in relevant:
                    if r.verdict == verdict:
                        for s in r.sources:
                            if s.get("verdict") == verdict:
                                label = f"{s.get('provider')}: {r.value}"
                                if label not in sources:
                                    sources.append(label)
                g.ioc_verdict_sources = sources[:5]
            for cve in g.cves:
                rec = cve_map.get(cve)
                if rec is None:
                    continue
                if rec.known_exploited:
                    g.kev = True
                if g.cvss is None and rec.cvss is not None and cve == g.cve:
                    g.cvss = rec.cvss

    @staticmethod
    def _link_iocs(iocs: list[IOCRecord], groups: list[AlertGroup]) -> None:
        # nothing to add beyond group ids today; kept for symmetry and future enrichment
        return None

    @staticmethod
    def _mitre_stats(groups: list[AlertGroup]) -> list[dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        rank = {"high": 3, "medium": 2, "low": 1}
        for g in groups:
            for m in g.mitre:
                s = stats.setdefault(m.technique_id, {"technique_id": m.technique_id, "name": m.name,
                                                      "tactics": m.tactics, "events": 0, "groups": 0,
                                                      "confidence": m.confidence, "max_risk": 0.0, "url": m.url,
                                                      "sources": [], "evidence": [], "hosts": []})
                s["events"] += g.count
                s["groups"] += 1
                s["max_risk"] = max(s["max_risk"], g.risk_score)
                if rank[m.confidence] > rank[s["confidence"]]:
                    s["confidence"] = m.confidence
                if m.source not in s["sources"]:
                    s["sources"].append(m.source)
                if m.evidence and m.evidence not in s["evidence"] and len(s["evidence"]) < 5:
                    s["evidence"].append(m.evidence)
                if g.agent_name and g.agent_name not in s["hosts"] and len(s["hosts"]) < 50:
                    s["hosts"].append(g.agent_name)
        return sorted(stats.values(), key=lambda s: (-s["max_risk"], -s["events"]))

    @staticmethod
    def _save_entities(store: AnalysisStore, groups: list[AlertGroup], incidents) -> None:
        sev_rank = {s.value: s.rank for s in Severity}
        host_info: dict[str, dict[str, Any]] = defaultdict(lambda: {"max_risk": 0.0, "severity": "informational",
                                                                     "groups": 0, "categories": Counter(),
                                                                     "users": set(), "src_ips": set(), "ip": "",
                                                                     "criticality": "", "rules": Counter()})
        user_info: dict[str, dict[str, Any]] = defaultdict(lambda: {"max_risk": 0.0, "severity": "informational",
                                                                     "groups": 0, "hosts": set(), "src_ips": set(),
                                                                     "categories": Counter()})
        for g in groups:
            if g.agent_name:
                h = host_info[g.agent_name]
                h["groups"] += 1
                h["ip"] = h["ip"] or g.agent_ip
                h["criticality"] = g.asset_criticality
                h["categories"][g.category] += g.count
                h["rules"][g.rule_id] += g.count
                if len(h["users"]) < 50:
                    h["users"].update(g.users[:10])
                if len(h["src_ips"]) < 50 and g.src_ip:
                    h["src_ips"].add(g.src_ip)
                if g.risk_score > h["max_risk"]:
                    h["max_risk"] = g.risk_score
                if sev_rank.get(g.severity, 0) > sev_rank.get(h["severity"], 0):
                    h["severity"] = g.severity
            for user in g.users:
                u = user_info[user]
                u["groups"] += 1
                if g.agent_name and len(u["hosts"]) < 50:
                    u["hosts"].add(g.agent_name)
                if g.src_ip and len(u["src_ips"]) < 50:
                    u["src_ips"].add(g.src_ip)
                u["categories"][g.category] += 1
                if g.risk_score > u["max_risk"]:
                    u["max_risk"] = g.risk_score
                if sev_rank.get(g.severity, 0) > sev_rank.get(u["severity"], 0):
                    u["severity"] = g.severity
        host_incidents: Counter = Counter()
        user_incidents: Counter = Counter()
        for inc in incidents:
            for h in inc.affected_hosts:
                host_incidents[h] += 1
            for u in inc.affected_users:
                user_incidents[u] += 1
        rows: list[dict[str, Any]] = []
        with store.engine.connect() as conn:
            for name, events, first, last in conn.exec_driver_sql(
                    "SELECT agent, COUNT(*), MIN(ts), MAX(ts) FROM alerts WHERE agent != '' GROUP BY agent"):
                h = host_info.get(name)
                if h is None:
                    continue
                rows.append({"type": "host", "name": name, "events": events, "groups": h["groups"],
                             "max_risk": h["max_risk"], "severity": h["severity"], "incidents": host_incidents[name],
                             "first_ts": first, "last_ts": last,
                             "data": {"ip": h["ip"], "criticality": h["criticality"],
                                      "categories": dict(h["categories"].most_common(8)),
                                      "top_rules": dict(h["rules"].most_common(8)),
                                      "users": sorted(h["users"])[:30], "src_ips": sorted(h["src_ips"])[:30]}})
            for name, events, first, last in conn.exec_driver_sql(
                    "SELECT user, COUNT(*), MIN(ts), MAX(ts) FROM alerts WHERE user != '' GROUP BY user"):
                u = user_info.get(name)
                if u is None:
                    continue
                rows.append({"type": "user", "name": name, "events": events, "groups": u["groups"],
                             "max_risk": u["max_risk"], "severity": u["severity"], "incidents": user_incidents[name],
                             "first_ts": first, "last_ts": last,
                             "data": {"hosts": sorted(u["hosts"])[:30], "src_ips": sorted(u["src_ips"])[:30],
                                      "categories": dict(u["categories"].most_common(8))}})
        store.save_entities(rows)

    @staticmethod
    def _dashboard(store: AnalysisStore, groups: list[AlertGroup], iocs: list[IOCRecord]) -> dict[str, Any]:
        rule_desc = {}
        for g in groups:
            rule_desc.setdefault(g.rule_id, g.rule_description)
        top_rules = [(rid, rule_desc.get(rid, ""), cnt) for rid, cnt in store.top("rule_id", 10)]
        external = [(i.value, i.count, i.verdict) for i in iocs if i.type == "ip" and not i.internal][:10]
        repeated = sorted(groups, key=lambda g: -g.count)[:10]
        categories = Counter()
        for g in groups:
            categories[g.category] += g.count
        return {
            "top_rules": top_rules,
            "top_hosts": store.top("agent", 10),
            "top_src_ips": store.top("src_ip", 10),
            "top_external_ips": external,
            "top_users": store.top("user", 10),
            "categories": categories.most_common(),
            "repeated": [(g.id, g.rule_id, g.rule_description, g.agent_name, g.count, g.severity) for g in repeated],
            "timeline": store.timeline(),
            "top_cves": [(c, n) for c, n in store.top("cve", 10)],
        }
