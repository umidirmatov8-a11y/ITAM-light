"""The agent loop.

    task --> [1. Prompt engineer] --> prompt --> [2. Executor] --> result --> [3. Verifier]
                    ^                                                            |
                    |                     rejected: feedback                     |
                    +------------------------------------------------------------+
                                                                    approved --> user

The loop stops when the verifier approves the result or after `max_iterations` rounds; in the
latter case the best-scored attempt is returned and marked as not approved.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Callable

from app.providers import Provider, ProviderError

PROMPT_ENGINEER_SYSTEM = """\
Ты — агент «Промпт-инженер». Тебе дают задачу пользователя, а на повторных кругах ещё и \
предыдущий промпт, полученный по нему результат и замечания проверяющего.
Составь один исчерпывающий промпт для агента-исполнителя, чтобы он с первого раза выполнил задачу \
правильно: роль исполнителя, цель, контекст, входные данные, требования и ограничения, формат и \
структура ответа, критерии качества. Если были замечания — явно устрани каждое из них в новом промпте.
Ничего не выполняй сам. Выведи только текст промпта, без пояснений и вступлений. Язык промпта: {language}."""

EXECUTOR_SYSTEM = """\
Ты — агент «Исполнитель». Выполни задание из промпта полностью и аккуратно, строго соблюдая \
требуемый формат. Выведи только готовый результат, без рассуждений о процессе и без вопросов к \
пользователю: если чего-то не хватает, сделай разумное допущение и коротко его укажи. \
Язык ответа: {language}, если в задании не сказано иное."""

VERIFIER_SYSTEM = """\
Ты — агент «Проверяющий». Тебе дают исходную задачу пользователя и результат исполнителя. \
Строго и объективно проверь результат: решает ли он задачу полностью, нет ли фактических, \
логических и технических ошибок, соблюдены ли все требования и формат.
approved = true только если результат можно отдавать пользователю без доработок.
score — оценка от 0 до 10. issues — конкретные найденные проблемы (пустой список, если их нет). \
feedback — конкретные указания, что исправить на следующем круге. Пиши на языке: {language}."""

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "score": {"type": "integer"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "feedback": {"type": "string"},
    },
    "required": ["approved", "score", "issues", "feedback"],
    "additionalProperties": False,
}

STAGE_PROMPT = "prompt"
STAGE_EXECUTE = "execute"
STAGE_VERIFY = "verify"
STAGE_DONE = "done"

STAGE_TITLES = {
    STAGE_PROMPT: "Агент 1 · Промпт-инженер",
    STAGE_EXECUTE: "Агент 2 · Исполнитель",
    STAGE_VERIFY: "Агент 3 · Проверяющий",
    STAGE_DONE: "Итог",
}


class Cancelled(Exception):
    """The user stopped the run."""


@dataclass
class Verdict:
    approved: bool
    score: int
    issues: list[str] = field(default_factory=list)
    feedback: str = ""

    def as_text(self) -> str:
        lines = [f"{'ПРИНЯТО' if self.approved else 'НА ДОРАБОТКУ'} · оценка {self.score}/10"]
        lines += [f"• {issue}" for issue in self.issues]
        if self.feedback:
            lines.append(f"Рекомендации: {self.feedback}")
        return "\n".join(lines)


@dataclass
class Attempt:
    iteration: int
    prompt: str
    result: str
    verdict: Verdict


@dataclass
class RunResult:
    task: str
    attempts: list[Attempt]

    @property
    def best(self) -> Attempt:
        approved = [a for a in self.attempts if a.verdict.approved]
        if approved:
            return approved[-1]
        return max(self.attempts, key=lambda a: (a.verdict.score, a.iteration))

    @property
    def approved(self) -> bool:
        return self.best.verdict.approved


@dataclass
class Event:
    stage: str
    iteration: int
    text: str
    started: bool = False  # True: the agent started working; False: `text` is its output


def parse_verdict(raw: str) -> Verdict:
    """Parse the verifier's JSON answer; tolerate code fences and text around the object."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ProviderError("Проверяющий вернул ответ не в формате JSON")
    try:
        data = json.loads(text[start:end + 1])
    except ValueError as exc:
        raise ProviderError("Проверяющий вернул некорректный JSON") from exc
    if not isinstance(data, dict):
        raise ProviderError("Проверяющий вернул некорректный JSON")
    try:
        score = int(data.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    issues = data.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    approved = data.get("approved")
    if isinstance(approved, str):
        approved = approved.strip().lower() in ("true", "yes", "да")
    return Verdict(
        approved=bool(approved),
        score=max(0, min(10, score)),
        issues=[str(i) for i in issues if str(i).strip()],
        feedback=str(data.get("feedback") or ""),
    )


class AgentPipeline:
    def __init__(self, provider: Provider, max_iterations: int = 3, language: str = "русский"):
        self.provider = provider
        self.max_iterations = max(1, int(max_iterations))
        self.language = language

    def run(
        self,
        task: str,
        on_event: Callable[[Event], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> RunResult:
        task = task.strip()
        if not task:
            raise ValueError("Пустая задача")
        emit = on_event or (lambda _e: None)
        cancel = cancel or threading.Event()
        attempts: list[Attempt] = []

        for iteration in range(1, self.max_iterations + 1):
            prompt = self._step(emit, cancel, STAGE_PROMPT, iteration,
                                lambda: self._engineer(task, attempts[-1] if attempts else None))
            result = self._step(emit, cancel, STAGE_EXECUTE, iteration, lambda: self._execute(prompt))
            verdict = self._step(emit, cancel, STAGE_VERIFY, iteration,
                                 lambda: self._verify(task, result), show=Verdict.as_text)
            attempts.append(Attempt(iteration, prompt, result, verdict))
            if verdict.approved:
                break

        run = RunResult(task, attempts)
        status = "принят проверяющим" if run.approved else (
            f"не принят за {len(attempts)} круг(а); показан лучший вариант (оценка {run.best.verdict.score}/10)")
        emit(Event(STAGE_DONE, run.best.iteration, f"Результат круга {run.best.iteration} {status}."))
        return run

    def _step(self, emit, cancel: threading.Event, stage: str, iteration: int, work, show=str):
        if cancel.is_set():
            raise Cancelled()
        emit(Event(stage, iteration, "", started=True))
        value = work()
        if cancel.is_set():
            raise Cancelled()
        emit(Event(stage, iteration, show(value)))
        return value

    def _engineer(self, task: str, previous: Attempt | None) -> str:
        user = f"Задача пользователя:\n{task}"
        if previous is not None:
            user += (
                f"\n\n--- Предыдущий промпт (круг {previous.iteration}) ---\n{previous.prompt}"
                f"\n\n--- Результат исполнителя ---\n{previous.result}"
                f"\n\n--- Заключение проверяющего ---\n{previous.verdict.as_text()}"
                "\n\nСоставь улучшенный промпт, который устраняет все замечания."
            )
        return self.provider.complete(PROMPT_ENGINEER_SYSTEM.format(language=self.language), user)

    def _execute(self, prompt: str) -> str:
        return self.provider.complete(EXECUTOR_SYSTEM.format(language=self.language), prompt)

    def _verify(self, task: str, result: str) -> Verdict:
        user = f"Исходная задача пользователя:\n{task}\n\n--- Результат исполнителя ---\n{result}"
        system = VERIFIER_SYSTEM.format(language=self.language)
        raw = self.provider.complete(system, user, schema=VERDICT_SCHEMA)
        try:
            return parse_verdict(raw)
        except ProviderError:
            # Small local models occasionally break the JSON format; ask once more.
            return parse_verdict(self.provider.complete(system, user, schema=VERDICT_SCHEMA))
