"""Catalog of the only operations A.R.C. can perform. Every action has a risk category,
an owning module (can be switched off) and a typed parameter model."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import Risk


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoParams(Params):
    pass


class AppParams(Params):
    app_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")


class ProcessParams(Params):
    pid: int = Field(gt=4)
    name: str = Field("", max_length=260)


class VolumeChangeParams(Params):
    delta: int = Field(ge=-100, le=100)


class VolumeSetParams(Params):
    level: int = Field(ge=0, le=100)


class MuteParams(Params):
    muted: bool


class SystemInfoParams(Params):
    topic: Literal["time", "date", "disk", "memory", "cpu", "processes", "stats", "gpu"]


class FileSearchParams(Params):
    query: str = Field(min_length=1, max_length=200)
    scope: Optional[str] = Field(None, max_length=1024)


class FileOpenParams(Params):
    path: str = Field(min_length=1, max_length=1024)


class CreateFolderParams(Params):
    name: str = Field(min_length=1, max_length=120)
    parent: str = Field("desktop", min_length=1, max_length=1024)


class ExplorerParams(Params):
    folder: Optional[str] = Field(None, max_length=1024)


_URL = re.compile(r"^https?://[^\s\"'<>`^|{}\\]+$", re.IGNORECASE)


class UrlParams(Params):
    url: str = Field(max_length=2048)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        if not _URL.match(value):
            raise ValueError("only http(s) URLs are allowed")
        return value


class QueryParams(Params):
    query: str = Field(min_length=1, max_length=300)


class PowerParams(Params):
    delay_s: int = Field(60, ge=0, le=3600)


class ModeParams(Params):
    mode: Literal["LOCAL", "ONLINE"]


class SilentParams(Params):
    enabled: bool


class ScenarioParams(Params):
    scenario_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")


@dataclass(frozen=True)
class ActionSpec:
    name: str
    title: str
    module: str
    risk: Risk
    params: Type[Params]
    gesture_allowed: bool = False
    requires_online: bool = False


CATALOG: dict[str, ActionSpec] = {spec.name: spec for spec in [
    ActionSpec("app.launch", "Запуск приложения", "apps", Risk.A, AppParams, gesture_allowed=True),
    ActionSpec("app.launch_admin", "Запуск от имени администратора", "apps", Risk.C, AppParams),
    ActionSpec("app.close", "Закрытие приложения", "processes", Risk.B, AppParams),
    ActionSpec("process.terminate", "Завершение процесса", "processes", Risk.B, ProcessParams),
    ActionSpec("volume.change", "Изменение громкости", "volume", Risk.A, VolumeChangeParams, gesture_allowed=True),
    ActionSpec("volume.set", "Установка громкости", "volume", Risk.A, VolumeSetParams, gesture_allowed=True),
    ActionSpec("volume.mute", "Звук вкл/выкл", "volume", Risk.A, MuteParams, gesture_allowed=True),
    ActionSpec("window.minimize_all", "Свернуть все окна", "windows", Risk.A, NoParams, gesture_allowed=True),
    ActionSpec("window.restore_all", "Вернуть окна", "windows", Risk.A, NoParams, gesture_allowed=True),
    ActionSpec("system.info", "Системная информация", "system_info", Risk.A, SystemInfoParams, gesture_allowed=True),
    ActionSpec("files.search", "Поиск файлов", "files", Risk.A, FileSearchParams),
    ActionSpec("files.open", "Открытие файла", "files", Risk.A, FileOpenParams),
    ActionSpec("files.create_folder", "Создание папки", "files", Risk.B, CreateFolderParams),
    ActionSpec("files.remove_empty_folder", "Удаление пустой папки", "files", Risk.B, FileOpenParams),
    ActionSpec("explorer.open", "Открыть проводник", "files", Risk.A, ExplorerParams, gesture_allowed=True),
    ActionSpec("browser.open_url", "Открыть сайт", "browser", Risk.A, UrlParams),
    ActionSpec("web.search", "Поиск в интернете", "web_search", Risk.A, QueryParams, requires_online=True),
    ActionSpec("power.shutdown", "Выключение компьютера", "power", Risk.C, PowerParams),
    ActionSpec("power.restart", "Перезагрузка компьютера", "power", Risk.C, PowerParams),
    ActionSpec("power.abort", "Отмена выключения", "power", Risk.A, NoParams),
    ActionSpec("mode.set", "Режим LOCAL/ONLINE", "modes", Risk.A, ModeParams),
    ActionSpec("profile.silent", "Режим тишины", "modes", Risk.A, SilentParams, gesture_allowed=True),
    ActionSpec("scenario.run", "Запуск сценария", "scenarios", Risk.A, ScenarioParams, gesture_allowed=True),
]}


def get_spec(action: str) -> Optional[ActionSpec]:
    return CATALOG.get(action)


def catalog_view() -> list[dict]:
    return [{"name": s.name, "title": s.title, "module": s.module, "risk": s.risk.value,
             "gesture_allowed": s.gesture_allowed, "requires_online": s.requires_online,
             "params": list(s.params.model_fields)} for s in CATALOG.values()]
