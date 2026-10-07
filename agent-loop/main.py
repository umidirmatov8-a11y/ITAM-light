"""AgentLoop entry point.

    AgentLoop.exe                         open the window
    AgentLoop.exe --task "текст задачи"   run in the console and print the result
    AgentLoop.exe --version
"""

from __future__ import annotations

import argparse
import sys

from app import __version__


def run_cli(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from app.config import PROVIDER_ANTHROPIC, PROVIDER_OLLAMA, load_settings
    from app.pipeline import STAGE_DONE, STAGE_TITLES, AgentPipeline, Event
    from app.local_runtime import LocalModelProvider
    from app.providers import OllamaProvider, ProviderError, create_provider
    from app.report import render_report

    settings = load_settings()
    if args.provider:
        settings = replace(settings, provider=args.provider)
    if args.gpu:
        settings = replace(settings, gpu_mode=args.gpu)
    if args.model:
        field = {PROVIDER_OLLAMA: "ollama_model", PROVIDER_ANTHROPIC: "anthropic_model"}.get(
            settings.provider, "local_model")
        settings = replace(settings, **{field: args.model})

    def show(event: Event) -> None:
        title = f"{STAGE_TITLES[event.stage]} · круг {event.iteration}"
        if event.started:
            print(f"\n=== {title} ===", file=sys.stderr, flush=True)
        elif event.stage == STAGE_DONE:
            print(f"\n{event.text}", file=sys.stderr, flush=True)
        elif event.stage != "execute":
            print(event.text, file=sys.stderr, flush=True)

    last_status = [""]

    def pull_progress(status: str, fraction: float | None) -> None:
        if status != last_status[0]:  # one line per download phase, not per chunk
            last_status[0] = status
            print(f"  {status}", file=sys.stderr, flush=True)

    try:
        provider = create_provider(settings)
        if isinstance(provider, LocalModelProvider):
            print(f"Модель {provider.model} работает на: {provider.start().device()}", file=sys.stderr, flush=True)
        if isinstance(provider, OllamaProvider) and not provider.has_model():
            print(f"Скачиваю модель {provider.model}…", file=sys.stderr, flush=True)
            provider.pull(pull_progress)
        pipeline = AgentPipeline(provider, args.iterations or settings.max_iterations, settings.language)
        run = pipeline.run(args.task, show)
    except (ProviderError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    print(run.best.result)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
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
    parser.add_argument("--provider", choices=("local", "ollama", "anthropic"), help="переопределить нейросеть из настроек")
    parser.add_argument("--model", help="переопределить модель: файл .gguf, имя в Ollama или модель Claude")
    parser.add_argument("--gpu", choices=("auto", "cpu"), help="встроенная модель: auto — видеокарта, если есть; cpu")
    parser.add_argument("--version", action="version", version=f"AgentLoop {__version__}")
    args = parser.parse_args(argv)
    if args.task:
        return run_cli(args)
    from app.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
