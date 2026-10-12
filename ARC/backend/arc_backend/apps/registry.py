"""Local registry of applications and games that A.R.C. is allowed to launch."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ..storage.db import Database

ALLOWED_PROTOCOLS = ("steam", "com.epicgames.launcher", "ms-settings", "uplay", "origin2",
                     "battlenet", "goggalaxy", "tg", "discord", "spotify", "ms-windows-store")
_AUMID = re.compile(r"^[A-Za-z0-9._\-]+![A-Za-z0-9._\-]+$")
_PROTOCOL = re.compile(r"^([a-z][a-z0-9.+\-]*):[^\s\"'<>|^`]*$", re.IGNORECASE)


class LaunchType(str, Enum):
    EXE = "exe"
    LNK = "lnk"
    UWP = "uwp"
    PROTOCOL = "protocol"


class AppKind(str, Enum):
    APP = "app"
    GAME = "game"
    SYSTEM = "system"


class AppInput(BaseModel):
    """Fields a user (or discovery) may set."""

    name: str = Field(min_length=1, max_length=120)
    kind: AppKind = AppKind.APP
    category: str = Field("", max_length=60)
    launch_type: LaunchType
    target: str = Field(min_length=1, max_length=1024)
    args: list[str] = Field(default_factory=list, max_length=32)
    working_dir: str = Field("", max_length=1024)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    process_name: str = Field("", max_length=120)
    source: str = Field("manual", max_length=30)
    run_as_admin: bool = False
    enabled: bool = True
    pinned: bool = False

    @field_validator("name", "category")
    @classmethod
    def _strip(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("args")
    @classmethod
    def _args(cls, value: list[str]) -> list[str]:
        for arg in value:
            if "\x00" in arg or len(arg) > 1024:
                raise ValueError("invalid argument")
        return value

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, value: list[str]) -> list[str]:
        cleaned = []
        for alias in value:
            alias = " ".join(alias.split())
            if alias and len(alias) <= 80 and alias.lower() not in (a.lower() for a in cleaned):
                cleaned.append(alias)
        return cleaned

    @field_validator("process_name")
    @classmethod
    def _process(cls, value: str) -> str:
        if value and (os.sep in value or "/" in value or "\\" in value):
            raise ValueError("process_name must be a file name like app.exe")
        return value

    @model_validator(mode="after")
    def _target(self) -> "AppInput":
        target = self.target.strip()
        if "\x00" in target:
            raise ValueError("invalid target")
        if self.launch_type in (LaunchType.EXE, LaunchType.LNK):
            if not _is_absolute_windows_or_posix(target):
                raise ValueError("target must be an absolute path")
            ext = ".exe" if self.launch_type == LaunchType.EXE else ".lnk"
            if not target.lower().endswith(ext):
                raise ValueError(f"target must end with {ext}")
            if self.launch_type == LaunchType.EXE and not self.process_name:
                self.process_name = re.split(r"[\\/]", target)[-1]
        elif self.launch_type == LaunchType.UWP:
            if not _AUMID.match(target):
                raise ValueError("target must be an AppUserModelID like Publisher.App_hash!App")
        elif self.launch_type == LaunchType.PROTOCOL:
            match = _PROTOCOL.match(target)
            if not match or match.group(1).lower() not in ALLOWED_PROTOCOLS:
                raise ValueError("protocol is not in the allowed list: " + ", ".join(ALLOWED_PROTOCOLS))
        if self.run_as_admin and self.launch_type != LaunchType.EXE:
            raise ValueError("run_as_admin is supported only for exe targets")
        self.target = target
        return self


class AppEntry(AppInput):
    id: str
    created_at: float
    updated_at: float
    last_launched: Optional[float] = None


def _is_absolute_windows_or_posix(path: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", path)) or path.startswith("\\\\") or path.startswith("/")


def builtin_apps() -> list[AppInput]:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    sys32 = root + r"\System32"
    return [
        AppInput(name="Проводник", kind=AppKind.SYSTEM, category="Система", launch_type=LaunchType.EXE,
                 target=root + r"\explorer.exe", aliases=["проводник", "explorer", "мой компьютер"],
                 source="builtin"),
        AppInput(name="Диспетчер задач", kind=AppKind.SYSTEM, category="Система", launch_type=LaunchType.EXE,
                 target=sys32 + r"\Taskmgr.exe", aliases=["диспетчер задач", "task manager"], source="builtin"),
        AppInput(name="Блокнот", kind=AppKind.SYSTEM, category="Система", launch_type=LaunchType.EXE,
                 target=sys32 + r"\notepad.exe", aliases=["блокнот", "notepad"], source="builtin"),
        AppInput(name="Калькулятор", kind=AppKind.SYSTEM, category="Система", launch_type=LaunchType.EXE,
                 target=sys32 + r"\calc.exe", aliases=["калькулятор", "calculator"], process_name="CalculatorApp.exe",
                 source="builtin"),
        AppInput(name="Параметры Windows", kind=AppKind.SYSTEM, category="Система",
                 launch_type=LaunchType.PROTOCOL, target="ms-settings:",
                 aliases=["параметры", "настройки windows", "параметры windows"], process_name="SystemSettings.exe",
                 source="builtin"),
        AppInput(name="Панель управления", kind=AppKind.SYSTEM, category="Система", launch_type=LaunchType.EXE,
                 target=sys32 + r"\control.exe", aliases=["панель управления", "control panel"], source="builtin"),
    ]


class AppRegistry:
    def __init__(self, db: Database):
        self._db = db

    def seed_builtins(self) -> int:
        added = 0
        for item in builtin_apps():
            if self.find_by_target(item.launch_type, item.target) is None:
                self.add(item)
                added += 1
        return added

    def list(self, include_disabled: bool = True) -> list[AppEntry]:
        sql = "SELECT * FROM apps" + ("" if include_disabled else " WHERE enabled = 1")
        rows = self._db.query(sql + " ORDER BY pinned DESC, kind, name COLLATE NOCASE")
        return [self._row(row) for row in rows]

    def get(self, app_id: str) -> AppEntry | None:
        row = self._db.query_one("SELECT * FROM apps WHERE id = ?", (app_id,))
        return self._row(row) if row else None

    def find_by_target(self, launch_type: LaunchType, target: str) -> AppEntry | None:
        row = self._db.query_one("SELECT * FROM apps WHERE launch_type = ? AND lower(target) = lower(?)",
                                 (launch_type.value, target))
        return self._row(row) if row else None

    def add(self, item: AppInput) -> AppEntry:
        if self.find_by_target(item.launch_type, item.target):
            raise ValueError("Такое приложение уже есть в реестре")
        now = time.time()
        app_id = uuid.uuid4().hex[:12]
        data = item.model_dump(mode="json")
        self._db.execute(
            "INSERT INTO apps(id, name, kind, category, launch_type, target, args, working_dir, aliases,"
            " process_name, source, run_as_admin, enabled, pinned, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (app_id, data["name"], data["kind"], data["category"], data["launch_type"], data["target"],
             json.dumps(data["args"], ensure_ascii=False), data["working_dir"],
             json.dumps(data["aliases"], ensure_ascii=False), data["process_name"], data["source"],
             int(data["run_as_admin"]), int(data["enabled"]), int(data["pinned"]), now, now),
        )
        entry = self.get(app_id)
        assert entry is not None
        return entry

    def update(self, app_id: str, patch: dict[str, Any]) -> AppEntry:
        current = self.get(app_id)
        if current is None:
            raise KeyError(app_id)
        merged = current.model_dump(mode="json", exclude={"id", "created_at", "updated_at", "last_launched"})
        unknown = set(patch) - set(merged)
        if unknown:
            raise ValueError("unknown fields: " + ", ".join(sorted(unknown)))
        merged.update(patch)
        item = AppInput.model_validate(merged)
        other = self.find_by_target(item.launch_type, item.target)
        if other and other.id != app_id:
            raise ValueError("Такое приложение уже есть в реестре")
        data = item.model_dump(mode="json")
        self._db.execute(
            "UPDATE apps SET name=?, kind=?, category=?, launch_type=?, target=?, args=?, working_dir=?,"
            " aliases=?, process_name=?, source=?, run_as_admin=?, enabled=?, pinned=?, updated_at=? WHERE id=?",
            (data["name"], data["kind"], data["category"], data["launch_type"], data["target"],
             json.dumps(data["args"], ensure_ascii=False), data["working_dir"],
             json.dumps(data["aliases"], ensure_ascii=False), data["process_name"], data["source"],
             int(data["run_as_admin"]), int(data["enabled"]), int(data["pinned"]), time.time(), app_id),
        )
        entry = self.get(app_id)
        assert entry is not None
        return entry

    def delete(self, app_id: str) -> bool:
        """Removes the entry from A.R.C. only; the program itself is untouched."""
        return self._db.execute("DELETE FROM apps WHERE id = ?", (app_id,)).rowcount > 0

    def mark_launched(self, app_id: str) -> None:
        self._db.execute("UPDATE apps SET last_launched = ? WHERE id = ?", (time.time(), app_id))

    @staticmethod
    def _row(row: Any) -> AppEntry:
        data = dict(row)
        data["args"] = json.loads(data["args"])
        data["aliases"] = json.loads(data["aliases"])
        for key in ("run_as_admin", "enabled", "pinned"):
            data[key] = bool(data[key])
        return AppEntry.model_validate(data)
