"""Composition root: builds all backend components for a data directory."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import paths
from .apps.registry import AppRegistry
from .assistant import Assistant
from .automation.controller import SystemController, create_controller
from .automation.executor import Executor
from .automation.sysinfo import GpuProbe
from .permissions.manager import PermissionManager
from .storage.db import Database
from .storage.journal import Journal
from .storage.scenarios import ScenarioInput, ScenarioStep, ScenarioStore
from .storage.settings import SettingsStore

log = logging.getLogger(__name__)


def default_scenarios() -> list[ScenarioInput]:
    return [
        ScenarioInput(name="Режим концентрации", aliases=["режим концентрации", "фокус", "концентрация"],
                      steps=[ScenarioStep(action="profile.silent", params={"enabled": True}),
                             ScenarioStep(action="window.minimize_all")]),
        ScenarioInput(name="Рабочий режим", aliases=["рабочий режим", "работа"],
                      steps=[ScenarioStep(action="profile.silent", params={"enabled": False}),
                             ScenarioStep(action="volume.set", params={"level": 40}),
                             ScenarioStep(action="explorer.open", params={"folder": "documents"})]),
    ]


@dataclass
class Services:
    data_dir: Path
    db: Database
    settings: SettingsStore
    registry: AppRegistry
    scenarios: ScenarioStore
    journal: Journal
    permissions: PermissionManager
    controller: SystemController
    executor: Executor
    gpu: GpuProbe
    assistant: Assistant
    folders: Callable[[], dict[str, str]]

    @classmethod
    def create(cls, data_dir: Optional[Path] = None, controller: Optional[SystemController] = None,
               folders: Optional[Callable[[], dict[str, str]]] = None, db_name: str = "arc.db") -> "Services":
        data_dir = data_dir or paths.data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        db = Database(data_dir / db_name)
        first_run = db.query_one("SELECT COUNT(*) AS n FROM settings")["n"] == 0
        if folders is None:
            known = {k: str(v) for k, v in paths.known_folders().items()}
            folders = lambda: known  # noqa: E731
        folder_map = folders

        def default_dirs() -> list[str]:
            return [p for k, p in folder_map().items() if k in ("desktop", "documents", "downloads") and os.path.isdir(p)]

        settings = SettingsStore(db, default_dirs)
        registry = AppRegistry(db)
        scenarios = ScenarioStore(db)
        if first_run:
            registry.seed_builtins()
            for scenario in default_scenarios():
                scenarios.add(scenario)
        journal = Journal(db)
        permissions = PermissionManager(settings.get)
        controller = controller or create_controller()
        gpu = GpuProbe()
        executor = Executor(controller, registry, settings, folder_map, gpu)
        assistant = Assistant(settings=settings, registry=registry, scenarios=scenarios, journal=journal,
                              permissions=permissions, executor=executor, folders=folder_map)
        log.info("services ready: data=%s controller=%s first_run=%s", data_dir, controller.name, first_run)
        return cls(data_dir, db, settings, registry, scenarios, journal, permissions, controller, executor, gpu,
                   assistant, folder_map)

    def close(self) -> None:
        self.assistant.close()
        self.db.close()
