"""Shared fixtures. All tests use the in-memory demo directory or fake ldap3 connections — never a real domain."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ADTOOLKIT_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ADTOOLKIT_CONFIG", raising=False)


@pytest.fixture
def db():
    from adtoolkit.storage.database import Database
    d = Database(":memory:")
    yield d
    d.close()


@pytest.fixture
def settings():
    from adtoolkit.core.app_config import AppSettings
    return AppSettings(bulk_rate_per_second=50.0)


@pytest.fixture
def ctx(db, settings):
    """Writable demo directory context (in-memory, fictional domain demo.local)."""
    from adtoolkit.ldap.demo_data import create_demo_gateway
    from adtoolkit.security.audit_log import OperationJournal
    from adtoolkit.services.context import ServiceContext
    gw = create_demo_gateway(read_only=False)
    return ServiceContext(gw, settings, OperationJournal(db))


@pytest.fixture
def ro_ctx(db, settings):
    from adtoolkit.ldap.demo_data import create_demo_gateway
    from adtoolkit.security.audit_log import OperationJournal
    from adtoolkit.services.context import ServiceContext
    return ServiceContext(create_demo_gateway(read_only=True), settings, OperationJournal(db))


def find_user(ctx, sam):
    from adtoolkit.services.user_service import UserService
    found = UserService(ctx).find_by_identity(sam)
    assert found, sam
    return found[0].dn
