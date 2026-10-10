"""Windows Security event log collection from domain controllers.

LDAP does not expose the Security log. This module uses the built-in Windows tool ``wevtutil.exe`` (remote query over
the Event Log RPC interface) with the *current Windows logon credentials* — no password is passed on a command line.

Requirements (checked explicitly, nothing is simulated):
* Windows workstation (wevtutil.exe present);
* network access to the DC: TCP 135 (RPC endpoint mapper) + dynamic RPC ports, firewall rule
  "Remote Event Log Management (RPC)" enabled on the DC;
* the Windows account running the application is a member of "Event Log Readers" on the DCs (or a domain admin).
  Use ``runas /netonly /user:DOMAIN\\account ADAdminToolkit.exe`` to run under another account.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import ExternalToolError, UnsupportedFeatureError, ValidationError
from ..security.masking import mask_text
from . import network_service as N

NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}

# event id -> (title, severity)
EVENT_CATALOG: dict[int, tuple[str, str]] = {
    4624: ("Успешный вход", "info"),
    4625: ("Неудачный вход", "medium"),
    4634: ("Выход из системы", "info"),
    4648: ("Вход с явными учётными данными", "low"),
    4672: ("Вход с привилегиями администратора", "low"),
    4720: ("Создана учётная запись пользователя", "medium"),
    4722: ("Учётная запись включена", "low"),
    4723: ("Попытка смены пароля", "low"),
    4724: ("Попытка сброса пароля", "medium"),
    4725: ("Учётная запись отключена", "low"),
    4726: ("Учётная запись удалена", "high"),
    4727: ("Создана глобальная группа безопасности", "medium"),
    4728: ("Добавлен член глобальной группы безопасности", "medium"),
    4729: ("Удалён член глобальной группы безопасности", "low"),
    4731: ("Создана локальная группа безопасности", "medium"),
    4732: ("Добавлен член локальной группы безопасности", "medium"),
    4733: ("Удалён член локальной группы безопасности", "low"),
    4738: ("Изменена учётная запись пользователя", "low"),
    4740: ("Учётная запись заблокирована", "high"),
    4741: ("Создана учётная запись компьютера", "low"),
    4743: ("Удалена учётная запись компьютера", "medium"),
    4756: ("Добавлен член универсальной группы безопасности", "medium"),
    4757: ("Удалён член универсальной группы безопасности", "low"),
    4767: ("Учётная запись разблокирована", "low"),
    4768: ("Запрошен билет Kerberos TGT", "info"),
    4769: ("Запрошен сервисный билет Kerberos", "info"),
    4771: ("Ошибка предварительной проверки Kerberos", "medium"),
    4776: ("Проверка учётных данных NTLM", "info"),
    4781: ("Изменено имя учётной записи", "medium"),
    4794: ("Попытка установить пароль DSRM", "high"),
    5136: ("Изменён объект службы каталогов", "low"),
    1102: ("Журнал аудита очищен", "critical"),
}

EVENT_GROUPS = {
    "Блокировки и неудачные входы": [4740, 4625, 4771, 4767],
    "Управление учётными записями": [4720, 4722, 4723, 4724, 4725, 4726, 4738, 4781],
    "Изменения групп": [4727, 4728, 4729, 4731, 4732, 4733, 4756, 4757],
    "Компьютеры": [4741, 4743],
    "Критичные события": [1102, 4794, 4726],
    "Успешные входы (большой объём!)": [4624, 4672],
    "Kerberos/NTLM": [4768, 4769, 4771, 4776],
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SEVERITY_LABEL = {"critical": "Критический", "high": "Высокий", "medium": "Средний", "low": "Низкий", "info": "Информация"}

_SAFE_USER = re.compile(r"^[A-Za-z0-9 ._$@\-Ѐ-ӿ]{1,104}$")


@dataclass
class SecurityEvent:
    dc: str
    time: datetime | None
    event_id: int
    title: str
    severity: str
    target_user: str = ""
    subject_user: str = ""
    source: str = ""
    status: str = ""
    message: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class EventQuery:
    dcs: list[str]
    event_ids: list[int]
    hours: int = 24
    user: str = ""
    max_events: int = 500
    min_severity: str = "info"
    timeout_s: int = 60


@dataclass
class EventResult:
    events: list[SecurityEvent]
    errors: dict[str, str] = field(default_factory=dict)
    requirements: list[str] = field(default_factory=list)


REQUIREMENTS_TEXT = [
    "Windows с утилитой wevtutil.exe (входит в состав Windows).",
    "Сетевой доступ к контроллерам: TCP 135 и динамические RPC-порты; правило «Удалённое управление журналом событий (RPC)».",
    "Учётная запись Windows, под которой запущено приложение, — член группы «Читатели журнала событий» (Event Log Readers) на DC.",
    "Для запуска под другой учётной записью: runas /netonly /user:ДОМЕН\\учётная_запись ADAdminToolkit.exe",
    "Политика аудита на DC должна включать нужные подкатегории (Account Lockout, User Account Management, Logon и т.д.).",
]


def availability() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Сбор журналов Windows доступен только при запуске на Windows"
    if not shutil.which("wevtutil"):
        return False, "Не найдена утилита wevtutil.exe"
    return True, "wevtutil.exe найден"


def build_xpath(event_ids: list[int], hours: int, user: str = "") -> str:
    if not event_ids:
        raise ValidationError("Не выбраны коды событий")
    ids = sorted({int(i) for i in event_ids})
    if any(i <= 0 or i > 65535 for i in ids):
        raise ValidationError("Некорректный код события")
    if not (1 <= int(hours) <= 24 * 90):
        raise ValidationError("Период должен быть от 1 часа до 90 суток")
    id_expr = " or ".join(f"EventID={i}" for i in ids)
    ms = int(hours) * 3600 * 1000
    xpath = f"*[System[({id_expr}) and TimeCreated[timediff(@SystemTime) <= {ms}]]]"
    user = (user or "").strip()
    if user:
        if "\\" in user:
            user = user.split("\\", 1)[1]
        if not _SAFE_USER.match(user) or "'" in user or '"' in user:
            raise ValidationError("Имя пользователя для фильтра содержит недопустимые символы")
        xpath = (f"*[System[({id_expr}) and TimeCreated[timediff(@SystemTime) <= {ms}]] and "
                 f"EventData[Data[@Name='TargetUserName']='{user}']]")
    return xpath


def parse_events_xml(dc: str, text: str) -> list[SecurityEvent]:
    """Parse the output of ``wevtutil qe ... /f:xml`` (concatenated <Event> elements)."""
    text = text.strip()
    if not text:
        return []
    root = ET.fromstring(f"<Events>{text}</Events>")
    out = []
    for ev in root.findall("e:Event", NS):
        sys_el = ev.find("e:System", NS)
        if sys_el is None:
            continue
        eid = int((sys_el.findtext("e:EventID", default="0", namespaces=NS) or "0").strip())
        tc = sys_el.find("e:TimeCreated", NS)
        ts = None
        if tc is not None and tc.get("SystemTime"):
            raw = tc.get("SystemTime").rstrip("Z")
            raw = raw[:26]
            try:
                ts = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
            except ValueError:
                ts = None
        data = {}
        for d in ev.findall("e:EventData/e:Data", NS):
            name = d.get("Name") or f"Data{len(data)}"
            data[name] = (d.text or "").strip()
        title, sev = EVENT_CATALOG.get(eid, (f"Событие {eid}", "info"))
        target = data.get("TargetUserName", "")
        tdom = data.get("TargetDomainName", "")
        subject = data.get("SubjectUserName", "")
        sdom = data.get("SubjectDomainName", "")
        source = data.get("IpAddress") or data.get("WorkstationName") or data.get("CallerComputerName") or ""
        status = data.get("Status") or data.get("FailureReason") or data.get("SubStatus") or ""
        if eid == 4740:
            source = data.get("TargetDomainName", source)  # caller computer is stored in TargetDomainName for 4740
            tdom = ""
        if eid in (4728, 4729, 4732, 4733, 4756, 4757):
            member = data.get("MemberName", "")
            msg = f"Группа: {target}; участник: {member}"
        else:
            msg = ""
        out.append(SecurityEvent(dc=dc, time=ts, event_id=eid, title=title, severity=sev,
                                 target_user=f"{tdom}\\{target}" if tdom and target else target,
                                 subject_user=f"{sdom}\\{subject}" if sdom and subject else subject,
                                 source=source, status=status, message=msg, data=data))
    return out


class EventsService:
    def __init__(self, runner=None):
        self._runner = runner or self._run_wevtutil

    @staticmethod
    def _run_wevtutil(dc: str, xpath: str, count: int, timeout: int) -> str:
        cmd = ["wevtutil", "qe", "Security", f"/r:{dc}", f"/q:{xpath}", "/f:xml", "/rd:true", f"/c:{int(count)}"]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=flags, shell=False)
        except subprocess.TimeoutExpired:
            raise ExternalToolError(f"Тайм-аут запроса журнала ({timeout} с) к {dc}") from None
        except FileNotFoundError:
            raise UnsupportedFeatureError("wevtutil.exe не найден") from None
        if proc.returncode != 0:
            err = proc.stderr.decode("cp866", "replace") or proc.stdout.decode("cp866", "replace")
            low = err.lower()
            if "access is denied" in low or "отказано в доступе" in low:
                hint = "Нет прав чтения журнала Security: добавьте учётную запись в «Event Log Readers» на DC."
            elif "rpc server is unavailable" in low or "сервер rpc недоступен" in low:
                hint = "RPC недоступен: проверьте брандмауэр (Remote Event Log Management) и доступность DC."
            else:
                hint = "Проверьте требования модуля журналов."
            raise ExternalToolError(f"wevtutil вернул ошибку для {dc}", details=mask_text(err.strip())[:500], hint=hint)
        return proc.stdout.decode("utf-8", "replace")

    def query(self, q: EventQuery, cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS,
              check_availability: bool = True) -> EventResult:
        if check_availability:
            ok, reason = availability()
            if not ok:
                raise UnsupportedFeatureError(reason, hint="; ".join(REQUIREMENTS_TEXT[:3]))
        xpath = build_xpath(q.event_ids, q.hours, q.user)
        result = EventResult(events=[], requirements=list(REQUIREMENTS_TEXT))
        min_rank = SEVERITY_ORDER.get(q.min_severity, 4)
        for i, dc in enumerate(q.dcs):
            if cancel:
                cancel.raise_if_cancelled()
            progress(int(i * 100 / max(1, len(q.dcs))), f"Чтение журнала Security: {dc}")
            try:
                N.validate_host(dc)
            except ValidationError as exc:
                result.errors[dc] = exc.message
                continue
            if check_availability:
                probe = N.tcp_check(dc, 135, 3, "RPC")
                if not probe.ok:
                    result.errors[dc] = f"TCP 135 (RPC) недоступен: {probe.message}"
                    continue
            try:
                text = self._runner(dc, xpath, q.max_events, q.timeout_s)
                events = parse_events_xml(dc, text)
            except (ExternalToolError, UnsupportedFeatureError) as exc:
                result.errors[dc] = exc.full_text()
                continue
            except ET.ParseError as exc:
                result.errors[dc] = f"Не удалось разобрать ответ wevtutil: {exc}"
                continue
            result.events.extend(e for e in events if SEVERITY_ORDER.get(e.severity, 4) <= min_rank)
        result.events.sort(key=lambda e: e.time or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        progress(100, f"Получено событий: {len(result.events)}")
        return result


def lockout_summary(events: list[SecurityEvent]) -> list[dict]:
    """Group 4740 events by user and calling computer — typical lockout source analysis."""
    summary: dict[tuple[str, str], dict] = {}
    for e in events:
        if e.event_id != 4740:
            continue
        key = (e.target_user, e.source)
        row = summary.setdefault(key, {"user": e.target_user, "source": e.source, "count": 0, "last": None})
        row["count"] += 1
        if e.time and (row["last"] is None or e.time > row["last"]):
            row["last"] = e.time
    return sorted(summary.values(), key=lambda r: r["count"], reverse=True)

