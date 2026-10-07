"""Built-in local model: llama.cpp's llama-server + GGUF weights shipped next to AgentLoop.exe.

Installed layout (see installer/AgentLoop.iss):

    AgentLoop.exe
    runtime/llama-server.exe (+ its DLLs)
    models/*.gguf

The server is started lazily on a free localhost port, hidden (no console window), and stopped
when AgentLoop exits. Requests go through its OpenAI-compatible /v1/chat/completions endpoint.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.config import Settings
from app.providers import ProviderError

SERVER_NAMES = ("llama-server.exe", "llama-server")


def app_home() -> Path:
    """Folder that holds runtime/ and models/: next to the exe, or the project folder from sources."""
    override = os.environ.get("AGENTLOOP_HOME")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def find_server(home: Path | None = None) -> Path | None:
    runtime = (home or app_home()) / "runtime"
    for name in SERVER_NAMES:
        candidate = runtime / name
        if candidate.is_file():
            return candidate
    return None


def list_local_models(home: Path | None = None) -> list[Path]:
    models = (home or app_home()) / "models"
    return sorted(models.glob("*.gguf")) if models.is_dir() else []


def resolve_model(settings: Settings, home: Path | None = None) -> Path | None:
    """The model chosen in settings (file name or full path), else the first bundled one."""
    if settings.local_model:
        chosen = Path(settings.local_model)
        if not chosen.is_absolute():
            chosen = (home or app_home()) / "models" / chosen
        return chosen if chosen.is_file() else None
    models = list_local_models(home)
    return models[0] if models else None


def _kill_with_parent(process: subprocess.Popen) -> None:
    """Windows: put the child in a job object that is closed (and the child killed) when AgentLoop dies,
    even if it crashes or is killed from Task Manager. Best effort; elsewhere atexit handles it."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount",
                        "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC_LIMIT(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED_LIMIT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.OpenProcess.restype = wintypes.HANDLE
        job = kernel32.CreateJobObjectW(None, None)
        info = EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info))
        handle = kernel32.OpenProcess(0x0001 | 0x0100, False, process.pid)  # PROCESS_TERMINATE | SET_QUOTA
        kernel32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(handle))
        kernel32.CloseHandle(wintypes.HANDLE(handle))
        _JOBS.append(job)  # the handle must stay open for the lifetime of AgentLoop
    except Exception:
        pass


_JOBS: list = []


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


GPU_AUTO = "auto"  # use a Vulkan GPU when there is one, otherwise (or if it fails) the CPU
GPU_OFF = "cpu"

# Launch variants, best first. The Vulkan build of llama-server also contains the CPU backend and loads
# ggml-vulkan.dll dynamically: without a Vulkan driver/GPU it silently runs on the CPU.
GPU_ARGS = ["-ngl", "999"]
CPU_ARGS = [["--device", "none", "-ngl", "0"], ["-ngl", "0"]]  # second form for builds without --device none

# "ggml_vulkan: 0 = Intel(R) Iris(R) Xe Graphics (Intel Corporation) | uma: 1 | ..." -> name without the driver
_LISTED_DEVICE = re.compile(r"^\s*([A-Za-z]+\d+): (.+?)(?: \(\d+ MiB.*\))?\s*$")
_VK_DEVICE = re.compile(r"ggml_vulkan: \d+ = ([^|\n]+?)(?: \([^()|\n]*\))? \|")
_OFFLOADED = re.compile(r"offloaded (\d+)/(\d+) layers to GPU")


_DEVICE_CACHE: dict[Path, list[str]] = {}


def list_gpus(server: Path) -> list[str]:
    """GPU names llama-server can use (`llama-server --list-devices`), e.g. ["NVIDIA GeForce RTX 3060"]."""
    if server not in _DEVICE_CACHE:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            out = subprocess.run([str(server), "--list-devices"], capture_output=True, timeout=60,
                                 cwd=str(server.parent), creationflags=flags, stdin=subprocess.DEVNULL)
            text = (out.stdout + out.stderr).decode("utf-8", "replace")
        except (OSError, subprocess.TimeoutExpired):
            text = ""
        names = []
        for line in text.splitlines():
            match = _LISTED_DEVICE.match(line)
            if match and not match.group(1).upper().startswith("CPU"):
                names.append(match.group(2).strip())
        _DEVICE_CACHE[server] = names
    return _DEVICE_CACHE[server]


class LlamaServer:
    """One llama-server process per (model, context size, GPU mode); shared by all agents."""

    _lock = threading.Lock()
    _instance: "LlamaServer | None" = None
    gpu_failed = False  # a GPU launch crashed in this session: stay on the CPU

    def __init__(self, server: Path, model: Path, num_ctx: int, extra_args: list[str], uses_gpu: bool):
        self.server, self.model, self.num_ctx = server, model, num_ctx
        self.uses_gpu = uses_gpu
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        log_dir = Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp")
        # One log per mode, so a failed GPU attempt's log survives the CPU fallback.
        self.log_path = log_dir / f"agentloop-llama-server-{'gpu' if uses_gpu else 'cpu'}.log"
        args = [str(server), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
                "-c", str(num_ctx), "-np", "1", *extra_args]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._log = open(self.log_path, "wb")
        try:
            self.process = subprocess.Popen(args, stdout=self._log, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, cwd=str(server.parent), creationflags=flags)
        except OSError as exc:
            self._log.close()
            raise ProviderError(f"Не удалось запустить встроенный движок {server.name}: {exc}") from exc
        _kill_with_parent(self.process)

    @classmethod
    def get(cls, server: Path, model: Path, num_ctx: int, gpu_mode: str = GPU_AUTO, timeout: float = 300.0,
            cancel: threading.Event | None = None) -> "LlamaServer":
        with cls._lock:
            want_gpu = gpu_mode != GPU_OFF and not cls.gpu_failed and bool(list_gpus(server))
            current = cls._instance
            if (current and current.alive() and (current.model, current.num_ctx) == (model, num_ctx)
                    and current.uses_gpu == want_gpu):
                return current
            if current:
                current.stop()
                cls._instance = None
            attempts = ([(GPU_ARGS, True)] if want_gpu else []) + [(a, False) for a in CPU_ARGS]
            errors = []
            for args, uses_gpu in attempts:
                candidate = cls(server, model, num_ctx, args, uses_gpu)
                try:
                    candidate.wait_ready(timeout, cancel)
                except ProviderError as exc:
                    candidate.stop()
                    if cancel is not None and cancel.is_set():
                        raise
                    errors.append(str(exc))
                    if uses_gpu:
                        cls.gpu_failed = True
                    continue
                cls._instance = candidate
                return candidate
            raise ProviderError(errors[-1])

    @classmethod
    def shutdown(cls) -> None:
        with cls._lock:
            if cls._instance:
                cls._instance.stop()
                cls._instance = None

    def alive(self) -> bool:
        return self.process.poll() is None

    def wait_ready(self, timeout: float, cancel: threading.Event | None = None) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                raise ProviderError("Запуск модели остановлен")
            if not self.alive():
                raise ProviderError(f"Встроенный движок завершился при загрузке модели. Журнал: {self.log_path}\n"
                                    + self.log_tail())
            try:
                with urllib.request.urlopen(f"{self.url}/health", timeout=2) as resp:
                    if resp.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                pass  # 503 while the model is loading, or not listening yet
            time.sleep(0.5)
        raise ProviderError(f"Модель не загрузилась за {int(timeout)} с. Журнал: {self.log_path}")

    def log_text(self) -> str:
        try:
            return self.log_path.read_text("utf-8", "replace")
        except OSError:
            return ""

    def log_tail(self, lines: int = 15) -> str:
        return "\n".join(self.log_text().splitlines()[-lines:])

    def device(self) -> str:
        """Human-readable device the model runs on, from the server log."""
        return describe_device(self.log_text(), list_gpus(self.server) if self.uses_gpu else [])

    def stop(self) -> None:
        if self.alive():
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self._log.close()


def describe_device(log: str, gpus: list[str]) -> str:
    """`gpus` is empty when the server runs on the CPU only."""
    offloaded = _OFFLOADED.search(log)
    if not gpus or (offloaded and int(offloaded.group(1)) == 0):
        return "процессор"
    named = _VK_DEVICE.search(log)
    text = f"видеокарта {named.group(1).strip() if named else gpus[0]}"
    if offloaded:
        text += f" ({offloaded.group(1)}/{offloaded.group(2)} слоёв)"
    return text


atexit.register(LlamaServer.shutdown)


class LocalModelProvider:
    name = "Встроенная модель"

    def __init__(self, settings: Settings, home: Path | None = None, timeout: float = 1800.0):
        server = find_server(home)
        if server is None:
            raise ProviderError("Встроенный движок не найден (папка runtime рядом с AgentLoop.exe). "
                                "Переустановите программу или выберите другую нейросеть в настройках.")
        model = resolve_model(settings, home)
        if model is None:
            raise ProviderError("Не найдена модель .gguf в папке models рядом с AgentLoop.exe")
        self.server_path, self.model_path = server, model
        self.model = model.name
        self.num_ctx = settings.num_ctx
        self.gpu_mode = settings.gpu_mode
        self.timeout = timeout

    def start(self, cancel: threading.Event | None = None) -> LlamaServer:
        return LlamaServer.get(self.server_path, self.model_path, self.num_ctx, self.gpu_mode, cancel=cancel)

    def complete(self, system: str, user: str, schema: dict | None = None) -> str:
        server = self.start()
        try:
            return self._chat(server, system, user, schema)
        except ProviderError:
            if not (server.uses_gpu and not server.alive()):
                raise
        # The GPU driver crashed mid-answer: continue on the CPU for the rest of the session.
        LlamaServer.gpu_failed = True
        return self._chat(self.start(), system, user, schema)

    def _chat(self, server: LlamaServer, system: str, user: str, schema: dict | None) -> str:
        payload: dict = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2 if schema is not None else 0.7,
        }
        if schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "verdict", "schema": schema}}
        request = urllib.request.Request(f"{server.url}/v1/chat/completions",
                                         data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ProviderError(f"Встроенная модель вернула ошибку {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError(f"Встроенная модель не отвечает. Журнал: {server.log_path}\n{server.log_tail()}") from exc
        except ValueError as exc:
            raise ProviderError("Встроенная модель вернула некорректный ответ") from exc
        try:
            text = str(data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Встроенная модель вернула ответ неожиданного формата") from exc
        if not text:
            raise ProviderError("Пустой ответ модели")
        return text
