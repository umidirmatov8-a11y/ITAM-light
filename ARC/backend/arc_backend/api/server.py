"""Local HTTP API (loopback only). The only client is the Electron main process."""
from __future__ import annotations

import hmac
import os
import platform
import sys
import time
from typing import Any, Callable, Literal, Optional

from fastapi import Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.types import ASGIApp, Receive, Scope, Send

from .. import __version__
from ..ai.ollama import check_ollama
from ..apps.discovery import discover_all, import_discovered
from ..apps.registry import AppInput, LaunchType
from ..automation import sysinfo
from ..models import ActionRequest, Source
from ..permissions.catalog import catalog_view
from ..services import Services
from ..storage.scenarios import SCENARIO_ACTIONS, ScenarioInput
from ..storage.settings import NetworkMode
from ..voice.engine import VoiceError, stt_device_info
from ..voice.models import DownloadError

TOKEN_HEADER = "x-arc-token"


class LocalOnlyMiddleware:
    """Rejects anything that is not the Electron main process:
    wrong/missing token, browser requests (Origin / Sec-Fetch-*), foreign Host headers (DNS rebinding),
    and non-JSON bodies (form-based CSRF)."""

    def __init__(self, app: ASGIApp, token: str, allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")):
        self.app = app
        self.token = token.encode()
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        reason = self._reject_reason(scope, headers)
        if reason:
            response = JSONResponse({"error": "forbidden", "detail": reason}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _reject_reason(self, scope: Scope, headers: dict[str, str]) -> Optional[str]:
        client = scope.get("client")
        if client and client[0] not in ("127.0.0.1", "::1", "testclient"):
            return "non-loopback client"
        host = headers.get("host", "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in self.allowed_hosts:
            return "host not allowed"
        if "origin" in headers or any(k.startswith("sec-fetch-") for k in headers):
            return "browser requests are not accepted"
        supplied = headers.get(TOKEN_HEADER, "").encode()
        if not supplied or not hmac.compare_digest(supplied, self.token):
            return "invalid token"
        if scope["method"] in ("POST", "PUT", "PATCH", "DELETE"):
            ctype = headers.get("content-type", "")
            length = headers.get("content-length", "0")
            if length not in ("", "0") and not ctype.startswith("application/json"):
                return "content-type must be application/json"
        return None


class CommandBody(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    source: Literal["text", "voice"] = "text"
    confidence: float = Field(1.0, ge=0, le=1)


class ConfirmBody(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    approve: bool
    acknowledge: bool = False


class EmergencyBody(BaseModel):
    engaged: bool


class PttBody(BaseModel):
    action: Literal["start", "stop", "toggle"]


class ListenBody(BaseModel):
    enabled: bool


class ModelBody(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9\-]+$")
    confirm: bool = False


class AppCreateBody(AppInput):
    confirm_untrusted: bool = False


def trusted_location(path: str) -> bool:
    """Programs installed into standard locations are considered known sources."""
    path = os.path.normcase(os.path.abspath(path))
    roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "SystemRoot")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(os.path.join(local, "Programs"))
        roots.append(os.path.join(local, "Microsoft", "WindowsApps"))
    for root in filter(None, roots):
        root = os.path.normcase(os.path.abspath(root))
        if path.startswith(root.rstrip("\\/") + os.sep):
            return True
    return False


def create_app(services: Services, token: str, *, on_shutdown: Optional[Callable[[], None]] = None,
               allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")) -> FastAPI:
    app = FastAPI(title="A.R.C. backend", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(LocalOnlyMiddleware, token=token, allowed_hosts=allowed_hosts)
    s = services
    started = time.time()
    ai_cache: dict[str, Any] = {"ts": 0.0, "value": None}

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
        if isinstance(exc, ValidationError):
            first = exc.errors()[0]
            detail = f"{'.'.join(map(str, first['loc']))}: {first['msg']}"
        else:
            detail = str(exc)
        return JSONResponse({"error": "invalid", "detail": detail}, status_code=400)

    @app.exception_handler(KeyError)
    async def _key_error(_request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse({"error": "not_found", "detail": str(exc)}, status_code=404)

    def ai_status(force: bool = False) -> dict[str, Any]:
        settings = s.settings.get()
        if not settings.devices.local_ai_enabled:
            return {"state": "disabled", "message": "Локальный ИИ отключён в настройках", "model": settings.ai.model,
                    "url": settings.ai.ollama_url, "models": []}
        if not force and time.time() - ai_cache["ts"] < 10 and ai_cache["value"]:
            return ai_cache["value"]
        value = check_ollama(settings.ai.ollama_url, settings.ai.model,
                             allow_remote=settings.network.mode == NetworkMode.ONLINE)
        ai_cache.update(ts=time.time(), value=value)
        return value

    # ------------------------------------------------------------------ core
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "pid": os.getpid(), "platform": sys.platform,
                "controller": s.controller.name, "simulated": s.controller.simulated,
                "uptime_s": round(time.time() - started, 1)}

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        settings = s.settings.get()
        return {**s.assistant.state(), "mode": settings.network.mode.value,
                "online_allowed": settings.network.online_allowed, "devices": settings.devices.model_dump(),
                "silent": settings.profile.silent, "dry_run": settings.safety.dry_run,
                "simulated": s.controller.simulated,
                "voice": {k: v for k, v in s.voice.status().items() if k in ("state", "message", "ptt", "continuous")},
                "camera": {"state": "not_installed", "message": "Модуль жестов подключается на этапе 3"}}

    @app.post("/api/command")
    def command(body: CommandBody) -> dict[str, Any]:
        response = s.assistant.handle_text(body.text, Source(body.source), body.confidence)
        return response.model_dump(mode="json")

    @app.post("/api/confirm")
    def confirm(body: ConfirmBody) -> dict[str, Any]:
        return s.assistant.confirm(body.id, body.approve, Source.UI, body.acknowledge).model_dump(mode="json")

    @app.post("/api/undo")
    def undo() -> dict[str, Any]:
        return s.assistant.undo_last(Source.UI).model_dump(mode="json")

    @app.post("/api/repeat")
    def repeat() -> dict[str, Any]:
        return s.assistant.repeat_last(Source.UI).model_dump(mode="json")

    @app.post("/api/emergency-stop")
    def emergency(body: EmergencyBody) -> dict[str, Any]:
        return s.assistant.emergency_stop(body.engaged).model_dump(mode="json")

    @app.get("/api/actions")
    def actions() -> list[dict[str, Any]]:
        return catalog_view()

    # ------------------------------------------------------------------ settings
    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return s.settings.get().model_dump(mode="json")

    @app.put("/api/settings")
    def put_settings(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
        updated = s.settings.update(patch)
        if not updated.devices.microphone_enabled:
            s.voice.stop_all()
        if "ai" in patch or "devices" in patch or "network" in patch:
            ai_cache["ts"] = 0.0
        s.journal.audit(action="settings.update", params={"sections": sorted(patch)}, risk="-", source="ui",
                        decision="allow", status="done", message="Настройки изменены")
        return updated.model_dump(mode="json")

    @app.get("/api/folders")
    def folders() -> dict[str, Any]:
        return {"known": s.folders(), "allowed": s.settings.get().safety.allowed_dirs}

    # ------------------------------------------------------------------ apps
    @app.get("/api/apps")
    def list_apps() -> list[dict[str, Any]]:
        return [a.model_dump(mode="json") for a in s.registry.list()]

    @app.post("/api/apps")
    def add_app(body: AppCreateBody) -> dict[str, Any]:
        item = AppInput.model_validate(body.model_dump(exclude={"confirm_untrusted"}))
        if item.launch_type in (LaunchType.EXE, LaunchType.LNK):
            if not s.controller.path_exists(item.target):
                raise ValueError("Файл не найден: " + item.target)
            if item.launch_type == LaunchType.EXE and not trusted_location(item.target) and not body.confirm_untrusted:
                return JSONResponse({"error": "untrusted_location",
                                     "detail": "Файл находится вне стандартных каталогов программ. "
                                               "Убедитесь, что он из надёжного источника, и подтвердите добавление."},
                                    status_code=409)  # type: ignore[return-value]
        entry = s.registry.add(item)
        s.journal.audit(action="registry.add", params={"name": entry.name, "target": entry.target}, risk="-",
                        source="ui", decision="allow", status="done", message=f"Добавлено «{entry.name}»")
        return entry.model_dump(mode="json")

    @app.put("/api/apps/{app_id}")
    def update_app(app_id: str, patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
        entry = s.registry.update(app_id, patch)
        return entry.model_dump(mode="json")

    @app.delete("/api/apps/{app_id}")
    def delete_app(app_id: str) -> dict[str, Any]:
        entry = s.registry.get(app_id)
        if not entry or not s.registry.delete(app_id):
            raise KeyError(app_id)
        s.journal.audit(action="registry.remove", params={"name": entry.name}, risk="-", source="ui",
                        decision="allow", status="done", message=f"Удалено из реестра «{entry.name}»")
        return {"deleted": app_id}

    @app.post("/api/apps/{app_id}/launch")
    def launch_app(app_id: str) -> dict[str, Any]:
        entry = s.registry.get(app_id)
        if entry is None:
            raise KeyError(app_id)
        action = "app.launch_admin" if entry.run_as_admin else "app.launch"
        request = ActionRequest(action=action, params={"app_id": app_id}, source=Source.UI)
        return s.assistant.run_action(request, {app_id: entry.name}).model_dump(mode="json")

    @app.post("/api/apps/discover")
    def discover() -> dict[str, Any]:
        report = import_discovered(s.registry, discover_all())
        s.journal.audit(action="registry.discover", params=report.by_source, risk="-", source="ui", decision="allow",
                        status="done", message=f"Найдено новых записей: {len(report.added)}")
        return report.__dict__

    # ------------------------------------------------------------------ scenarios
    @app.get("/api/scenarios")
    def list_scenarios() -> dict[str, Any]:
        return {"scenarios": [x.model_dump(mode="json") for x in s.scenarios.list()],
                "allowed_actions": list(SCENARIO_ACTIONS)}

    @app.post("/api/scenarios")
    def add_scenario(body: ScenarioInput) -> dict[str, Any]:
        return s.scenarios.add(body).model_dump(mode="json")

    @app.put("/api/scenarios/{scenario_id}")
    def update_scenario(scenario_id: str, body: ScenarioInput) -> dict[str, Any]:
        return s.scenarios.update(scenario_id, body).model_dump(mode="json")

    @app.delete("/api/scenarios/{scenario_id}")
    def delete_scenario(scenario_id: str) -> dict[str, Any]:
        if not s.scenarios.delete(scenario_id):
            raise KeyError(scenario_id)
        return {"deleted": scenario_id}

    @app.post("/api/scenarios/{scenario_id}/run")
    def run_scenario(scenario_id: str) -> dict[str, Any]:
        scenario = s.scenarios.get(scenario_id)
        if scenario is None:
            raise KeyError(scenario_id)
        request = ActionRequest(action="scenario.run", params={"scenario_id": scenario_id}, source=Source.UI)
        return s.assistant.run_action(request, {scenario_id: scenario.name}).model_dump(mode="json")

    # ------------------------------------------------------------------ journal
    @app.get("/api/history")
    def history(limit: int = Query(50, ge=1, le=1000)) -> list[dict[str, Any]]:
        return s.journal.history(limit)

    @app.delete("/api/history")
    def clear_history() -> dict[str, Any]:
        return {"deleted": s.journal.clear_history()}

    @app.get("/api/audit")
    def audit(limit: int = Query(100, ge=1, le=5000)) -> list[dict[str, Any]]:
        return s.journal.audit_entries(limit)

    @app.delete("/api/audit")
    def clear_audit() -> dict[str, Any]:
        deleted = s.journal.clear_audit()
        s.journal.audit(action="audit.clear", params={"deleted": deleted}, risk="-", source="ui", decision="allow",
                        status="done", message="Журнал очищен")
        return {"deleted": deleted}

    @app.get("/api/audit/export")
    def export_audit(format: Literal["json", "csv"] = "json") -> dict[str, Any]:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        return {"filename": f"arc-log-{stamp}.{format}", "content": s.journal.export(format)}

    # ------------------------------------------------------------------ system / diagnostics
    @app.get("/api/system/stats")
    def system_stats() -> dict[str, Any]:
        return sysinfo.stats(s.gpu)

    @app.get("/api/ai/status")
    def ai(force: bool = False) -> dict[str, Any]:
        return ai_status(force)

    @app.get("/api/diagnostics")
    def diagnostics() -> dict[str, Any]:
        settings = s.settings.get()
        checks = []

        def add(name: str, state: str, detail: str) -> None:
            checks.append({"name": name, "state": state, "detail": detail})

        add("Backend", "ok", f"A.R.C. {__version__}, Python {platform.python_version()}, {platform.platform()}")
        add("База данных", "ok", f"{s.db.path} (схема v{s.db.schema_version})")
        add("Автоматизация", "warn" if s.controller.simulated else "ok",
            "Режим имитации: системные действия не выполняются" if s.controller.simulated
            else "Windows API доступны")
        try:
            import pycaw  # type: ignore
            assert pycaw
            add("Громкость", "ok", "pycaw: точная установка громкости")
        except ImportError:
            add("Громкость", "warn", "pycaw не установлен: громкость меняется медиаклавишами (шаг 2%)")
        missing = [d for d in settings.safety.allowed_dirs if not os.path.isdir(d)]
        add("Разрешённые каталоги", "warn" if missing or not settings.safety.allowed_dirs else "ok",
            f"{len(settings.safety.allowed_dirs)} каталогов" + (f", недоступны: {', '.join(missing)}" if missing else ""))
        add("Тестовый режим", "warn" if settings.safety.dry_run else "ok",
            "Операции категорий B/C имитируются" if settings.safety.dry_run else "Операции B/C выполняются после подтверждения")
        ai_state = ai_status(force=True)
        add("Локальный ИИ (Ollama)", "ok" if ai_state["state"] == "ready" else "warn", ai_state.get("message", ""))
        add("GPU", "ok" if s.gpu.available else "warn",
            "nvidia-smi найден" if s.gpu.available else "nvidia-smi не найден: метрики GPU недоступны, ИИ будет на CPU")
        mics = s.voice.devices()
        add("Микрофон", "ok" if mics else "warn",
            ", ".join(d["name"] for d in mics[:3]) if mics else "Устройства записи не найдены: работают текстовые команды")
        stt_id = settings.voice.stt_model
        add("Распознавание речи", "ok" if s.models.installed(stt_id) else "warn",
            f"{stt_id}: {'установлена' if s.models.installed(stt_id) else 'не установлена (Настройки → Голос)'}; "
            f"ускорение: {'CUDA доступна' if stt_device_info()['cuda'] else 'CPU (CUDA не найдена)'}")
        voice_status = s.voice.status()
        add("Синтез речи", "warn" if voice_status["tts"]["warning"] else "ok",
            voice_status["tts"]["warning"] or f"Движок: {settings.voice.tts_engine}")
        add("Камера / жесты", "info", "Модуль жестов подключается на этапе 3")
        add("Сеть", "ok", f"Режим {settings.network.mode.value}; онлайн-функции "
                          f"{'разрешены' if settings.network.online_allowed else 'выключены'}")
        add("Приложения", "ok", f"В реестре: {len(s.registry.list())}")
        return {"checks": checks, "data_dir": str(s.data_dir), "ts": time.time()}

    # ------------------------------------------------------------------ voice
    def voice_call(fn):
        try:
            return fn()
        except VoiceError as exc:
            return JSONResponse({"error": "voice_unavailable", "detail": str(exc)}, status_code=409)

    @app.get("/api/voice/status")
    def voice_status() -> dict[str, Any]:
        return s.voice.status()

    @app.post("/api/voice/ptt")
    def voice_ptt(body: PttBody) -> dict[str, Any]:
        action = {"start": s.voice.start_ptt, "stop": s.voice.stop_ptt, "toggle": s.voice.toggle_ptt}[body.action]
        return voice_call(action)

    @app.post("/api/voice/listen")
    def voice_listen(body: ListenBody) -> dict[str, Any]:
        return voice_call(lambda: s.voice.set_continuous(body.enabled))

    @app.post("/api/voice/tts-test")
    def voice_tts_test() -> dict[str, Any]:
        spoken = s.voice.speak("Проверка голоса. A.R.C. на связи.", force=True)
        status = s.voice.status()
        return {"spoken": spoken, "warning": status["tts"]["warning"]}

    @app.get("/api/voice/devices")
    def voice_devices() -> dict[str, Any]:
        voices: list[dict] = []
        try:
            voices = s.voice._synthesizer().voices()
        except Exception as exc:  # SAPI/COM problems should not break the settings screen
            voices = [{"name": f"недоступно: {exc}", "language": "", "russian": False}]
        return {"inputs": s.voice.devices(), "voices": voices, **stt_device_info()}

    @app.get("/api/voice/models")
    def voice_models() -> dict[str, Any]:
        return {"models": s.models.list(), "free_mb": round(s.models.free_mb()), "dir": str(s.models.models_dir)}

    @app.post("/api/voice/models/download")
    def voice_model_download(body: ModelBody) -> dict[str, Any]:
        if not body.confirm:
            raise ValueError("Загрузка требует подтверждения пользователя")
        try:
            job = s.models.start_download(body.id, online_allowed=s.settings.get().network.online_allowed)
        except DownloadError as exc:
            raise ValueError(str(exc))
        s.journal.audit(action="voice.model_download", params={"id": body.id}, risk="-", source="ui",
                        decision="allow", status="started", message=f"Загрузка модели {body.id}")
        return job.view()

    @app.post("/api/voice/models/cancel")
    def voice_model_cancel(body: ModelBody) -> dict[str, Any]:
        return {"cancelled": s.models.cancel(body.id)}

    @app.delete("/api/voice/models/{model_id}")
    def voice_model_delete(model_id: str) -> dict[str, Any]:
        try:
            removed = s.models.remove(model_id)
        except DownloadError as exc:
            raise ValueError(str(exc))
        return {"removed": removed}

    @app.post("/api/shutdown")
    def shutdown() -> dict[str, Any]:
        if on_shutdown:
            on_shutdown()
        return {"ok": True}

    return app
