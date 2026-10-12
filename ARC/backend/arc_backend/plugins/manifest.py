"""Module manifest: a declarative description, never code.

A module can add voice/text phrases that run actions from the A.R.C. catalog. Only category A and
B actions are allowed (critical C actions, mode switching, raw process termination and admin
launch are refused), each action must belong to a module permission the manifest requests, and
parameters are validated with the same typed models the rest of A.R.C. uses."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ..models import Risk
from ..permissions.catalog import CATALOG
from ..router.text import normalize
from ..storage.settings import MODULES

FORBIDDEN_ACTIONS = {"mode.set", "app.launch_admin", "process.terminate", "files.remove_empty_folder"}
FORBIDDEN_MODULES = {"modes", "power"}
REQUESTABLE_MODULES = tuple(m for m in MODULES if m not in FORBIDDEN_MODULES)
MAX_FILE_BYTES = 256 * 1024


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PluginAction(Strict):
    action: str = Field(max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    # For app actions a module names the program ("Telegram"); it is looked up in the user's registry.
    app: Optional[str] = Field(None, min_length=1, max_length=80)


class PluginCommand(Strict):
    phrases: list[str] = Field(min_length=1, max_length=20)
    actions: list[PluginAction] = Field(min_length=1, max_length=5)
    reply: str = Field("", max_length=300)

    @field_validator("phrases")
    @classmethod
    def _phrases(cls, value: list[str]) -> list[str]:
        result = []
        for phrase in value:
            norm = normalize(phrase)
            if not 2 <= len(norm) <= 80:
                raise ValueError("a phrase must be 2–80 characters")
            result.append(norm)
        return result


class PluginManifest(Strict):
    format: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,40}$")
    name: str = Field(min_length=1, max_length=60)
    version: str = Field(pattern=r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")
    author: str = Field("", max_length=80)
    description: str = Field("", max_length=500)
    homepage: str = Field("", max_length=300)
    permissions: list[str] = Field(default_factory=list, max_length=len(REQUESTABLE_MODULES))
    commands: list[PluginCommand] = Field(default_factory=list, max_length=50)

    @field_validator("homepage")
    @classmethod
    def _homepage(cls, value: str) -> str:
        if value and not re.match(r"^https://[^\s\"'<>`]+$", value):
            raise ValueError("homepage must be an https:// address")
        return value

    @field_validator("permissions")
    @classmethod
    def _permissions(cls, value: list[str]) -> list[str]:
        for module in value:
            if module not in REQUESTABLE_MODULES:
                raise ValueError(f"permission «{module}» cannot be requested by a module")
        return sorted(set(value))

    @model_validator(mode="after")
    def _actions(self) -> "PluginManifest":
        for command in self.commands:
            for item in command.actions:
                spec = CATALOG.get(item.action)
                if spec is None:
                    raise ValueError(f"unknown action {item.action}")
                if item.action in FORBIDDEN_ACTIONS or spec.risk == Risk.C:
                    raise ValueError(f"action {item.action} is not available to modules")
                if spec.module not in self.permissions:
                    raise ValueError(f"action {item.action} needs permission «{spec.module}»")
                params = dict(item.params)
                if "app_id" in spec.params.model_fields:
                    if "app_id" in params or not item.app:
                        raise ValueError(f"{item.action}: name the program with \"app\", not app_id")
                    params["app_id"] = "placeholder"
                elif item.app:
                    raise ValueError(f"{item.action} does not take \"app\"")
                try:
                    spec.params.model_validate(params)
                except ValidationError as exc:
                    first = exc.errors()[0]
                    raise ValueError(f"{item.action}: {'.'.join(map(str, first['loc']))} {first['msg']}")
        return self

    def version_tuple(self) -> tuple[int, ...]:
        return tuple(int(x) for x in self.version.split("."))
