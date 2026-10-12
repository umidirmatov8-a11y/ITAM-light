"""What a gesture may trigger: a few internal UI actions or a catalog action that is
category A *and* marked gesture_allowed. Anything else is rejected when settings are saved,
and the Permission Manager checks again (Source.GESTURE) when the gesture fires."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import Risk
from ..permissions.catalog import CATALOG

if TYPE_CHECKING:
    from ..storage.settings import GestureBinding

INTERNAL_ACTIONS = {
    "gestures.pause_toggle": "Пауза / возобновление жестов",
    "gestures.cancel": "Отменить текущий вопрос или запрос",
    "assistant.repeat": "Повторить последнее безопасное действие",
    "ui.toggle_compact": "Переключить вид интерфейса (пульт / виджет)",
    "profile.silent_toggle": "Режим тишины вкл/выкл",
}


def gesture_actions() -> dict[str, str]:
    """All actions selectable for gestures (code -> Russian title)."""
    result = dict(INTERNAL_ACTIONS)
    for spec in CATALOG.values():
        if spec.gesture_allowed and spec.risk == Risk.A:
            result[spec.name] = spec.title
    return result


def validate_binding(binding: "GestureBinding") -> "GestureBinding":
    if binding.action in INTERNAL_ACTIONS:
        if binding.params:
            raise ValueError(f"{binding.action} takes no parameters")
        return binding
    spec = CATALOG.get(binding.action)
    if spec is None or not spec.gesture_allowed or spec.risk != Risk.A:
        raise ValueError(f"action {binding.action} cannot be bound to a gesture")
    binding.params = spec.params.model_validate(binding.params).model_dump()
    return binding
