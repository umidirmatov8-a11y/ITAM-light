"""Shared fixtures. Every test session uses an isolated WSA_HOME (no user files are touched)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_HOME = tempfile.mkdtemp(prefix="wsa_test_home_")
os.environ["WSA_HOME"] = _HOME
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.core.config import AppConfig  # noqa: E402
from app.core.secrets import MemorySecretStore  # noqa: E402


@pytest.fixture
def config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def secrets() -> MemorySecretStore:
    return MemorySecretStore()


@pytest.fixture
def sample_dir() -> Path:
    return ROOT / "sample_data"


def make_alert(rule_id="5710", level=5, description="sshd: Attempt to login using a non-existent user",
               groups=("syslog", "sshd", "authentication_failed", "invalid_login"), agent="web-01",
               agent_ip="10.0.0.5", ts="2026-09-30T10:00:00.000+0000", data=None, full_log="", alert_id=None,
               mitre=None, **extra) -> dict:
    doc = {"timestamp": ts, "rule": {"id": rule_id, "level": level, "description": description,
                                     "groups": list(groups)},
           "agent": {"id": "001", "name": agent, "ip": agent_ip}, "data": data or {}, "full_log": full_log}
    if mitre:
        doc["rule"]["mitre"] = {"id": mitre}
    if alert_id:
        doc["id"] = alert_id
    doc.update(extra)
    return doc


@pytest.fixture
def alert_factory():
    return make_alert


def write_jsonl(path: Path, alerts: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(a) for a in alerts) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def jsonl_writer():
    return write_jsonl


@pytest.fixture(scope="session")
def demo_session(tmp_path_factory):
    from app.services.pipeline import AnalysisPipeline

    ws = tmp_path_factory.mktemp("demo_ws")
    session = AnalysisPipeline(AppConfig(), workspace=ws, online=False).run([ROOT / "sample_data"])
    yield session
    session.close()
