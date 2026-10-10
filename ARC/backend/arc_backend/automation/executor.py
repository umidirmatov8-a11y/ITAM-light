"""Executes validated catalog actions through the SystemController.

The executor is called only by the Assistant after the Permission Manager allowed the request
(or the user confirmed it). Every handler receives typed parameters.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import urllib.parse
from typing import Callable, Optional

import psutil

from ..apps.registry import AppEntry, AppRegistry, LaunchType
from ..models import ActionRequest, ActionResult, Source, Status
from ..permissions import catalog as c
from ..storage.settings import SettingsStore
from . import sysinfo
from .controller import ControllerError, SystemController
from .files import PathError, PathGuard, is_executable, search_files, validate_folder_name

log = logging.getLogger(__name__)

PROTECTED_PROCESSES = {"system", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
                       "lsass.exe", "svchost.exe", "dwm.exe", "fontdrvhost.exe", "lsaiso.exe", "registry",
                       "memory compression", "msmpeng.exe", "audiodg.exe"}

_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
           "ноября", "декабря"]
_WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def ok(message: str, data: Optional[dict] = None, undo: Optional[ActionRequest] = None,
       repeatable: bool = True) -> ActionResult:
    return ActionResult(ok=True, status=Status.DONE, message=message, data=data or {}, undo=undo,
                        repeatable=repeatable)


def fail(status: Status, message: str, data: Optional[dict] = None) -> ActionResult:
    return ActionResult(ok=False, status=status, message=message, data=data or {})


class Executor:
    def __init__(self, controller: SystemController, registry: AppRegistry, settings: SettingsStore,
                 folders: Callable[[], dict[str, str]], gpu: sysinfo.GpuProbe):
        self.controller = controller
        self.registry = registry
        self.settings = settings
        self.folders = folders
        self.gpu = gpu
        self._handlers: dict[str, Callable[[c.Params, Source], ActionResult]] = {
            "app.launch": self._app_launch,
            "app.launch_admin": self._app_launch_admin,
            "app.close": self._app_close,
            "process.terminate": self._process_terminate,
            "volume.change": self._volume_change,
            "volume.set": self._volume_set,
            "volume.mute": self._volume_mute,
            "window.minimize_all": self._minimize_all,
            "window.restore_all": self._restore_all,
            "system.info": self._system_info,
            "files.search": self._files_search,
            "files.open": self._files_open,
            "files.create_folder": self._create_folder,
            "files.remove_empty_folder": self._remove_empty_folder,
            "explorer.open": self._explorer_open,
            "browser.open_url": self._open_url,
            "web.search": self._web_search,
            "power.shutdown": lambda p, s: self._power("shutdown", p),
            "power.restart": lambda p, s: self._power("restart", p),
            "power.abort": self._power_abort,
            "mode.set": self._mode_set,
            "profile.silent": self._silent,
        }

    def supports(self, action: str) -> bool:
        return action in self._handlers

    def execute(self, action: str, params: c.Params, source: Source) -> ActionResult:
        handler = self._handlers.get(action)
        if handler is None:
            return fail(Status.ERROR, f"Нет обработчика для действия {action}")
        try:
            return handler(params, source)
        except ControllerError as exc:
            return fail(Status.ERROR, str(exc))
        except PathError as exc:
            return fail(Status.DENIED, str(exc))

    # ------------------------------------------------------------------ helpers
    def _guard(self) -> PathGuard:
        return PathGuard(self.settings.get().safety.allowed_dirs)

    def _entry(self, app_id: str) -> AppEntry | ActionResult:
        entry = self.registry.get(app_id)
        if entry is None:
            return fail(Status.NOT_FOUND, "Приложение не найдено в реестре A.R.C.")
        if not entry.enabled:
            return fail(Status.DENIED, f"Запуск «{entry.name}» отключён в реестре")
        return entry

    def _resolve_folder(self, value: str) -> str:
        folders = self.folders()
        if value in folders:
            return folders[value]
        if os.path.isabs(value):
            return value
        raise PathError(f"Неизвестный каталог: {value}")

    # ------------------------------------------------------------------ applications
    def _app_launch(self, p: c.AppParams, source: Source) -> ActionResult:
        entry = self._entry(p.app_id)
        if isinstance(entry, ActionResult):
            return entry
        if entry.run_as_admin:
            return fail(Status.DENIED, "Эта запись запускается только с правами администратора (нужно подтверждение)")
        if entry.process_name:
            pids = self.controller.find_processes(entry.process_name)
            if pids:
                switched = self.controller.activate_window(pids)
                self.registry.mark_launched(entry.id)
                msg = f"«{entry.name}» уже запущен" + (" — переключаю на окно." if switched else ".")
                return ok(msg, {"app": entry.name, "state": "already_running", "pids": pids})
        if entry.launch_type in (LaunchType.EXE, LaunchType.LNK) and not self.controller.path_exists(entry.target):
            return fail(Status.NOT_FOUND, f"Файл «{entry.name}» не найден: {entry.target}. Проверьте путь в реестре.",
                        {"app": entry.name, "state": "missing"})
        if entry.launch_type == LaunchType.EXE:
            if entry.working_dir and not self.controller.is_dir(entry.working_dir):
                return fail(Status.ERROR, f"Рабочий каталог не найден: {entry.working_dir}")
            pid = self.controller.launch_exe(entry.target, entry.args, entry.working_dir or None)
            data = {"pid": pid}
        elif entry.launch_type == LaunchType.LNK:
            self.controller.shell_open(entry.target)
            data = {}
        elif entry.launch_type == LaunchType.UWP:
            self.controller.shell_open("shell:AppsFolder\\" + entry.target)
            data = {}
        else:
            self.controller.shell_open(entry.target)
            data = {}
        self.registry.mark_launched(entry.id)
        return ok(f"Запускаю «{entry.name}».", {"app": entry.name, "state": "launched", **data})

    def _app_launch_admin(self, p: c.AppParams, source: Source) -> ActionResult:
        entry = self._entry(p.app_id)
        if isinstance(entry, ActionResult):
            return entry
        if entry.launch_type != LaunchType.EXE:
            return fail(Status.DENIED, "С правами администратора можно запускать только EXE-файлы")
        if not self.controller.path_exists(entry.target):
            return fail(Status.NOT_FOUND, f"Файл не найден: {entry.target}")
        self.controller.run_as_admin(entry.target, entry.args, entry.working_dir or None)
        self.registry.mark_launched(entry.id)
        return ok(f"Запрос прав администратора для «{entry.name}» отправлен Windows (UAC).",
                  {"app": entry.name, "state": "launched_admin"}, repeatable=False)

    def _app_close(self, p: c.AppParams, source: Source) -> ActionResult:
        entry = self._entry(p.app_id)
        if isinstance(entry, ActionResult):
            return entry
        if not entry.process_name:
            return fail(Status.ERROR, f"Для «{entry.name}» не указано имя процесса — не знаю, что закрыть.")
        if entry.process_name.lower() in PROTECTED_PROCESSES:
            return fail(Status.DENIED, "Системный процесс завершать нельзя")
        pids = self.controller.find_processes(entry.process_name)
        if not pids:
            return ok(f"«{entry.name}» не запущен.", {"app": entry.name, "state": "not_running"}, repeatable=False)
        for pid in pids:
            self.controller.terminate_process(pid)
        return ok(f"«{entry.name}» закрыт.", {"app": entry.name, "pids": pids}, repeatable=False)

    def _process_terminate(self, p: c.ProcessParams, source: Source) -> ActionResult:
        if p.pid == os.getpid() or p.pid == os.getppid():
            return fail(Status.DENIED, "A.R.C. не завершает сам себя этой командой")
        try:
            name = psutil.Process(p.pid).name()
        except psutil.NoSuchProcess:
            return fail(Status.NOT_FOUND, "Процесс уже завершён")
        except psutil.Error:
            name = p.name
        if p.name and name.lower() != p.name.lower():
            return fail(Status.DENIED, "Идентификатор процесса изменился — операция отменена")
        if name.lower() in PROTECTED_PROCESSES:
            return fail(Status.DENIED, "Системный процесс завершать нельзя")
        self.controller.terminate_process(p.pid)
        return ok(f"Процесс {name} ({p.pid}) завершён.", {"pid": p.pid, "name": name}, repeatable=False)

    # ------------------------------------------------------------------ audio
    def _volume_change(self, p: c.VolumeChangeParams, source: Source) -> ActionResult:
        before = self.controller.volume_get()
        if self.controller.mute_get() and p.delta > 0:
            self.controller.mute_set(False)
        self.controller.volume_step(p.delta)
        after = self.controller.volume_get()
        undo = ActionRequest(action="volume.set", params={"level": before}) if before is not None else None
        word = "увеличена" if p.delta > 0 else "уменьшена"
        level = f" до {after}%" if after is not None else ""
        return ok(f"Громкость {word}{level}.", {"before": before, "after": after}, undo)

    def _volume_set(self, p: c.VolumeSetParams, source: Source) -> ActionResult:
        before = self.controller.volume_get()
        self.controller.volume_set(p.level)
        undo = ActionRequest(action="volume.set", params={"level": before}) if before is not None else None
        return ok(f"Громкость {p.level}%.", {"before": before, "after": p.level}, undo)

    def _volume_mute(self, p: c.MuteParams, source: Source) -> ActionResult:
        before = self.controller.mute_get()
        self.controller.mute_set(p.muted)
        undo = ActionRequest(action="volume.mute", params={"muted": before}) if before is not None else None
        return ok("Звук выключен." if p.muted else "Звук включён.", {"muted": p.muted}, undo, repeatable=False)

    # ------------------------------------------------------------------ windows
    def _minimize_all(self, p: c.NoParams, source: Source) -> ActionResult:
        self.controller.minimize_all()
        return ok("Окна свёрнуты.", undo=ActionRequest(action="window.restore_all"))

    def _restore_all(self, p: c.NoParams, source: Source) -> ActionResult:
        self.controller.restore_all()
        return ok("Окна восстановлены.", undo=ActionRequest(action="window.minimize_all"))

    # ------------------------------------------------------------------ information
    def _system_info(self, p: c.SystemInfoParams, source: Source) -> ActionResult:
        now = dt.datetime.now()
        if p.topic == "time":
            return ok(f"Сейчас {now:%H:%M}.", {"time": now.isoformat(timespec="seconds")})
        if p.topic == "date":
            return ok(f"Сегодня {_WEEKDAYS[now.weekday()]}, {now.day} {_MONTHS[now.month - 1]} {now.year} года.",
                      {"date": now.date().isoformat()})
        if p.topic == "disk":
            disks = sysinfo.disks()
            if not disks:
                return fail(Status.ERROR, "Не удалось получить сведения о дисках")
            parts = [f"диск {d['mount'].rstrip(chr(92)).rstrip(':')}: свободно {d['free_gb']:g} из {d['total_gb']:g} ГБ"
                     for d in disks]
            text = "; ".join(parts)
            return ok(text[0].upper() + text[1:] + ".", {"disks": disks})
        if p.topic == "processes":
            programs = sysinfo.running_programs(self.controller.windowed_pids())
            if not programs:
                return ok("Не вижу запущенных программ с окнами.", {"programs": []})
            names = ", ".join(_pretty_process(x["name"]) for x in programs[:12])
            return ok(f"Запущено программ: {len(programs)}. {names}.", {"programs": programs})
        stats = sysinfo.stats(self.gpu)
        if p.topic == "memory":
            ram = stats["ram"]
            return ok(f"Память занята на {ram['percent']:.0f}%: {ram['used_gb']:g} из {ram['total_gb']:g} ГБ.", stats)
        if p.topic == "cpu":
            return ok(f"Загрузка процессора {stats['cpu']:.0f}%.", stats)
        if p.topic == "gpu":
            gpu = stats["gpu"]
            if not gpu:
                return ok("Данные о видеокарте недоступны (нужен драйвер NVIDIA с nvidia-smi).", stats)
            return ok(f"{gpu['name']}: загрузка {gpu['load']:.0f}%, видеопамять {gpu['mem_used_mb']:.0f} из "
                      f"{gpu['mem_total_mb']:.0f} МБ, {gpu['temp_c']:.0f}°C.", stats)
        gpu = stats["gpu"]
        gpu_text = f", видеокарта {gpu['load']:.0f}%" if gpu else ""
        return ok(f"Процессор {stats['cpu']:.0f}%, память {stats['ram']['percent']:.0f}%{gpu_text}.", stats)

    # ------------------------------------------------------------------ files
    def _files_search(self, p: c.FileSearchParams, source: Source) -> ActionResult:
        guard = self._guard()
        if p.scope:
            roots = [guard.check(self._resolve_folder(p.scope))]
        else:
            roots = [r for r in guard.allowed_dirs if os.path.isdir(r)]
        if not roots:
            return fail(Status.DENIED, "Нет разрешённых каталогов для поиска. Добавьте их в «Разрешения».")
        found, truncated = search_files(p.query, roots)
        files = [{"path": f.path, "name": f.name, "size": f.size, "modified": f.modified, "is_dir": f.is_dir}
                 for f in found]
        if not files:
            return ok(f"Файлы по запросу «{p.query}» не найдены в разрешённых каталогах.", {"files": []})
        names = ", ".join(f["name"] for f in files[:5])
        more = " (показаны первые результаты)" if truncated else ""
        return ok(f"Нашёл {len(files)}: {names}{more}.", {"files": files, "truncated": truncated})

    def _files_open(self, p: c.FileOpenParams, source: Source) -> ActionResult:
        path = self._guard().check(p.path)
        if is_executable(path):
            return fail(Status.DENIED, "Исполняемые файлы так не открываются. Добавьте программу в реестр приложений.")
        if not os.path.isfile(path):
            return fail(Status.NOT_FOUND, "Файл не найден")
        self.controller.shell_open(path)
        return ok(f"Открываю {os.path.basename(path)}.", {"path": path})

    def _create_folder(self, p: c.CreateFolderParams, source: Source) -> ActionResult:
        guard = self._guard()
        parent = guard.check(self._resolve_folder(p.parent))
        name = validate_folder_name(p.name)
        path = guard.check(os.path.join(parent, name))
        if os.path.exists(path):
            return fail(Status.ERROR, f"Папка «{name}» уже существует.")
        self.controller.make_dir(path)
        return ok(f"Папка «{name}» создана.", {"path": path},
                  undo=ActionRequest(action="files.remove_empty_folder", params={"path": path}), repeatable=False)

    def _remove_empty_folder(self, p: c.FileOpenParams, source: Source) -> ActionResult:
        path = self._guard().check(p.path)
        self.controller.remove_empty_dir(path)
        return ok(f"Пустая папка «{os.path.basename(path)}» удалена.", {"path": path}, repeatable=False)

    def _explorer_open(self, p: c.ExplorerParams, source: Source) -> ActionResult:
        explorer = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "explorer.exe")
        if p.folder:
            path = self._guard().check(self._resolve_folder(p.folder))
            self.controller.launch_exe(explorer, [path], None)
            return ok(f"Открываю {os.path.basename(path.rstrip(os.sep)) or path}.", {"path": path})
        self.controller.launch_exe(explorer, [], None)
        return ok("Открываю проводник.")

    # ------------------------------------------------------------------ browser
    def _open_url(self, p: c.UrlParams, source: Source) -> ActionResult:
        self.controller.shell_open(p.url)
        host = urllib.parse.urlparse(p.url).netloc
        return ok(f"Открываю {host} в браузере.", {"url": p.url})

    def _web_search(self, p: c.QueryParams, source: Source) -> ActionResult:
        template = self.settings.get().network.search_url
        url = template.replace("{query}", urllib.parse.quote_plus(p.query))
        self.controller.shell_open(url)
        return ok(f"Ищу в интернете: «{p.query}». Результаты открыты в браузере.", {"url": url})

    # ------------------------------------------------------------------ power
    def _power(self, kind: str, p: c.PowerParams) -> ActionResult:
        self.controller.power(kind, p.delay_s)
        what = "выключится" if kind == "shutdown" else "перезагрузится"
        return ok(f"Компьютер {what} через {p.delay_s} с. Скажите «отмени выключение», чтобы отменить.",
                  {"delay_s": p.delay_s}, undo=ActionRequest(action="power.abort"), repeatable=False)

    def _power_abort(self, p: c.NoParams, source: Source) -> ActionResult:
        self.controller.power("abort", 0)
        return ok("Запланированное выключение отменено.", repeatable=False)

    # ------------------------------------------------------------------ modes
    def _mode_set(self, p: c.ModeParams, source: Source) -> ActionResult:
        before = self.settings.get().network.mode.value
        self.settings.update({"network": {"mode": p.mode}})
        text = "Онлайн-режим включён: разрешены запросы в интернет по вашим командам." if p.mode == "ONLINE" \
            else "Локальный режим: A.R.C. не обращается к интернету."
        return ok(text, {"mode": p.mode}, undo=ActionRequest(action="mode.set", params={"mode": before}),
                  repeatable=False)

    def _silent(self, p: c.SilentParams, source: Source) -> ActionResult:
        before = self.settings.get().profile.silent
        self.settings.update({"profile": {"silent": p.enabled}})
        if p.enabled:
            try:
                self.controller.mute_set(True)
            except ControllerError as exc:
                log.warning("mute in silent mode failed: %s", exc)
        text = "Режим тишины включён: звук выключен, голосовые ответы отключены." if p.enabled \
            else "Режим тишины выключен."
        return ok(text, {"silent": p.enabled}, undo=ActionRequest(action="profile.silent", params={"enabled": before}),
                  repeatable=False)


def _pretty_process(name: str) -> str:
    return name[:-4] if name.lower().endswith(".exe") else name

