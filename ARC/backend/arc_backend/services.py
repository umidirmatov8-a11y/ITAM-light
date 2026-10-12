"""Composition root: builds all backend components for a data directory."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from . import paths
from .ai.planner import LocalPlanner
from .apps.registry import AppRegistry
from .assistant import Assistant
from .automation.controller import SystemController, create_controller
from .automation.executor import Executor
from .automation.sysinfo import GpuProbe
from .documents.engine import DocJob, DocumentEngine
from .models import ActionRequest, Source
from .online.client import OnlineClient
from .online.research import ResearchEngine
from .online.secrets import SecretStore, create_secret_store
from .permissions.manager import PermissionManager
from .plugins.manager import PluginManager
from .storage.db import Database
from .storage.journal import Journal
from .storage.scenarios import ScenarioInput, ScenarioStep, ScenarioStore
from .storage.settings import GestureBinding, SettingsStore
from .vision.engine import VisionEngine
from .vision.gestures import GESTURE_TITLES
from .voice.engine import VoiceEngine
from .voice.models import ModelManager

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
    models: ModelManager
    voice: VoiceEngine
    vision: VisionEngine
    secrets: SecretStore
    online: OnlineClient
    research: ResearchEngine
    documents: DocumentEngine
    plugins: PluginManager

    @classmethod
    def create(cls, data_dir: Optional[Path] = None, controller: Optional[SystemController] = None,
               folders: Optional[Callable[[], dict[str, str]]] = None, db_name: str = "arc.db",
               voice_options: Optional[dict[str, Any]] = None, models_dir: Optional[Path] = None,
               vision_options: Optional[dict[str, Any]] = None,
               planner: Optional[LocalPlanner] = None, online_transport: Optional[httpx.BaseTransport] = None,
               ai_transport: Optional[httpx.BaseTransport] = None,
               secrets: Optional[SecretStore] = None) -> "Services":
        """`voice_options` are passed to VoiceEngine (tests inject fake audio/recognizer/synthesizer);
        `online_transport` / `ai_transport` replace the network for the online and document modules in tests."""
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
        secrets = secrets or create_secret_store()
        online = OnlineClient(settings.get, journal, transport=online_transport)
        research = ResearchEngine(online, settings.get, secrets, ai_transport=ai_transport)
        voice_ref: list[VoiceEngine] = []

        def document_finished(job: DocJob) -> None:
            status = {"done": "done", "cancelled": "cancelled"}.get(job.status, "error")
            journal.add_history(source="documents", input=f"документ: {job.topic}", intent="documents.finished",
                                action="documents.create", status=status, message=job.message)
            journal.audit(action="documents.write", params={"kind": job.kind, "path": job.path, "job": job.id},
                          risk="B", source=job.source, decision="allow", status=status, message=job.message)
            if job.source == Source.VOICE.value and voice_ref:
                voice_ref[0].speak(job.message)

        documents = DocumentEngine(settings.get, folder_map, research, on_finished=document_finished,
                                   opener=controller.shell_open, emergency=lambda: permissions.emergency_stop,
                                   ai_transport=ai_transport)
        executor = Executor(controller, registry, settings, folder_map, gpu, research=research, documents=documents)
        plugins = PluginManager(data_dir / "plugins", settings, registry)
        assistant = Assistant(settings=settings, registry=registry, scenarios=scenarios, journal=journal,
                              permissions=permissions, executor=executor, folders=folder_map,
                              planner=planner or LocalPlanner(), plugins=plugins)
        models = ModelManager(models_dir or data_dir / "models")

        def hints() -> list[str]:
            names = [a.name for a in registry.list(include_disabled=False)]
            names += [sc.name for sc in scenarios.list()]
            return names[:40]

        def on_utterance(text: str, confidence: float, explicit: bool):
            return assistant.handle_text(text, Source.VOICE, confidence, explicit=explicit)

        voice = VoiceEngine(settings, models, on_utterance, hints=hints, **(voice_options or {}))
        voice_ref.append(voice)

        def on_gesture(gesture: str, binding: GestureBinding) -> dict:
            label = f"жест: {GESTURE_TITLES.get(gesture, gesture)}"
            if binding.action == "gestures.cancel":
                response = assistant.cancel_current(Source.GESTURE, label)
            elif binding.action == "assistant.repeat":
                response = assistant.repeat_from(Source.GESTURE, label)
            elif binding.action == "ui.toggle_compact":
                return {"status": "done", "message": "Переключение вида интерфейса", "ui": "toggle_compact"}
            elif binding.action == "profile.silent_toggle":
                enabled = not settings.get().profile.silent
                response = assistant.run_action(ActionRequest(action="profile.silent", params={"enabled": enabled},
                                                              source=Source.GESTURE), input_text=label)
            else:
                response = assistant.run_action(ActionRequest(action=binding.action, params=binding.params,
                                                              source=Source.GESTURE), input_text=label)
            return {"status": response.status.value, "message": response.message}

        vision = VisionEngine(settings, models, on_gesture, **(vision_options or {}))
        log.info("services ready: data=%s controller=%s first_run=%s", data_dir, controller.name, first_run)
        return cls(data_dir, db, settings, registry, scenarios, journal, permissions, controller, executor, gpu,
                   assistant, folder_map, models, voice, vision, secrets, online, research, documents, plugins)

    def close(self) -> None:
        self.documents.shutdown()
        self.vision.shutdown()
        self.voice.shutdown()
        self.assistant.close()
        self.db.close()
