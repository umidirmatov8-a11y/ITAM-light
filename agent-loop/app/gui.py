"""Tkinter desktop window: type a task, press «Запустить», watch the three agents work."""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from app import __version__
from app.config import (OLLAMA_PRESETS, PROVIDER_ANTHROPIC, PROVIDER_LOCAL, PROVIDER_OLLAMA, Settings,
                        load_settings, save_settings)
from app.local_runtime import LocalModelProvider, app_home, list_local_models
from app.pipeline import STAGE_DONE, STAGE_TITLES, AgentPipeline, Cancelled, Event, RunResult
from app.providers import OllamaProvider, ProviderError, create_provider

EFFORTS = ("low", "medium", "high", "xhigh", "max")
GPU_MODES = {"Авто — видеокарта (Vulkan), если есть": "auto", "Только процессор": "cpu"}


class SettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, settings: Settings):
        super().__init__(master)
        self.title("Настройки")
        self.resizable(False, False)
        self.transient(master)
        self.settings = settings
        self.result: Settings | None = None
        self.pull_cancel = threading.Event()

        self.provider = tk.StringVar(value=settings.provider)
        bundled = [p.name for p in list_local_models()]
        self.local_model = tk.StringVar(value=settings.local_model or (bundled[0] if bundled else ""))
        self.gpu_mode = tk.StringVar(value=next((k for k, v in GPU_MODES.items() if v == settings.gpu_mode),
                                                next(iter(GPU_MODES))))
        self.api_key = tk.StringVar(value=settings.anthropic_api_key)
        self.model = tk.StringVar(value=settings.anthropic_model)
        self.effort = tk.StringVar(value=settings.effort)
        self.ollama_url = tk.StringVar(value=settings.ollama_url)
        self.ollama_model = tk.StringVar(value=settings.ollama_model)
        self.ollama_info = tk.StringVar()
        self.iterations = tk.IntVar(value=settings.max_iterations)
        self.language = tk.StringVar(value=settings.language)

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        row = 0

        def label(text: str):
            ttk.Label(body, text=text).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 8))

        ttk.Label(body, text="Нейросеть:", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Radiobutton(body, text="Встроенная модель (работает из коробки, без интернета)",
                        value=PROVIDER_LOCAL, variable=self.provider).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        label("Файл модели:")
        local = ttk.Frame(body)
        local.grid(row=row, column=1, sticky="we")
        ttk.Combobox(local, textvariable=self.local_model, values=bundled, width=40).pack(side="left")
        ttk.Button(local, text="Папка моделей", command=self._open_models).pack(side="left", padx=6)
        row += 1
        ttk.Label(body, text="Свои модели: положите файл .gguf (например, с huggingface.co) в папку моделей.",
                  foreground="#57606a").grid(row=row, column=1, sticky="w")
        row += 1
        label("Ускорение:")
        ttk.Combobox(body, textvariable=self.gpu_mode, values=list(GPU_MODES), state="readonly",
                     width=40).grid(row=row, column=1, sticky="w")
        row += 1
        ttk.Radiobutton(body, text="Ollama (если он у вас уже установлен)",
                        value=PROVIDER_OLLAMA, variable=self.provider).grid(row=row, column=0, columnspan=2,
                                                                           sticky="w", pady=(10, 0))
        row += 1
        label("Модель:")
        models = ttk.Frame(body)
        models.grid(row=row, column=1, sticky="we")
        combo = ttk.Combobox(models, textvariable=self.ollama_model, width=24,
                             values=[name for name, _size, _note in OLLAMA_PRESETS])
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._describe_model())
        combo.bind("<KeyRelease>", lambda _e: self._describe_model())
        self.pull_btn = ttk.Button(models, text="Скачать модель", command=self._pull)
        self.pull_btn.pack(side="left", padx=6)
        ttk.Button(models, text="Проверить", command=self._check).pack(side="left")
        row += 1
        ttk.Label(body, textvariable=self.ollama_info, foreground="#57606a", wraplength=460).grid(
            row=row, column=1, sticky="w")
        row += 1
        label("Адрес Ollama:")
        ttk.Entry(body, textvariable=self.ollama_url, width=48).grid(row=row, column=1, sticky="we")
        row += 1
        ttk.Radiobutton(body, text="Claude API (облако, нужен платный API-ключ)", value=PROVIDER_ANTHROPIC,
                        variable=self.provider).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        row += 1
        label("API-ключ Claude:")
        ttk.Entry(body, textvariable=self.api_key, show="•", width=48).grid(row=row, column=1, sticky="we")
        row += 1
        label("Модель Claude:")
        ttk.Entry(body, textvariable=self.model, width=48).grid(row=row, column=1, sticky="we")
        row += 1
        label("Усилие (effort):")
        ttk.Combobox(body, textvariable=self.effort, values=EFFORTS, state="readonly",
                     width=12).grid(row=row, column=1, sticky="w")
        row += 1
        ttk.Separator(body).grid(row=row, column=0, columnspan=2, sticky="we", pady=10)
        row += 1
        label("Макс. кругов проверки:")
        ttk.Spinbox(body, from_=1, to=10, textvariable=self.iterations, width=6).grid(row=row, column=1, sticky="w")
        row += 1
        label("Язык ответов:")
        ttk.Entry(body, textvariable=self.language, width=20).grid(row=row, column=1, sticky="w")
        row += 1

        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Сохранить", command=self._save).pack(side="left", padx=4)
        ttk.Button(buttons, text="Отмена", command=self.destroy).pack(side="left")

        self._describe_model()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    def destroy(self):
        self.pull_cancel.set()
        super().destroy()

    @staticmethod
    def _open_models():
        folder = app_home() / "models"
        folder.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Папка моделей", str(folder))

    def _describe_model(self):
        name = self.ollama_model.get().strip()
        for preset, size, note in OLLAMA_PRESETS:
            if preset == name:
                self.ollama_info.set(f"{size} · {note}")
                return
        self.ollama_info.set("Любая модель из каталога https://ollama.com/library")

    def _ollama(self) -> OllamaProvider:
        return OllamaProvider(replace(self.settings, ollama_url=self.ollama_url.get().strip(),
                                      ollama_model=self.ollama_model.get().strip()))

    def _set_info(self, text: str):
        # Called from worker threads: hop to the UI thread; ignore if the dialog is already closed.
        try:
            self.after(0, self.ollama_info.set, text)
        except (tk.TclError, RuntimeError):
            pass

    def _check(self):
        provider = self._ollama()

        def work():
            try:
                models = provider.list_models()
                state = "скачана ✔" if provider.has_model() else "не скачана — нажмите «Скачать модель»"
                self._set_info(f"Ollama работает. {provider.model}: {state}. "
                               f"На компьютере: {', '.join(models) or 'моделей нет'}")
            except ProviderError as exc:
                self._set_info(str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _pull(self):
        provider = self._ollama()
        self.pull_btn.configure(state="disabled")

        def progress(status: str, fraction: float | None):
            self._set_info(f"{provider.model}: {status} {fraction:.0%}" if fraction is not None
                           else f"{provider.model}: {status}")

        def work():
            try:
                provider.pull(progress, self.pull_cancel)
                self._set_info(f"{provider.model} скачана ✔ — можно сохранять и запускать")
            except ProviderError as exc:
                self._set_info(str(exc))
            try:
                self.after(0, lambda: self.pull_btn.configure(state="normal"))
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=work, daemon=True).start()

    def _save(self):
        try:
            iterations = int(self.iterations.get())
        except (tk.TclError, ValueError):
            iterations = 3
        self.result = replace(
            self.settings,
            provider=self.provider.get(),
            local_model=self.local_model.get().strip(),
            gpu_mode=GPU_MODES.get(self.gpu_mode.get(), "auto"),
            anthropic_api_key=self.api_key.get().strip(),
            anthropic_model=self.model.get().strip() or Settings.anthropic_model,
            effort=self.effort.get() or Settings.effort,
            ollama_url=self.ollama_url.get().strip() or Settings.ollama_url,
            ollama_model=self.ollama_model.get().strip() or Settings.ollama_model,
            max_iterations=max(1, min(10, iterations)),
            language=self.language.get().strip() or Settings.language,
        )
        self.destroy()


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = load_settings()
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self.last_run: RunResult | None = None
        self.device = ""  # where the built-in model runs: GPU name or CPU

        root.title(f"AgentLoop {__version__} — команда ИИ-агентов")
        root.geometry("1000x720")
        root.minsize(720, 520)

        top = ttk.Frame(root, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Опишите задачу (Ctrl+Enter — запустить):").pack(anchor="w")
        self.task = scrolledtext.ScrolledText(top, height=6, wrap="word", font=("Segoe UI", 10))
        self.task.pack(fill="x", pady=(4, 6))
        self.task.bind("<Control-Return>", lambda _e: (self.start(), "break")[1])

        bar = ttk.Frame(top)
        bar.pack(fill="x")
        self.run_btn = ttk.Button(bar, text="▶ Запустить", command=self.start)
        self.run_btn.pack(side="left")
        self.stop_btn = ttk.Button(bar, text="■ Стоп", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(bar, text="Настройки", command=self.open_settings).pack(side="left")
        ttk.Button(bar, text="Сохранить отчёт…", command=self.save_report).pack(side="right")
        ttk.Button(bar, text="Копировать результат", command=self.copy_result).pack(side="right", padx=6)

        tabs = ttk.Notebook(root)
        tabs.pack(fill="both", expand=True, padx=10, pady=4)
        self.tabs = tabs
        self.log = self._text_tab(tabs, "Ход работы агентов")
        self.output = self._text_tab(tabs, "Результат")
        for tag, color in (("prompt", "#1f6feb"), ("execute", "#8250df"), ("verify", "#bf8700"),
                           ("done", "#1a7f37"), ("error", "#cf222e")):
            self.log.tag_configure(tag, foreground=color, font=("Segoe UI", 10, "bold"))

        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, anchor="w", padding=(10, 2)).pack(fill="x", side="bottom")
        self._update_status()
        root.after(100, self._poll)

    @staticmethod
    def _text_tab(tabs: ttk.Notebook, title: str) -> scrolledtext.ScrolledText:
        frame = ttk.Frame(tabs)
        tabs.add(frame, text=title)
        text = scrolledtext.ScrolledText(frame, wrap="word", font=("Consolas", 10), state="disabled")
        text.pack(fill="both", expand=True)
        return text

    @staticmethod
    def _append(widget: scrolledtext.ScrolledText, text: str, tag: str | None = None):
        widget.configure(state="normal")
        widget.insert("end", text, tag or ())
        widget.see("end")
        widget.configure(state="disabled")

    @staticmethod
    def _clear(widget: scrolledtext.ScrolledText):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def _update_status(self, extra: str = ""):
        s = self.settings
        if s.provider == PROVIDER_ANTHROPIC:
            model = s.anthropic_model
        elif s.provider == PROVIDER_OLLAMA:
            model = f"Ollama · {s.ollama_model}"
        else:
            bundled = list_local_models()
            model = f"встроенная · {s.local_model or (bundled[0].name if bundled else 'не найдена')}"
            if self.device:
                model += f" · {self.device}"
        self.status.set(f"Модель: {model} · кругов: до {s.max_iterations}" + (f" · {extra}" if extra else ""))

    def open_settings(self):
        dialog = SettingsDialog(self.root, self.settings)
        self.root.wait_window(dialog)
        if dialog.result is not None:
            self.settings = dialog.result
            try:
                save_settings(self.settings)
            except OSError as exc:
                messagebox.showerror("Настройки", f"Не удалось сохранить настройки: {exc}")
            self._update_status()

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        task = self.task.get("1.0", "end").strip()
        if not task:
            messagebox.showinfo("AgentLoop", "Сначала опишите задачу.")
            return
        try:
            provider = create_provider(self.settings)
        except ProviderError as exc:
            messagebox.showerror("AgentLoop", str(exc))
            return
        pipeline = AgentPipeline(provider, self.settings.max_iterations, self.settings.language)
        self.cancel = threading.Event()
        self._clear(self.log)
        self._clear(self.output)
        self.tabs.select(0)
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.last_run = None

        def work():
            try:
                if isinstance(provider, LocalModelProvider):
                    self.events.put(("progress", f"Загружаю модель {provider.model} в память…"))
                    server = provider.start(self.cancel)
                    self.events.put(("device", server.device()))
                if isinstance(provider, OllamaProvider) and not provider.has_model():
                    self.events.put(("log", f"Модель {provider.model} ещё не скачана — скачиваю (один раз)…\n"))
                    provider.pull(lambda status, fraction: self.events.put(
                        ("progress", f"Скачивание {provider.model}: {status}"
                                     + (f" {fraction:.0%}" if fraction is not None else ""))), self.cancel)
                    self.events.put(("log", f"Модель {provider.model} скачана.\n"))
                result = pipeline.run(task, self.events.put, self.cancel)
                if isinstance(provider, LocalModelProvider):
                    self.events.put(("device", provider.start().device()))  # may have fallen back to the CPU
                self.events.put(("finished", result))
            except Cancelled:
                self.events.put(("stopped", None))
            except (ProviderError, ValueError) as exc:
                self.events.put(("stopped", None) if self.cancel.is_set() else ("error", str(exc)))
            except Exception as exc:  # keep the UI alive on unexpected failures
                self.events.put(("error", f"{type(exc).__name__}: {exc}"))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def stop(self):
        self.cancel.set()
        self.stop_btn.configure(state="disabled")
        self._update_status("останавливаю после текущего шага…")

    def _poll(self):
        try:
            while True:
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _handle(self, item):
        if isinstance(item, Event):
            title = f"{STAGE_TITLES[item.stage]} · круг {item.iteration}"
            if item.started:
                self._append(self.log, f"\n▶ {title} — работает…\n", item.stage)
                self._update_status(f"{title} работает…")
            elif item.stage == STAGE_DONE:
                self._append(self.log, f"\n✔ {item.text}\n", STAGE_DONE)
            else:
                self._append(self.log, item.text + "\n")
            return
        kind, payload = item
        if kind == "log":
            self._append(self.log, payload)
            return
        if kind == "progress":
            self.status.set(payload)
            return
        if kind == "device":
            if payload != self.device:
                self.device = payload
                self._append(self.log, f"Модель работает на: {payload}\n")
            self._update_status()
            return
        self.run_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if kind == "finished":
            self.last_run = payload
            best = payload.best
            header = ("✔ Результат проверен и принят" if payload.approved
                      else "⚠ Проверку не прошёл ни один вариант — показан лучший")
            self._append(self.output, f"{header} (круг {best.iteration}, оценка {best.verdict.score}/10)\n\n")
            self._append(self.output, best.result)
            self.tabs.select(1)
            self._update_status("готово")
        elif kind == "stopped":
            self._append(self.log, "\n■ Остановлено пользователем\n", "error")
            self._update_status("остановлено")
        else:
            self._append(self.log, f"\n✖ Ошибка: {payload}\n", "error")
            self._update_status("ошибка")
            messagebox.showerror("AgentLoop", payload)

    def copy_result(self):
        if self.last_run:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.last_run.best.result)
            self._update_status("результат скопирован")

    def save_report(self):
        if not self.last_run:
            messagebox.showinfo("AgentLoop", "Пока нечего сохранять.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".md",
                                            filetypes=[("Markdown", "*.md"), ("Текст", "*.txt")])
        if path:
            from app.report import render_report
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(render_report(self.last_run))


def main() -> int:
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "resources" / "agentloop.ico"
    try:
        root.iconbitmap(default=str(icon))
    except tk.TclError:
        pass
    MainWindow(root)
    root.mainloop()
    return 0
