"""SystemController: the only place that touches the operating system.

`WindowsController` is the real implementation; `MockController` records calls and is used by
tests and on non-Windows development machines. Nothing here accepts shell command strings.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import psutil

log = logging.getLogger(__name__)


class ControllerError(RuntimeError):
    """Expected failure with a user-facing (Russian) message."""


class SystemController(Protocol):
    name: str
    simulated: bool

    def path_exists(self, path: str) -> bool: ...
    def is_dir(self, path: str) -> bool: ...
    def launch_exe(self, path: str, args: list[str], cwd: str | None) -> int: ...
    def run_as_admin(self, path: str, args: list[str], cwd: str | None) -> None: ...
    def shell_open(self, target: str) -> None: ...
    def find_processes(self, process_name: str) -> list[int]: ...
    def activate_window(self, pids: list[int]) -> bool: ...
    def windowed_pids(self) -> Optional[set[int]]: ...
    def terminate_process(self, pid: int) -> None: ...
    def volume_get(self) -> Optional[int]: ...
    def volume_set(self, level: int) -> None: ...
    def volume_step(self, delta: int) -> None: ...
    def mute_get(self) -> Optional[bool]: ...
    def mute_set(self, muted: bool) -> None: ...
    def minimize_all(self) -> None: ...
    def restore_all(self) -> None: ...
    def power(self, kind: str, delay_s: int) -> None: ...
    def make_dir(self, path: str) -> None: ...
    def remove_empty_dir(self, path: str) -> None: ...


def find_processes_psutil(process_name: str) -> list[int]:
    wanted = process_name.lower()
    pids = []
    for proc in psutil.process_iter(["name", "pid"]):
        name = (proc.info.get("name") or "").lower()
        if name == wanted:
            pids.append(proc.info["pid"])
    return pids


# --------------------------------------------------------------------------- mock
@dataclass
class MockController:
    """In-memory controller. Records every call in `calls`; never touches the system."""

    name: str = "mock"
    simulated: bool = True
    existing_paths: set[str] = field(default_factory=set)
    assume_paths_exist: bool = True
    running: dict[str, list[int]] = field(default_factory=dict)
    volume: int = 50
    muted: bool = False
    fail_on: set[str] = field(default_factory=set)
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    _pid: int = 1000

    def _record(self, method: str, *args: Any) -> None:
        self.calls.append((method, args))
        if method in self.fail_on:
            raise ControllerError(f"Сбой (имитация): {method}")

    def called(self, method: str) -> list[tuple[Any, ...]]:
        return [args for name, args in self.calls if name == method]

    def path_exists(self, path: str) -> bool:
        return self.assume_paths_exist or path.lower() in {p.lower() for p in self.existing_paths}

    def is_dir(self, path: str) -> bool:
        return os.path.isdir(path)

    def launch_exe(self, path: str, args: list[str], cwd: str | None) -> int:
        self._record("launch_exe", path, tuple(args), cwd)
        self._pid += 1
        return self._pid

    def run_as_admin(self, path: str, args: list[str], cwd: str | None) -> None:
        self._record("run_as_admin", path, tuple(args), cwd)

    def shell_open(self, target: str) -> None:
        self._record("shell_open", target)

    def find_processes(self, process_name: str) -> list[int]:
        return list(self.running.get(process_name.lower(), []))

    def activate_window(self, pids: list[int]) -> bool:
        self._record("activate_window", tuple(pids))
        return True

    def windowed_pids(self) -> Optional[set[int]]:
        return None

    def terminate_process(self, pid: int) -> None:
        self._record("terminate_process", pid)
        for name, pids in self.running.items():
            if pid in pids:
                pids.remove(pid)

    def volume_get(self) -> Optional[int]:
        return self.volume

    def volume_set(self, level: int) -> None:
        self._record("volume_set", level)
        self.volume = max(0, min(100, level))

    def volume_step(self, delta: int) -> None:
        self._record("volume_step", delta)
        self.volume = max(0, min(100, self.volume + delta))

    def mute_get(self) -> Optional[bool]:
        return self.muted

    def mute_set(self, muted: bool) -> None:
        self._record("mute_set", muted)
        self.muted = muted

    def minimize_all(self) -> None:
        self._record("minimize_all")

    def restore_all(self) -> None:
        self._record("restore_all")

    def power(self, kind: str, delay_s: int) -> None:
        self._record("power", kind, delay_s)

    def make_dir(self, path: str) -> None:
        self._record("make_dir", path)
        try:
            os.makedirs(path, exist_ok=False)
        except OSError as exc:
            raise ControllerError(f"Не удалось создать папку: {exc}")

    def remove_empty_dir(self, path: str) -> None:
        self._record("remove_empty_dir", path)
        try:
            os.rmdir(path)
        except OSError as exc:
            raise ControllerError(f"Не удалось удалить папку: {exc}")


# --------------------------------------------------------------------------- windows
class WindowsController:
    name = "windows"
    simulated = False

    _DETACHED = 0x00000008
    _NEW_GROUP = 0x00000200
    _BREAKAWAY = 0x01000000
    _NO_WINDOW = 0x08000000

    def __init__(self) -> None:
        self._com_lock = threading.Lock()

    # ---- files / processes
    def path_exists(self, path: str) -> bool:
        return os.path.exists(path)

    def is_dir(self, path: str) -> bool:
        return os.path.isdir(path)

    def launch_exe(self, path: str, args: list[str], cwd: str | None) -> int:
        workdir = cwd or os.path.dirname(path) or None
        base = self._DETACHED | self._NEW_GROUP
        for flags in (base | self._BREAKAWAY, base):
            try:
                proc = subprocess.Popen([path, *args], cwd=workdir, shell=False, close_fds=True,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, creationflags=flags)
                return proc.pid
            except PermissionError:
                if flags & self._BREAKAWAY:
                    continue  # the job object does not allow breakaway
                raise ControllerError("Нет прав на запуск программы")
            except OSError as exc:
                if getattr(exc, "winerror", None) == 740:
                    raise ControllerError("Программа требует прав администратора. "
                                          "Включите «запуск от имени администратора» в реестре A.R.C.")
                if flags & self._BREAKAWAY and getattr(exc, "winerror", None) == 5:
                    continue
                raise ControllerError(f"Не удалось запустить: {exc.strerror or exc}")
        raise ControllerError("Не удалось запустить программу")

    def run_as_admin(self, path: str, args: list[str], cwd: str | None) -> None:
        import ctypes
        params = subprocess.list2cmdline(args)
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", path, params or None,
                                                 cwd or os.path.dirname(path), 1)
        if rc <= 32:
            raise ControllerError("Запуск с правами администратора отменён или не удался")

    def shell_open(self, target: str) -> None:
        try:
            os.startfile(target)  # type: ignore[attr-defined]
        except OSError as exc:
            raise ControllerError(f"Не удалось открыть: {exc.strerror or exc}")

    def find_processes(self, process_name: str) -> list[int]:
        return find_processes_psutil(process_name)

    def activate_window(self, pids: list[int]) -> bool:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        wanted = set(pids)
        found: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) == 0:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in wanted:
                found.append(hwnd)
                return False
            return True

        user32.EnumWindows(callback, 0)
        if not found:
            return False
        hwnd = found[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True

    def windowed_pids(self) -> Optional[set[int]]:
        """PIDs owning a visible top-level window with a title (what the user calls "programs")."""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        pids: set[int] = set()

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0 \
                    and not user32.GetWindow(hwnd, 4):  # GW_OWNER: skip owned dialogs
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                pids.add(pid.value)
            return True

        user32.EnumWindows(callback, 0)
        return pids

    def terminate_process(self, pid: int) -> None:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            raise ControllerError("Процесс не завершился за 5 секунд")
        except psutil.NoSuchProcess:
            return
        except psutil.AccessDenied:
            raise ControllerError("Нет прав на завершение процесса")

    # ---- audio (pycaw if available, media keys otherwise)
    def _endpoint(self):
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore
        except ImportError:
            return None
        try:
            speakers = AudioUtilities.GetSpeakers()
            if speakers is None:
                raise OSError("no default render device")
            endpoint = getattr(speakers, "EndpointVolume", None)
            if endpoint is not None:
                return endpoint
            from ctypes import POINTER, cast
            from comtypes import CLSCTX_ALL  # type: ignore
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(interface, POINTER(IAudioEndpointVolume))
        except Exception as exc:  # COMError when there is no audio device
            log.warning("audio endpoint unavailable: %s", exc)
            raise ControllerError("Не найдено устройство вывода звука")

    def _with_audio(self, fn):
        try:
            import comtypes  # type: ignore
        except ImportError:
            return fn(None)
        with self._com_lock:
            comtypes.CoInitialize()
            try:
                return fn(self._endpoint())
            finally:
                comtypes.CoUninitialize()

    def volume_get(self) -> Optional[int]:
        try:
            return self._with_audio(lambda ep: None if ep is None else round(ep.GetMasterVolumeLevelScalar() * 100))
        except ControllerError:
            return None

    def volume_set(self, level: int) -> None:
        level = max(0, min(100, level))

        def apply(ep):
            if ep is None:
                raise ControllerError("Точная установка громкости недоступна (не установлен pycaw)")
            ep.SetMasterVolumeLevelScalar(level / 100.0, None)
        self._with_audio(apply)

    def volume_step(self, delta: int) -> None:
        def apply(ep):
            if ep is not None:
                current = round(ep.GetMasterVolumeLevelScalar() * 100)
                ep.SetMasterVolumeLevelScalar(max(0, min(100, current + delta)) / 100.0, None)
            else:
                key = 0xAF if delta > 0 else 0xAE  # VK_VOLUME_UP / VK_VOLUME_DOWN, 2% per press
                for _ in range(max(1, abs(delta) // 2)):
                    self._press(key)
        self._with_audio(apply)

    def mute_get(self) -> Optional[bool]:
        try:
            return self._with_audio(lambda ep: None if ep is None else bool(ep.GetMute()))
        except ControllerError:
            return None

    def mute_set(self, muted: bool) -> None:
        def apply(ep):
            if ep is not None:
                ep.SetMute(int(muted), None)
            else:
                self._press(0xAD)  # VK_VOLUME_MUTE toggles
        self._with_audio(apply)

    @staticmethod
    def _press(vk: int, *modifiers: int) -> None:
        import ctypes
        user32 = ctypes.windll.user32
        for mod in modifiers:
            user32.keybd_event(mod, 0, 0, 0)
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)
        for mod in reversed(modifiers):
            user32.keybd_event(mod, 0, 2, 0)

    # ---- windows
    def _shell_app(self, method: str) -> bool:
        try:
            import comtypes  # type: ignore
            import comtypes.client  # type: ignore
        except ImportError:
            return False
        comtypes.CoInitialize()
        try:
            getattr(comtypes.client.CreateObject("Shell.Application", dynamic=True), method)()
            return True
        except Exception as exc:  # COM errors are not worth crashing for; fall back to keys
            log.warning("Shell.Application.%s failed: %s", method, exc)
            return False
        finally:
            comtypes.CoUninitialize()

    def minimize_all(self) -> None:
        if not self._shell_app("MinimizeAll"):
            self._press(0x4D, 0x5B)  # Win+M

    def restore_all(self) -> None:
        if not self._shell_app("UndoMinimizeALL"):
            self._press(0x4D, 0x5B, 0x10)  # Win+Shift+M

    # ---- power
    def power(self, kind: str, delay_s: int) -> None:
        flags = {"shutdown": ["/s", "/t", str(delay_s)], "restart": ["/r", "/t", str(delay_s)], "abort": ["/a"]}
        if kind not in flags:
            raise ControllerError("Неизвестная операция питания")
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        result = subprocess.run([os.path.join(system_root, "System32", "shutdown.exe"), *flags[kind]],
                                capture_output=True, timeout=10, creationflags=self._NO_WINDOW)
        if result.returncode != 0 and kind != "abort":
            raise ControllerError("Команда завершения работы не выполнена")

    # ---- folders
    def make_dir(self, path: str) -> None:
        try:
            os.makedirs(path, exist_ok=False)
        except FileExistsError:
            raise ControllerError("Папка уже существует")
        except OSError as exc:
            raise ControllerError(f"Не удалось создать папку: {exc.strerror or exc}")

    def remove_empty_dir(self, path: str) -> None:
        try:
            os.rmdir(path)
        except OSError as exc:
            raise ControllerError(f"Не удалось удалить папку (она не пуста?): {exc.strerror or exc}")


def create_controller(force_mock: bool = False) -> SystemController:
    if force_mock or sys.platform != "win32":
        return MockController(assume_paths_exist=False)
    return WindowsController()
