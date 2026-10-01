"""Command-line entry point.

    WazuhSecurityAnalyzer.exe                         start the GUI
    WazuhSecurityAnalyzer.exe alerts.json logs.zip    start the GUI and analyze the files
    WazuhSecurityAnalyzer.exe --analyze PATH [PATH..] [--online] [--report-dir DIR] [--formats pdf,html,json]
                                                      headless analysis + reports
    WazuhSecurityAnalyzer.exe --self-test             analyze the bundled demo dataset and verify results
    WazuhSecurityAnalyzer.exe --api [--port 8765]     local REST API (FastAPI, 127.0.0.1 only)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from app import __app_name__, __version__


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="WazuhSecurityAnalyzer", description=f"{__app_name__} {__version__}")
    p.add_argument("paths", nargs="*", help="files, folders or archives to open in the GUI")
    p.add_argument("--analyze", nargs="+", metavar="PATH", help="run a headless analysis")
    p.add_argument("--online", action="store_true", help="enable online enrichment for --analyze")
    p.add_argument("--report-dir", default="", help="write reports to this folder (with --analyze)")
    p.add_argument("--formats", default="html,json", help="report formats: pdf,html,docx,xlsx,csv,json")
    p.add_argument("--self-test", action="store_true", help="analyze the demo dataset and verify the results")
    p.add_argument("--api", action="store_true", help="start the local REST API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    return p


def _headless(paths: list[str], online: bool, report_dir: str, formats: str) -> int:
    from app.core.config import ConfigManager
    from app.core.logging_setup import setup_logging
    from app.core.secrets import SecretStore
    from app.database.state import StateStore
    from app.reports.exporters import export_report
    from app.services.pipeline import AnalysisPipeline

    cfg = ConfigManager().config
    setup_logging(cfg.logging.level, console=False)
    state = StateStore(cfg.storage.state_database_url or None)
    last = {"t": 0.0}

    def progress(p) -> None:
        if time.monotonic() - last["t"] > 1.0:
            last["t"] = time.monotonic()
            print(f"  [{p.percent:5.1f}%] {p.message} {p.processed:,}" if p.processed else
                  f"  [{p.percent:5.1f}%] {p.message}", file=sys.stderr)

    session = AnalysisPipeline(cfg, SecretStore(), state, progress=progress, online=online).run(paths)
    s = session.summary
    print(json.dumps({"files": s.files, "events": s.events, "severity_counts": s.severity_counts,
                      "incidents": s.incidents, "chains": s.chains, "enrichment": s.enrichment_status,
                      "rejected": s.rejected_inputs, "duration_seconds": s.duration_seconds}, indent=2))
    for inc in session.incidents()[:15]:
        print(f"{inc.id}  {inc.severity.upper():<13} {inc.risk_score:5.1f}  {inc.title}  [{inc.assessment}]")
    print("\n" + s.executive_summary)
    if report_dir:
        written = export_report(session, Path(report_dir), [f.strip() for f in formats.split(",") if f.strip()])
        for path in written:
            print(f"report: {path}")
    session.close()
    state.dispose()
    return 0 if s.events else 2


def self_test() -> int:
    """Analyze the bundled demo data and check key expectations. Used to validate the packaged .exe."""
    import tempfile

    from app.core import paths
    from app.core.config import AppConfig
    from app.reports.exporters import export_report
    from app.services.pipeline import AnalysisPipeline

    out_lines: list[str] = []
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        session = AnalysisPipeline(AppConfig(), workspace=Path(tmp), online=False).run([paths.sample_data_dir()])
        s = session.summary
        checks = {
            "events parsed": s.events > 2000,
            "no parse errors": s.parse_errors == 0,
            "critical findings": s.severity_counts.get("critical", 0) > 0,
            "attack chains": s.chains >= 2,
            "incidents": s.incidents >= 5,
            "mitre techniques": s.mitre_techniques >= 5,
            "cves": s.cves >= 5,
        }
        written = export_report(session, Path(tmp) / "reports", ["pdf", "html", "docx", "xlsx", "csv", "json"])
        checks["reports exported"] = all(p.exists() and p.stat().st_size > 0 for p in written)
        session.close()
        for name, passed in checks.items():
            out_lines.append(f"{'PASS' if passed else 'FAIL'}  {name}")
            ok = ok and passed
    out_lines.append(f"SELF-TEST {'PASSED' if ok else 'FAILED'} ({s.events} events, {s.incidents} incidents)")
    text = "\n".join(out_lines)
    print(text)
    try:
        (paths.logs_dir() / "self_test.log").write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.self_test:
        return self_test()
    if args.analyze:
        return _headless(args.analyze, args.online, args.report_dir, args.formats)
    if args.api:
        from app.api.server import serve
        return serve(args.host, args.port)
    from app.ui.app import run_gui
    return run_gui(initial_paths=args.paths or None)
