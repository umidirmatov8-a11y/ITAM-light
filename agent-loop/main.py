"""AgentLoop entry point.

    AgentLoop.exe                         open the window
    AgentLoop.exe --task "текст задачи"   run in the console and print the result
    AgentLoop.exe --version
"""

from __future__ import annotations

import argparse
import sys

from app import __version__


def run_cli(task: str, report_path: str | None, iterations: int | None) -> int:
    from app.config import load_settings
    from app.pipeline import STAGE_DONE, STAGE_TITLES, AgentPipeline, Event
    from app.providers import ProviderError, create_provider
    from app.report import render_report

    settings = load_settings()

    def show(event: Event) -> None:
        title = f"{STAGE_TITLES[event.stage]} · круг {event.iteration}"
        if event.started:
            print(f"\n=== {title} ===", file=sys.stderr, flush=True)
        elif event.stage == STAGE_DONE:
            print(f"\n{event.text}", file=sys.stderr, flush=True)
        elif event.stage != "execute":
            print(event.text, file=sys.stderr, flush=True)

    try:
        pipeline = AgentPipeline(create_provider(settings), iterations or settings.max_iterations, settings.language)
        run = pipeline.run(task, show)
    except (ProviderError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    print(run.best.result)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(render_report(run))
    return 0 if run.approved else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="AgentLoop", description="Команда ИИ-агентов: промпт → исполнение → проверка")
    parser.add_argument("--task", help="выполнить задачу в консоли без окна")
    parser.add_argument("--report", help="сохранить подробный отчёт (Markdown) в файл")
    parser.add_argument("--iterations", type=int, help="максимум кругов проверки")
    parser.add_argument("--version", action="version", version=f"AgentLoop {__version__}")
    args = parser.parse_args(argv)
    if args.task:
        return run_cli(args.task, args.report, args.iterations)
    from app.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
