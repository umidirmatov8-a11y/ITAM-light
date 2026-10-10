"""User scenarios ("рабочий режим", "игровой режим"): a named list of catalog actions."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ..permissions.catalog import get_spec
from .db import Database

# Scenario steps may only use these actions (no power / admin / nested scenarios).
SCENARIO_ACTIONS = ("app.launch", "volume.set", "volume.change", "volume.mute", "window.minimize_all",
                    "window.restore_all", "browser.open_url", "explorer.open", "profile.silent", "mode.set")


class ScenarioStep(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def _action(cls, value: str) -> str:
        if value not in SCENARIO_ACTIONS:
            raise ValueError(f"action {value} is not allowed in scenarios")
        return value

    def model_post_init(self, _ctx: Any) -> None:
        spec = get_spec(self.action)
        assert spec is not None
        self.params = spec.params.model_validate(self.params).model_dump()


class ScenarioInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list, max_length=10)
    steps: list[ScenarioStep] = Field(min_length=1, max_length=20)
    enabled: bool = True


class Scenario(ScenarioInput):
    id: str
    created_at: float
    updated_at: float


class ScenarioStore:
    def __init__(self, db: Database):
        self._db = db

    def list(self) -> list[Scenario]:
        return [self._row(r) for r in self._db.query("SELECT * FROM scenarios ORDER BY name COLLATE NOCASE")]

    def get(self, scenario_id: str) -> Scenario | None:
        row = self._db.query_one("SELECT * FROM scenarios WHERE id = ?", (scenario_id,))
        return self._row(row) if row else None

    def add(self, item: ScenarioInput) -> Scenario:
        now = time.time()
        sid = uuid.uuid4().hex[:12]
        self._db.execute("INSERT INTO scenarios(id, name, aliases, steps, enabled, created_at, updated_at)"
                         " VALUES(?,?,?,?,?,?,?)", (sid, item.name, json.dumps(item.aliases, ensure_ascii=False),
                                                   json.dumps([s.model_dump() for s in item.steps], ensure_ascii=False),
                                                   int(item.enabled), now, now))
        result = self.get(sid)
        assert result is not None
        return result

    def update(self, scenario_id: str, item: ScenarioInput) -> Scenario:
        if self.get(scenario_id) is None:
            raise KeyError(scenario_id)
        self._db.execute("UPDATE scenarios SET name=?, aliases=?, steps=?, enabled=?, updated_at=? WHERE id=?",
                         (item.name, json.dumps(item.aliases, ensure_ascii=False),
                          json.dumps([s.model_dump() for s in item.steps], ensure_ascii=False), int(item.enabled),
                          time.time(), scenario_id))
        result = self.get(scenario_id)
        assert result is not None
        return result

    def delete(self, scenario_id: str) -> bool:
        return self._db.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,)).rowcount > 0

    @staticmethod
    def _row(row: Any) -> Scenario:
        data = dict(row)
        data["aliases"] = json.loads(data["aliases"])
        data["steps"] = json.loads(data["steps"])
        data["enabled"] = bool(data["enabled"])
        return Scenario.model_validate(data)
