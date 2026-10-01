"""Filesystem locations used by the application.

Read-only resources are resolved relative to the bundle root (the project
directory in development, ``sys._MEIPASS`` in a PyInstaller build).  Writable
data (configuration, logs, workspaces, state database) lives in a per-user
directory so the executable can run from a read-only location.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "WazuhSecurityAnalyzer"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Directory that contains bundled read-only files (resources, config, sample data)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if is_frozen() and meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[2]


def resources_dir() -> Path:
    return bundle_root() / "resources"


def knowledge_dir() -> Path:
    return resources_dir() / "knowledge"


def templates_dir() -> Path:
    return resources_dir() / "templates"


def default_config_path() -> Path:
    return bundle_root() / "config" / "default_config.yaml"


def sample_data_dir() -> Path:
    return bundle_root() / "sample_data"


def user_data_dir() -> Path:
    """Per-user writable directory. ``WSA_HOME`` overrides it (used by tests and portable mode)."""
    override = os.environ.get("WSA_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = (Path(local) if local else Path.home() / "AppData" / "Local") / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".local" / "share") / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _subdir(name: str) -> Path:
    path = user_data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    return _subdir("logs")


def workspace_dir() -> Path:
    return _subdir("workspace")


def reports_dir() -> Path:
    return _subdir("reports")


def cache_dir() -> Path:
    return _subdir("cache")


def user_config_path() -> Path:
    return user_data_dir() / "config.yaml"


def state_db_path() -> Path:
    return user_data_dir() / "state.db"


def user_ioc_path() -> Path:
    """Optional user-maintained local IOC list (same CSV format as the bundled one)."""
    return user_data_dir() / "local_ioc.csv"
