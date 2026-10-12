"""Document Engine: background jobs that (optionally) search the web, write the content, render the
file, verify it by reading it back and only then put it next to the user's documents.

The file is first written under a temporary name in the target folder; a file that fails
verification is removed and never shown as ready. Existing files are never overwritten.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx

from ..ai.ollama import OllamaError
from ..automation.files import PathError, PathGuard
from ..online.client import OnlineError
from ..online.providers import SearchResult
from ..online.research import ResearchEngine
from ..storage.settings import Settings
from .content import ai_usable, attach_sources, generate_with_ai, template_content
from .model import KIND_TITLES
from .render import RENDERERS, RenderError

log = logging.getLogger(__name__)

EXTENSIONS = {"pptx": ".pptx", "docx": ".docx", "xlsx": ".xlsx", "pdf": ".pdf", "txt": ".txt"}
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)
STAGES = {"queued": "в очереди", "research": "поиск в интернете", "writing": "составляю текст",
          "rendering": "создаю файл", "verifying": "проверяю файл", "done": "готово", "error": "ошибка",
          "cancelled": "отменено"}


def safe_filename(title: str, ext: str) -> str:
    name = " ".join(_BAD.sub(" ", title).split())[:80].rstrip(". ")
    if not name or _RESERVED.match(name):
        name = "Документ " + time.strftime("%Y-%m-%d %H-%M")
    return name + ext


def unique_path(folder: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, filename)
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return candidate


@dataclass
class DocJob:
    id: str
    kind: str
    topic: str
    use_web: bool
    source: str
    created: float = field(default_factory=time.time)
    status: str = "queued"
    title: str = ""
    path: str = ""
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    ai_used: bool = False
    sources: int = 0
    pages: int = 0
    finished: float = 0.0
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def view(self) -> dict:
        return {"id": self.id, "kind": self.kind, "topic": self.topic, "use_web": self.use_web, "source": self.source,
                "created": self.created, "status": self.status, "stage": STAGES.get(self.status, self.status),
                "title": self.title, "path": self.path, "name": os.path.basename(self.path) if self.path else "",
                "message": self.message, "warnings": self.warnings, "details": self.details, "ai_used": self.ai_used,
                "sources": self.sources, "pages": self.pages, "finished": self.finished}


class Cancelled(Exception):
    pass


class DocumentEngine:
    def __init__(self, settings: Callable[[], Settings], folders: Callable[[], dict[str, str]],
                 research: Optional[ResearchEngine], *, on_finished: Optional[Callable[[DocJob], None]] = None,
                 opener: Optional[Callable[[str], None]] = None, emergency: Callable[[], bool] = lambda: False,
                 ai_transport: Optional[httpx.BaseTransport] = None):
        self.settings = settings
        self.folders = folders
        self.research = research
        self.on_finished = on_finished
        self.opener = opener
        self.emergency = emergency
        self._ai_transport = ai_transport
        self._jobs: dict[str, DocJob] = {}
        self._lock = threading.Lock()
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="arc-docs")

    # ------------------------------------------------------------------ folders
    def output_dir(self) -> str:
        """Target folder, validated against the allowed directories (raises PathError)."""
        settings = self.settings()
        folder = settings.documents.output_dir
        if not folder:
            documents = self.folders().get("documents")
            if not documents:
                raise PathError("Не найдена папка «Документы». Укажите папку в «Настройки → Документы».")
            folder = os.path.join(documents, "ARC")
        return PathGuard(settings.safety.allowed_dirs).check(folder)

    def recent_files(self, limit: int = 20) -> list[dict]:
        try:
            folder = self.output_dir()
            entries = [e for e in os.scandir(folder)
                       if e.is_file() and os.path.splitext(e.name)[1].lower() in EXTENSIONS.values()
                       and not e.name.startswith(".~arc-")]
        except (PathError, OSError):
            return []
        entries.sort(key=lambda e: e.stat().st_mtime, reverse=True)
        return [{"name": e.name, "path": e.path, "size": e.stat().st_size, "modified": e.stat().st_mtime}
                for e in entries[:limit]]

    # ------------------------------------------------------------------ jobs
    def submit(self, kind: str, topic: str, use_web: bool, source: str) -> DocJob:
        job = DocJob(id=secrets.token_hex(6), kind=kind, topic=" ".join(topic.split())[:300], use_web=use_web,
                     source=source)
        with self._lock:
            self._jobs[job.id] = job
            for old in sorted(self._jobs.values(), key=lambda j: j.created)[:-30]:
                if old.status in ("done", "error", "cancelled"):
                    del self._jobs[old.id]
        self._pool.submit(self._run, job)
        return job

    def jobs(self) -> list[dict]:
        with self._lock:
            return [j.view() for j in sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)]

    def get(self, job_id: str) -> Optional[DocJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def active(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status not in ("done", "error", "cancelled"))

    def latest_path(self) -> Optional[str]:
        with self._lock:
            done = [j for j in self._jobs.values() if j.status == "done" and j.path]
        if done:
            return max(done, key=lambda j: j.finished).path
        files = self.recent_files(1)
        return files[0]["path"] if files else None

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.status in ("done", "error", "cancelled"):
            return False
        job.cancel.set()
        return True

    def cancel_all(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                job.cancel.set()

    def wait(self, job_id: str, timeout: float = 30.0) -> Optional[DocJob]:
        """Tests and CLI: block until the job finishes."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.get(job_id)
            if job is None or job.status in ("done", "error", "cancelled"):
                return job
            time.sleep(0.05)
        return self.get(job_id)

    def shutdown(self) -> None:
        self.cancel_all()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ worker
    def _step(self, job: DocJob, status: str) -> None:
        if job.cancel.is_set() or self.emergency():
            raise Cancelled()
        job.status = status

    def _run(self, job: DocJob) -> None:
        tmp = ""
        try:
            folder = self.output_dir()
            results: list[SearchResult] = []
            if job.use_web:
                self._step(job, "research")
                results = self._search(job)
            self._step(job, "writing")
            settings = self.settings()
            usable, reason = ai_usable(settings)
            content = None
            if usable:
                try:
                    content = generate_with_ai(job.kind, job.topic, settings, results, self._ai_transport)
                    job.ai_used = True
                except (OllamaError, ValueError) as exc:
                    reason = str(exc)
            if content is None:
                job.warnings.append(f"Текст не составлен моделью: {reason}. Создан шаблон.")
                content = template_content(job.kind, job.topic, results, reason)
            content = attach_sources(content, results)
            job.title, job.sources = content.title, len(content.sources)
            self._step(job, "rendering")
            os.makedirs(folder, exist_ok=True)
            ext = EXTENSIONS[job.kind]
            tmp = os.path.join(folder, f".~arc-{job.id}{ext}")
            render, verify = RENDERERS[job.kind]
            render(content, tmp)
            self._step(job, "verifying")
            check = verify(content, tmp)
            if not check.ok or os.path.getsize(tmp) == 0:
                raise RenderError("Файл не прошёл проверку: " + "; ".join(check.details or ["пустой файл"]))
            final = unique_path(folder, safe_filename(content.title, ext))
            os.replace(tmp, final)
            tmp = ""
            job.path, job.pages, job.details = final, check.pages, check.details
            job.status = "done"
            job.message = self._done_message(job)
        except Cancelled:
            job.status, job.message = "cancelled", "Создание документа отменено."
        except (PathError, RenderError, OnlineError) as exc:
            job.status, job.message = "error", f"Документ не создан: {exc}"
        except Exception as exc:  # a bug in a library must not kill the worker
            log.exception("document job %s failed", job.id)
            job.status, job.message = "error", f"Документ не создан: внутренняя ошибка {type(exc).__name__}"
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            job.finished = time.time()
        if job.status == "done" and self.settings().documents.open_when_ready and self.opener:
            try:
                self.opener(job.path)
            except Exception as exc:
                log.warning("cannot open %s: %s", job.path, exc)
        if self.on_finished:
            try:
                self.on_finished(job)
            except Exception:
                log.exception("on_finished failed")

    def _search(self, job: DocJob) -> list[SearchResult]:
        if self.research is None:
            job.warnings.append("Поиск в интернете недоступен.")
            return []
        try:
            report = self.research.search(job.topic, limit=self.settings().online.max_results)
        except OnlineError as exc:
            job.warnings.append(f"Поиск в интернете не удался: {exc}. Документ составлен без источников.")
            return []
        job.warnings += [f"Поиск: {e}" for e in report.errors]
        return report.results

    @staticmethod
    def _done_message(job: DocJob) -> str:
        parts = [f"Готово: «{job.title}» ({KIND_TITLES[job.kind]}), файл {os.path.basename(job.path)}."]
        if job.sources:
            parts.append(f"Источников: {job.sources}.")
        if not job.ai_used:
            parts.append("Это шаблон: локальная модель не составила текст.")
        return " ".join(parts)
