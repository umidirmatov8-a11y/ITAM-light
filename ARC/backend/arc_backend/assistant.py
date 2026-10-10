"""Assistant: orchestrates Router → Permission Manager → Executor and keeps dialog state,
undo stack, the last repeatable command, history and the audit log."""
from __future__ import annotations

import concurrent.futures
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .apps.registry import AppRegistry
from .automation.executor import Executor
from .models import ActionRequest, ActionResult, ClarifyInfo, CommandResponse, Risk, Source, Status
from .permissions.catalog import ActionSpec, Params
from .permissions.manager import ConfirmationError, PermissionManager
from .router.router import CommandRouter, DialogState, Plan, RouterContext
from .storage.journal import Journal
from .storage.scenarios import ScenarioStore
from .storage.settings import SettingsStore

log = logging.getLogger(__name__)

HELP_TEXT = ("Примеры команд: «открой Telegram», «запусти игру», «увеличь громкость на 20 процентов», "
             "«выключи звук», «сверни все окна», «открой проводник», «найди файл отчёт на рабочем столе», "
             "«какие программы запущены», «сколько свободного места на диске», «создай папку Проект», "
             "«переключись в онлайн-режим», «режим тишины», «повтори», «отмени».")


@dataclass
class UndoEntry:
    request: ActionRequest
    title: str
    ts: float


class Assistant:
    def __init__(self, *, settings: SettingsStore, registry: AppRegistry, scenarios: ScenarioStore,
                 journal: Journal, permissions: PermissionManager, executor: Executor,
                 folders: Callable[[], dict[str, str]], router: Optional[CommandRouter] = None,
                 clock: Callable[[], float] = time.time):
        self.settings = settings
        self.registry = registry
        self.scenarios = scenarios
        self.journal = journal
        self.permissions = permissions
        self.executor = executor
        self.folders = folders
        self.router = router or CommandRouter()
        self.clock = clock
        self._lock = threading.RLock()
        self._dialog: Optional[DialogState] = None
        self._undo: list[UndoEntry] = []
        self._last: Optional[ActionRequest] = None
        self._last_labels: dict[str, str] = {}
        self.last_response: Optional[CommandResponse] = None
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="arc-action")

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ================================================================== entry points
    def handle_text(self, text: str, source: Source = Source.TEXT, confidence: float = 1.0,
                    explicit: bool = False) -> CommandResponse:
        """`explicit` — voice captured after a deliberate activation (push-to-talk): no wake word needed."""
        with self._lock:
            settings = self.settings.get()
            if source == Source.VOICE and confidence < settings.general.min_confidence:
                # after push-to-talk the user expects an answer; background speech is ignored silently
                return self._finish(CommandResponse(input=text, source=source,
                                                    status=Status.UNKNOWN if explicit else Status.IGNORED,
                                                    message="Не расслышал команду. Повторите, пожалуйста.",
                                                    intent="low_confidence", data={"confidence": confidence}),
                                    record=explicit)
            ctx = RouterContext(
                apps=self.registry.list(include_disabled=False),
                scenarios=self.scenarios.list(),
                folders=self.folders(),
                wake_word=settings.general.wake_word,
                require_wake_word=(source == Source.VOICE and not explicit
                                   and settings.general.require_wake_word_for_voice),
                dialog=self._dialog,
                has_pending_confirmation=self.permissions.latest_pending() is not None,
                now=self.clock(),
            )
            plan = self.router.route(text, ctx)
            return self._execute_plan(plan, text, source)

    def confirm(self, confirmation_id: str, approve: bool, source: Source = Source.UI,
                acknowledge: bool = False) -> CommandResponse:
        with self._lock:
            response = self._confirm(confirmation_id, approve, source, acknowledge)
            return self._finish(response)

    def _confirm(self, confirmation_id: str, approve: bool, source: Source, acknowledge: bool) -> CommandResponse:
        if not approve:
            item = self.permissions.cancel(confirmation_id)
            msg = "Действие отменено." if item else "Запрос подтверждения уже неактуален."
            return CommandResponse(source=source, status=Status.CANCELLED, message=msg,
                                   action=item.spec.name if item else None, input=item.description if item else "")
        try:
            item = self.permissions.resolve(confirmation_id, source=source, acknowledge=acknowledge)
        except ConfirmationError as exc:
            return CommandResponse(source=source, status=Status.DENIED, message=str(exc))
        params = item.spec.params.model_validate(item.request.params)
        response = self._perform(item.request.model_copy(update={"source": item.request.source}), item.spec, params,
                                 item.context.get("labels", {}), decision=f"confirmed:{source.value}")
        response.input = item.description
        return response

    def undo_last(self, source: Source = Source.UI) -> CommandResponse:
        with self._lock:
            return self._finish(self._undo_last(source, "отмени"))

    def repeat_last(self, source: Source = Source.UI) -> CommandResponse:
        with self._lock:
            return self._finish(self._repeat_last(source, "повтори"))

    def emergency_stop(self, engaged: bool) -> CommandResponse:
        self.permissions.set_emergency_stop(engaged)
        with self._lock:
            self._dialog = None
        message = "Аварийная остановка: все действия автоматизации заблокированы." if engaged \
            else "Аварийная остановка снята."
        self.journal.audit(action="automation.emergency_stop", params={"engaged": engaged}, risk="A", source="ui",
                           decision="allow", status="done", message=message)
        return self._finish(CommandResponse(source=Source.UI, status=Status.DONE, message=message,
                                            intent="emergency_stop"))

    def run_action(self, request: ActionRequest, labels: Optional[dict[str, str]] = None) -> CommandResponse:
        """Direct action from the UI (quick-launch button)."""
        with self._lock:
            response = self._run_request(request, labels or {})
            return self._finish(response)

    # ================================================================== plan handling
    def _execute_plan(self, plan: Plan, text: str, source: Source) -> CommandResponse:
        if plan.kind == "ignored":
            return self._finish(CommandResponse(input=text, source=source, status=Status.IGNORED, message=plan.message,
                                                intent=plan.intent), record=False)
        if not plan.keep_dialog and plan.kind != "clarify":
            self._dialog = None
        if plan.kind == "clarify":
            self._dialog = plan.dialog
            return self._finish(CommandResponse(input=text, source=source, status=Status.CLARIFY, message=plan.message,
                                                intent=plan.intent,
                                                clarify=ClarifyInfo(question=plan.message, options=plan.options)))
        if plan.kind in ("reply", "unknown", "unavailable"):
            status = {"reply": Status.REPLY, "unknown": Status.UNKNOWN, "unavailable": Status.UNAVAILABLE}[plan.kind]
            if plan.intent == "app.not_found":
                status = Status.NOT_FOUND
            return self._finish(CommandResponse(input=text, source=source, status=status, message=plan.message,
                                                intent=plan.intent))
        if plan.kind == "meta":
            response = self._meta(plan, source)
            response.input = text
            return self._finish(response)
        responses = []
        for request in plan.actions:
            request.source = source
            responses.append(self._run_request(request, plan.labels))
            if responses[-1].status not in (Status.DONE, Status.DRY_RUN):
                break
        response = responses[-1] if len(responses) == 1 else self._merge(responses)
        response.input = text
        response.intent = plan.intent
        return self._finish(response)

    def _meta(self, plan: Plan, source: Source) -> CommandResponse:
        if plan.meta == "help":
            return CommandResponse(source=source, status=Status.REPLY, message=HELP_TEXT, intent="help")
        if plan.meta == "emergency_stop":
            self.permissions.set_emergency_stop(True)
            self._dialog = None
            return CommandResponse(source=source, status=Status.DONE, intent="emergency_stop",
                                   message="Аварийная остановка: автоматизация заблокирована. "
                                           "Снять её можно кнопкой в окне A.R.C.")
        if plan.meta == "cancel":
            pending = self.permissions.latest_pending()
            if pending:
                self.permissions.cancel(pending.id)
            had_dialog = self._dialog is not None
            self._dialog = None
            msg = "Хорошо, отменено." if pending or had_dialog else "Нечего отменять."
            return CommandResponse(source=source, status=Status.CANCELLED, message=msg, intent="cancel")
        if plan.meta in ("confirm_yes", "confirm_no"):
            pending = self.permissions.latest_pending()
            if pending is None:
                return CommandResponse(source=source, status=Status.REPLY, message="Нет действий, ожидающих подтверждения.")
            if plan.meta == "confirm_no":
                self.permissions.cancel(pending.id)
                return CommandResponse(source=source, status=Status.CANCELLED, message="Действие отменено.",
                                       action=pending.spec.name)
            return self._confirm(pending.id, True, source, False)
        if plan.meta == "undo":
            return self._undo_last(source, "")
        if plan.meta == "repeat":
            return self._repeat_last(source, "")
        return CommandResponse(source=source, status=Status.UNKNOWN, message="Неизвестная команда")

    def _undo_last(self, source: Source, text: str) -> CommandResponse:
        if not self._undo:
            return CommandResponse(input=text, source=source, status=Status.REPLY, intent="undo",
                                   message="Последнее действие нельзя отменить или отменять нечего.")
        entry = self._undo.pop()
        request = entry.request.model_copy(update={"source": source})
        response = self._run_request(request, self._last_labels, undoable=False)
        response.intent = "undo"
        if response.status == Status.DONE:
            response.message = f"Отменено: {entry.title}. {response.message}"
        return response

    def _repeat_last(self, source: Source, text: str) -> CommandResponse:
        if self._last is None:
            return CommandResponse(input=text, source=source, status=Status.REPLY, intent="repeat",
                                   message="Нечего повторять.")
        request = self._last.model_copy(update={"source": source})
        response = self._run_request(request, self._last_labels)
        response.intent = "repeat"
        return response

    # ================================================================== single action
    def _run_request(self, request: ActionRequest, labels: dict[str, str], undoable: bool = True) -> CommandResponse:
        decision = self.permissions.evaluate(request)
        spec = decision.spec
        risk = spec.risk if spec else None
        if decision.verdict == "deny":
            self.journal.audit(action=request.action, params=request.params, risk=risk.value if risk else "-",
                               source=request.source.value, decision="deny", status="denied", message=decision.reason)
            return CommandResponse(source=request.source, status=Status.DENIED, message=decision.reason,
                                   action=request.action, risk=risk)
        assert spec is not None and decision.params is not None
        if decision.verdict == "confirm":
            description = self._describe(spec, decision.params, labels)
            pending = self.permissions.request_confirmation(request, spec, description, {"labels": labels})
            self.journal.audit(action=request.action, params=request.params, risk=spec.risk.value,
                               source=request.source.value, decision="confirm", status="pending", message=description)
            hint = " Подтвердите в окне A.R.C. с отметкой «Я понимаю последствия»." if spec.risk == Risk.C \
                else " Скажите «да» или нажмите «Подтвердить»."
            return CommandResponse(source=request.source, status=Status.NEEDS_CONFIRMATION,
                                   message=f"Требуется подтверждение: {description}.{hint}",
                                   action=request.action, risk=spec.risk, confirmation=pending.info())
        return self._perform(request, spec, decision.params, labels, decision="allow", undoable=undoable)

    def _perform(self, request: ActionRequest, spec: ActionSpec, params: Params, labels: dict[str, str], *,
                 decision: str, undoable: bool = True) -> CommandResponse:
        settings = self.settings.get()
        if spec.risk in (Risk.B, Risk.C) and settings.safety.dry_run:
            description = self._describe(spec, params, labels)
            message = f"[ТЕСТОВЫЙ РЕЖИМ] Действие не выполнено: {description}. " \
                      f"Отключите тестовый режим в «Разрешениях», чтобы выполнять такие операции."
            self.journal.audit(action=request.action, params=request.params, risk=spec.risk.value,
                               source=request.source.value, decision=decision, status="dry_run", message=message,
                               dry_run=True)
            return CommandResponse(source=request.source, status=Status.DRY_RUN, message=message, action=spec.name,
                                   risk=spec.risk, dry_run=True)
        if spec.name == "scenario.run":
            result = self._run_scenario(params, request.source)
        else:
            result = self._execute_with_timeout(spec, params, request.source, settings.safety.action_timeout_s)
        self.journal.audit(action=request.action, params=request.params, risk=spec.risk.value,
                           source=request.source.value, decision=decision, status=result.status.value,
                           message=result.message)
        if result.ok:
            if result.undo is not None and undoable:
                self._undo.append(UndoEntry(result.undo, self._describe(spec, params, labels), self.clock()))
                del self._undo[:-20]
            if result.repeatable and spec.risk == Risk.A:
                self._last = request.model_copy()
                self._last_labels = dict(labels)
        return CommandResponse(source=request.source, status=result.status, message=result.message, action=spec.name,
                               risk=spec.risk, data=result.data)

    def _execute_with_timeout(self, spec: ActionSpec, params: Params, source: Source, timeout: float) -> ActionResult:
        future = self._pool.submit(self.executor.execute, spec.name, params, source)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return ActionResult(ok=False, status=Status.ERROR,
                                message=f"Операция «{spec.title}» не завершилась за {timeout:g} с и прервана.")
        except Exception as exc:  # unexpected bug in a handler: report, keep the assistant alive
            log.exception("action %s failed", spec.name)
            return ActionResult(ok=False, status=Status.ERROR, message=f"Внутренняя ошибка: {type(exc).__name__}")

    def _run_scenario(self, params: Params, source: Source) -> ActionResult:
        scenario = self.scenarios.get(getattr(params, "scenario_id"))
        if scenario is None or not scenario.enabled:
            return ActionResult(ok=False, status=Status.NOT_FOUND, message="Сценарий не найден или отключён")
        messages, failed = [], 0
        for step in scenario.steps:
            if self.permissions.emergency_stop:
                messages.append("остановлено аварийной остановкой")
                failed += 1
                break
            req = ActionRequest(action=step.action, params=step.params, source=Source.SCENARIO)
            decision = self.permissions.evaluate(req)
            if decision.verdict != "allow" or decision.spec is None or decision.params is None:
                messages.append(f"{step.action}: {decision.reason or 'нужно подтверждение'}")
                failed += 1
                continue
            result = self._execute_with_timeout(decision.spec, decision.params, Source.SCENARIO,
                                                self.settings.get().safety.action_timeout_s)
            self.journal.audit(action=step.action, params=step.params, risk=decision.spec.risk.value,
                               source=Source.SCENARIO.value, decision="allow", status=result.status.value,
                               message=result.message)
            messages.append(result.message)
            failed += 0 if result.ok else 1
        status = Status.DONE if failed == 0 else Status.ERROR
        summary = f"Сценарий «{scenario.name}»: " + " ".join(messages)
        return ActionResult(ok=failed == 0, status=status, message=summary,
                            data={"scenario": scenario.name, "failed": failed})

    # ================================================================== helpers
    def _describe(self, spec: ActionSpec, params: Params, labels: dict[str, str]) -> str:
        p = params.model_dump()
        if "app_id" in p:
            entry = self.registry.get(p["app_id"])
            name = labels.get(p["app_id"]) or (entry.name if entry else p["app_id"])
            verbs = {"app.launch": "запустить", "app.launch_admin": "запустить от имени администратора",
                     "app.close": "закрыть"}
            return f"{verbs.get(spec.name, spec.title)} «{name}»"
        if spec.name in ("power.shutdown", "power.restart"):
            return f"{spec.title.lower()} через {p['delay_s']} с"
        if spec.name == "files.create_folder":
            parent = self.folders().get(p["parent"], p["parent"])
            return f"создать папку «{p['name']}» в {parent}"
        if spec.name == "files.remove_empty_folder":
            return f"удалить пустую папку {p['path']}"
        if spec.name == "process.terminate":
            return f"завершить процесс {p.get('name') or ''} (PID {p['pid']})"
        if spec.name == "volume.change":
            return f"изменить громкость на {p['delta']:+d}%"
        if spec.name == "volume.set":
            return f"установить громкость {p['level']}%"
        if spec.name == "scenario.run":
            return f"сценарий «{labels.get(p['scenario_id'], p['scenario_id'])}»"
        return spec.title.lower()

    @staticmethod
    def _merge(responses: list[CommandResponse]) -> CommandResponse:
        last = responses[-1]
        last.message = " ".join(r.message for r in responses)
        return last

    def _finish(self, response: CommandResponse, record: bool = True) -> CommandResponse:
        if record:
            self.journal.add_history(source=response.source.value, input=response.input, intent=response.intent,
                                     action=response.action, status=response.status.value, message=response.message)
        self.last_response = response
        return response

    def state(self) -> dict:
        pending = self.permissions.latest_pending()
        return {
            "emergency_stop": self.permissions.emergency_stop,
            "dialog": {"question": self._dialog.question, "options": list(self._dialog.options)}
            if self._dialog and self._dialog.expires_at > self.clock() else None,
            "pending_confirmation": pending.info().model_dump() if pending else None,
            "can_undo": bool(self._undo),
            "can_repeat": self._last is not None,
            "last_response": self.last_response.model_dump(mode="json") if self.last_response else None,
            "pid": os.getpid(),
        }
