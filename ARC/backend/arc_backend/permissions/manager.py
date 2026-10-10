"""Permission Manager: decides allow / confirm / deny for every ActionRequest."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

from pydantic import ValidationError

from ..models import ActionRequest, ConfirmationInfo, Risk, Source
from ..storage.settings import NetworkMode, Settings
from .catalog import ActionSpec, Params, get_spec

Verdict = Literal["allow", "confirm", "deny"]


@dataclass
class Decision:
    verdict: Verdict
    reason: str = ""
    spec: Optional[ActionSpec] = None
    params: Optional[Params] = None

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"


@dataclass
class PendingConfirmation:
    id: str
    request: ActionRequest
    spec: ActionSpec
    description: str
    created_at: float
    expires_at: float
    context: dict = field(default_factory=dict)

    def info(self) -> ConfirmationInfo:
        return ConfirmationInfo(id=self.id, action=self.spec.name, title=self.spec.title,
                                description=self.description, risk=self.spec.risk, expires_at=self.expires_at,
                                requires_acknowledge=self.spec.risk == Risk.C)


class ConfirmationError(Exception):
    pass


class PermissionManager:
    def __init__(self, settings: Callable[[], Settings], clock: Callable[[], float] = time.time):
        self._settings = settings
        self._clock = clock
        self._lock = threading.Lock()
        self._pending: dict[str, PendingConfirmation] = {}
        self._emergency = False

    # ------------------------------------------------------------------ emergency stop
    @property
    def emergency_stop(self) -> bool:
        return self._emergency

    def set_emergency_stop(self, engaged: bool) -> None:
        with self._lock:
            self._emergency = engaged
            if engaged:
                self._pending.clear()

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, request: ActionRequest) -> Decision:
        spec = get_spec(request.action)
        if spec is None:
            return Decision("deny", "Действие не входит в каталог разрешённых операций")
        try:
            params = spec.params.model_validate(request.params)
        except ValidationError as exc:
            first = exc.errors()[0]
            return Decision("deny", f"Некорректные параметры: {'.'.join(map(str, first['loc']))} — {first['msg']}",
                            spec)
        settings = self._settings()
        if self._emergency:
            return Decision("deny", "Автоматизация остановлена (аварийная остановка). Снимите её в интерфейсе.",
                            spec, params)
        if not settings.safety.modules.get(spec.module, False):
            return Decision("deny", f"Модуль «{spec.module}» отключён в настройках разрешений", spec, params)
        needs_online = spec.requires_online or (spec.name == "mode.set" and getattr(params, "mode", "") == "ONLINE")
        if needs_online and not settings.network.online_allowed:
            return Decision("deny", "Онлайн-функции полностью отключены в настройках", spec, params)
        if spec.requires_online and settings.network.mode != NetworkMode.ONLINE:
            return Decision("deny", "Для этого нужен режим ONLINE. Скажите «переключись в онлайн-режим».",
                            spec, params)
        if request.source == Source.GESTURE and (not spec.gesture_allowed or spec.risk != Risk.A):
            return Decision("deny", "Это действие нельзя выполнить жестом", spec, params)
        if spec.name == "mode.set" and request.source == Source.AI:
            return Decision("deny", "Языковая модель не может менять режим работы", spec, params)
        if spec.risk == Risk.A:
            return Decision("allow", "", spec, params)
        return Decision("confirm", "Требуется подтверждение", spec, params)

    # ------------------------------------------------------------------ confirmations
    def request_confirmation(self, request: ActionRequest, spec: ActionSpec, description: str,
                             context: Optional[dict] = None) -> PendingConfirmation:
        ttl = self._settings().safety.confirmation_ttl_s
        now = self._clock()
        item = PendingConfirmation(id=secrets.token_urlsafe(12), request=request, spec=spec,
                                   description=description, created_at=now, expires_at=now + ttl,
                                   context=context or {})
        with self._lock:
            self._expire(now)
            self._pending[item.id] = item
        return item

    def pending(self) -> list[PendingConfirmation]:
        with self._lock:
            self._expire(self._clock())
            return list(self._pending.values())

    def latest_pending(self) -> Optional[PendingConfirmation]:
        items = self.pending()
        return max(items, key=lambda p: p.created_at) if items else None

    def cancel(self, confirmation_id: str) -> Optional[PendingConfirmation]:
        with self._lock:
            return self._pending.pop(confirmation_id, None)

    def resolve(self, confirmation_id: str, *, source: Source, acknowledge: bool = False) -> PendingConfirmation:
        """Consume an approval. Raises ConfirmationError if it cannot be accepted from this source."""
        with self._lock:
            now = self._clock()
            self._expire(now)
            item = self._pending.get(confirmation_id)
            if item is None:
                raise ConfirmationError("Запрос подтверждения не найден или истёк")
            if self._emergency:
                raise ConfirmationError("Аварийная остановка активна")
            if source in (Source.GESTURE, Source.AI, Source.SCENARIO):
                raise ConfirmationError("Это действие нельзя подтвердить данным способом")
            if item.spec.risk == Risk.C and (source != Source.UI or not acknowledge):
                raise ConfirmationError("Критическое действие подтверждается только в окне A.R.C. "
                                        "с отметкой «Я понимаю последствия»")
            del self._pending[confirmation_id]
            return item

    def _expire(self, now: float) -> None:
        for key in [k for k, v in self._pending.items() if v.expires_at <= now]:
            del self._pending[key]
