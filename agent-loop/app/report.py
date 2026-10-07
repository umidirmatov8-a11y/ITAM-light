"""Markdown report of a whole run: every round's prompt, result and verdict."""

from __future__ import annotations

from app.pipeline import RunResult


def render_report(run: RunResult) -> str:
    best = run.best
    lines = [
        "# Отчёт AgentLoop",
        "",
        "## Задача",
        run.task,
        "",
        f"## Итоговый результат (круг {best.iteration}, оценка {best.verdict.score}/10, "
        f"{'принят' if run.approved else 'НЕ принят проверяющим'})",
        best.result,
    ]
    for attempt in run.attempts:
        lines += [
            "",
            f"## Круг {attempt.iteration}",
            "### Промпт (агент 1)",
            attempt.prompt,
            "### Результат (агент 2)",
            attempt.result,
            "### Проверка (агент 3)",
            attempt.verdict.as_text(),
        ]
    return "\n".join(lines) + "\n"
