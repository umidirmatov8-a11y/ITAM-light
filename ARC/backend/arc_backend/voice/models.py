"""Catalog and installer of local speech models.

Nothing is downloaded automatically: `ModelManager.start_download` is called only from the
UI after the user confirmed the size. Downloads go to a temporary directory and are moved
into place atomically, so a cancelled or broken download never looks installed.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import httpx

log = logging.getLogger(__name__)

Kind = Literal["stt", "tts_runtime", "tts_voice"]
HF = "https://huggingface.co"
PIPER_VOICES = f"{HF}/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU"
WHISPER_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")


@dataclass(frozen=True)
class ModelSpec:
    id: str
    title: str
    kind: Kind
    size_mb: int
    files: tuple[tuple[str, str], ...]          # (url, relative path)
    description: str = ""
    license: str = ""
    platform: Optional[str] = None              # "win32" if the model only works on Windows
    archive: bool = False                       # files are zip archives to extract
    marker: str = ""                            # file that proves the model is installed


def _whisper(size: str, mb: int, note: str) -> ModelSpec:
    repo = f"{HF}/Systran/faster-whisper-{size}/resolve/main"
    return ModelSpec(id=f"whisper-{size}", title=f"Whisper {size}", kind="stt", size_mb=mb,
                     files=tuple((f"{repo}/{name}", name) for name in WHISPER_FILES),
                     description=note, license="MIT (OpenAI Whisper, конвертация Systran)", marker="model.bin")


def _voice(name: str, title: str) -> ModelSpec:
    base = f"{PIPER_VOICES}/{name}/medium/ru_RU-{name}-medium"
    return ModelSpec(id=f"piper-ru-{name}", title=f"Голос Piper: {title}", kind="tts_voice", size_mb=63,
                     files=((f"{base}.onnx", "voice.onnx"), (f"{base}.onnx.json", "voice.onnx.json")),
                     description="Русский голос для ответов A.R.C. (нужен «Piper — программа»)",
                     license="см. карточку голоса rhasspy/piper-voices", marker="voice.onnx")


CATALOG: dict[str, ModelSpec] = {m.id: m for m in [
    _whisper("tiny", 75, "Самая быстрая, низкое качество русской речи"),
    _whisper("base", 145, "Быстрая, приемлемо для коротких команд"),
    _whisper("small", 484, "Рекомендуется: хороший русский, работает и на CPU"),
    _whisper("medium", 1530, "Лучшее качество, рекомендуется с видеокартой NVIDIA"),
    ModelSpec(id="piper-runtime", title="Piper — программа синтеза речи", kind="tts_runtime", size_mb=22,
              files=(("https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip",
                      "piper.zip"),),
              description="Локальный синтез речи (запускается как отдельная программа)", license="MIT",
              platform="win32", archive=True, marker="piper/piper.exe"),
    _voice("irina", "Ирина"),
    _voice("dmitri", "Дмитрий"),
    _voice("denis", "Денис"),
]}


@dataclass
class DownloadState:
    id: str
    state: Literal["downloading", "done", "error", "cancelled"] = "downloading"
    done_bytes: int = 0
    total_bytes: int = 0
    message: str = ""
    started: float = field(default_factory=time.time)
    cancel: threading.Event = field(default_factory=threading.Event)

    def view(self) -> dict:
        total = self.total_bytes or 1
        return {"state": self.state, "done_mb": round(self.done_bytes / 2**20, 1),
                "total_mb": round(self.total_bytes / 2**20, 1), "progress": min(1.0, self.done_bytes / total),
                "message": self.message}


class DownloadError(RuntimeError):
    pass


def safe_extract(archive: Path, dest: Path) -> None:
    """Extracts a zip refusing absolute paths and `..` (zip-slip)."""
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if not str(target).startswith(str(root) + os.sep) and target != root:
                raise DownloadError(f"Небезопасный путь в архиве: {member.filename}")
        zf.extractall(dest)


class ModelManager:
    def __init__(self, models_dir: Path, catalog: Optional[dict[str, ModelSpec]] = None,
                 http_timeout: float = 60.0):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.catalog = catalog or CATALOG
        self._timeout = http_timeout
        self._lock = threading.Lock()
        self._jobs: dict[str, DownloadState] = {}

    # ------------------------------------------------------------------ queries
    def path(self, model_id: str) -> Path:
        if model_id not in self.catalog:
            raise KeyError(model_id)
        return self.models_dir / model_id

    def installed(self, model_id: str) -> bool:
        spec = self.catalog.get(model_id)
        return bool(spec) and (self.path(model_id) / spec.marker).is_file()

    def free_mb(self) -> float:
        return shutil.disk_usage(self.models_dir).free / 2**20

    def list(self) -> list[dict]:
        result = []
        for spec in self.catalog.values():
            job = self._jobs.get(spec.id)
            result.append({
                "id": spec.id, "title": spec.title, "kind": spec.kind, "size_mb": spec.size_mb,
                "description": spec.description, "license": spec.license,
                "supported": spec.platform in (None, sys.platform),
                "installed": self.installed(spec.id),
                "download": job.view() if job else None,
            })
        return result

    # ------------------------------------------------------------------ download
    def start_download(self, model_id: str, *, online_allowed: bool) -> DownloadState:
        spec = self.catalog.get(model_id)
        if spec is None:
            raise DownloadError("Неизвестная модель")
        if not online_allowed:
            raise DownloadError("Онлайн-функции отключены в настройках: загрузка моделей невозможна")
        if spec.platform and spec.platform != sys.platform:
            raise DownloadError("Эта модель доступна только для Windows")
        if self.installed(model_id):
            raise DownloadError("Модель уже установлена")
        need = spec.size_mb * (2.3 if spec.archive else 1.2) + 200
        if self.free_mb() < need:
            raise DownloadError(f"Недостаточно места: нужно ~{need:.0f} МБ, свободно {self.free_mb():.0f} МБ")
        with self._lock:
            job = self._jobs.get(model_id)
            if job and job.state == "downloading":
                return job
            job = DownloadState(id=model_id, total_bytes=spec.size_mb * 2**20)
            self._jobs[model_id] = job
        threading.Thread(target=self._run, args=(spec, job), name=f"download-{model_id}", daemon=True).start()
        return job

    def cancel(self, model_id: str) -> bool:
        job = self._jobs.get(model_id)
        if job and job.state == "downloading":
            job.cancel.set()
            return True
        return False

    def wait(self, model_id: str, timeout: float = 600) -> DownloadState:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self._jobs.get(model_id)
            if job is None or job.state != "downloading":
                return job  # type: ignore[return-value]
            time.sleep(0.05)
        raise TimeoutError(model_id)

    def remove(self, model_id: str) -> bool:
        path = self.path(model_id)
        if self._jobs.get(model_id) and self._jobs[model_id].state == "downloading":
            raise DownloadError("Модель загружается — сначала отмените загрузку")
        if path.exists():
            shutil.rmtree(path)
            self._jobs.pop(model_id, None)
            return True
        return False

    def _run(self, spec: ModelSpec, job: DownloadState) -> None:
        tmp = self.models_dir / f".{spec.id}.partial"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        try:
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(self._timeout, connect=15.0)) as client:
                sizes = []
                for url, _rel in spec.files:
                    head = client.head(url)
                    sizes.append(int(head.headers.get("content-length") or 0))
                if all(sizes):
                    job.total_bytes = sum(sizes)
                for url, rel in spec.files:
                    self._fetch(client, url, tmp / rel, job)
            for _url, rel in spec.files:
                if spec.archive:
                    safe_extract(tmp / rel, tmp)
                    (tmp / rel).unlink()
            if not (tmp / spec.marker).is_file():
                raise DownloadError(f"После загрузки не найден файл {spec.marker}")
            final = self.path(spec.id)
            shutil.rmtree(final, ignore_errors=True)
            os.replace(tmp, final)
            job.state, job.message = "done", "Установлено"
            log.info("model %s installed (%d bytes)", spec.id, job.done_bytes)
        except _Cancelled:
            job.state, job.message = "cancelled", "Загрузка отменена"
        except (httpx.HTTPError, OSError, DownloadError, zipfile.BadZipFile) as exc:
            job.state = "error"
            job.message = f"Ошибка загрузки: {exc}"
            log.warning("model %s download failed: %s", spec.id, exc)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)

    def _fetch(self, client: httpx.Client, url: str, dest: Path, job: DownloadState) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with client.stream("GET", url) as response:
            response.raise_for_status()
            expected = int(response.headers.get("content-length") or 0)
            written = 0
            with open(dest, "wb") as fh:
                for chunk in response.iter_bytes(1 << 16):
                    if job.cancel.is_set():
                        raise _Cancelled()
                    fh.write(chunk)
                    written += len(chunk)
                    job.done_bytes += len(chunk)
        if expected and written != expected:
            raise DownloadError(f"Файл загружен не полностью: {dest.name}")


class _Cancelled(Exception):
    pass
