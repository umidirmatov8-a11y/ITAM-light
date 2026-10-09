"""Computer accounts: search / views, OS classification, enable/disable, move."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import ProtectedObjectError
from ..ldap.adtypes import UAC, utcnow
from ..ldap.filters import And, Not, Or, Present, Substring
from ..models.records import ComputerRecord, OsSupport
from ..security.audit_log import RESULT_SKIPPED
from . import ad_queries as Q
from .common import QueryResult, get_or_fail, optimistic_value_change, require_dn, search_records
from .context import ServiceContext

ACTIVITY_NOTE = ("Последняя активность — lastLogonTimestamp (обновляется с задержкой до ~14–19 дней) и pwdLastSet "
                 "(компьютер меняет пароль раз в 30 дней по умолчанию). LDAP НЕ показывает, включён ли компьютер "
                 "сейчас — доступность проверяется отдельно (ping/TCP/DNS).")


class ComputerView(str, Enum):
    ALL = "all"
    ENABLED = "enabled"
    DISABLED = "disabled"
    STALE = "stale"
    NEVER_LOGGED = "never"
    OUTDATED_OS = "outdated"
    SERVERS = "servers"
    WORKSTATIONS = "workstations"
    DOMAIN_CONTROLLERS = "dcs"
    RECENT = "recent"
    NO_OS = "no_os"

    @property
    def label(self) -> str:
        return {
            "all": "Все компьютеры", "enabled": "Включённые", "disabled": "Отключённые",
            "stale": "Неактивные (давно не входили)", "never": "Нет данных о входе",
            "outdated": "Устаревшие ОС", "servers": "Серверы", "workstations": "Рабочие станции",
            "dcs": "Контроллеры домена", "recent": "Недавно созданные", "no_os": "ОС не указана",
        }[self.value]


@dataclass
class ComputerQuery:
    view: ComputerView = ComputerView.ALL
    text: str = ""
    ou_dn: str = ""
    os_text: str = ""
    stale_days: int = 90
    recent_days: int = 14
    limit: int = 5000


def classify_os(record: ComputerRecord, rules: list[dict]) -> None:
    os_name = (record.os or "").casefold()
    if not os_name:
        record.os_support, record.os_note = OsSupport.UNKNOWN, "ОС не указана в атрибуте operatingSystem"
        return
    for rule in rules:
        pattern = str(rule.get("pattern", "")).casefold()
        if pattern and pattern in os_name:
            if pattern == "windows 10" and ("ltsc" in os_name or "ltsb" in os_name):
                continue
            record.os_support, record.os_note = OsSupport.OUTDATED, str(rule.get("note", ""))
            return
    record.os_support, record.os_note = OsSupport.SUPPORTED, ""


class ComputerService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.gw = ctx.gateway

    def build_filter(self, q: ComputerQuery):
        now = utcnow()
        parts = [Q.IS_COMPUTER]
        notes: list[str] = []
        if q.text.strip():
            t = q.text.strip()
            parts.append(Or(Substring("cn", any=(t,)), Substring("dNSHostName", any=(t,)),
                            Substring("description", any=(t,)), Substring("sAMAccountName", any=(t,))))
        if q.os_text.strip():
            parts.append(Substring("operatingSystem", any=(q.os_text.strip(),)))
        v = q.view
        if v is ComputerView.ENABLED:
            parts.append(Q.ENABLED)
        elif v is ComputerView.DISABLED:
            parts.append(Q.DISABLED)
        elif v is ComputerView.STALE:
            parts += [Q.ENABLED, Q.stale_logon_filter(q.stale_days, now), Q.created_before(q.stale_days, now)]
            notes.append(ACTIVITY_NOTE)
        elif v is ComputerView.NEVER_LOGGED:
            parts.append(Not(Present("lastLogonTimestamp")))
            notes.append(ACTIVITY_NOTE)
        elif v is ComputerView.SERVERS:
            parts.append(Substring("operatingSystem", any=("Server",)))
        elif v is ComputerView.WORKSTATIONS:
            parts += [Present("operatingSystem"), Not(Substring("operatingSystem", any=("Server",)))]
        elif v is ComputerView.DOMAIN_CONTROLLERS:
            parts.append(Q.DC_ACCOUNT)
        elif v is ComputerView.RECENT:
            parts.append(Q.created_since(q.recent_days, now))
        elif v is ComputerView.NO_OS:
            parts.append(Not(Present("operatingSystem")))
        elif v is ComputerView.OUTDATED_OS:
            parts.append(Present("operatingSystem"))
            notes.append("Классификация ОС выполняется по правилам из настроек (подстрока operatingSystem); "
                         "атрибут заполняет сам компьютер и может быть устаревшим.")
        return And(*parts), notes

    def search(self, q: ComputerQuery, cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> QueryResult:
        base = q.ou_dn.strip() or self.ctx.base_dn
        require_dn(base, "контейнер поиска")
        flt, notes = self.build_filter(q)
        progress(None, "Поиск компьютеров…")
        items, stats = search_records(self.gw, base, flt, Q.COMPUTER_ATTRIBUTES, ComputerRecord.from_entry,
                                      limit=q.limit, cancel=cancel)
        rules = self.ctx.settings.outdated_os
        for c in items:
            classify_os(c, rules)
        if q.view is ComputerView.OUTDATED_OS:
            items = [c for c in items if c.os_support is OsSupport.OUTDATED]
        if ACTIVITY_NOTE not in notes:
            notes.append(ACTIVITY_NOTE)
        if stats.truncated:
            notes.append(f"Показаны первые {len(items)} объектов — уточните условия поиска.")
        progress(100, f"Найдено: {len(items)}")
        return QueryResult(items=items, truncated=stats.truncated, notes=notes, filter_text=flt.to_ldap(), base_dn=base,
                           criteria={"Представление": q.view.label, "Текст": q.text, "ОС": q.os_text, "OU": base,
                                     **({"Период неактивности, дней": q.stale_days} if q.view is ComputerView.STALE else {})})

    def get(self, dn: str) -> ComputerRecord:
        c = ComputerRecord.from_entry(get_or_fail(self.gw, dn, Q.COMPUTER_ATTRIBUTES))
        classify_os(c, self.ctx.settings.outdated_os)
        return c

    def set_enabled(self, dn: str, enabled: bool) -> bool:
        op = "computer.enable" if enabled else "computer.disable"
        self.gw._guard_write()
        e = get_or_fail(self.gw, dn, ["userAccountControl"])
        uac = e.int("userAccountControl", 0) or 0
        if uac & UAC.SERVER_TRUST_ACCOUNT or uac & UAC.PARTIAL_SECRETS_ACCOUNT:
            raise ProtectedObjectError("Учётные записи контроллеров домена не отключаются через приложение")
        new = (uac & ~int(UAC.ACCOUNTDISABLE)) if enabled else (uac | int(UAC.ACCOUNTDISABLE))
        if new == uac:
            self.ctx.journal.record(op, dn, RESULT_SKIPPED, details={"reason": "уже в требуемом состоянии"})
            return False
        with self.ctx.journal.track(op, dn):
            self.ctx.permissions.require_write(dn, ["userAccountControl"], "Изменение состояния компьютера")
            self.gw.modify(dn, optimistic_value_change("userAccountControl", uac, new))
        return True

    def move(self, dn: str, target_ou: str) -> str:
        with self.ctx.journal.track("computer.move", dn, details={"target": target_ou}):
            e = get_or_fail(self.gw, dn, ["userAccountControl"])
            if (e.int("userAccountControl", 0) or 0) & UAC.SERVER_TRUST_ACCOUNT:
                raise ProtectedObjectError("Контроллеры домена не перемещаются через приложение")
            from .ou_service import OUService
            OUService(self.ctx).validate_move_target(dn, target_ou, "computer")
            return self.gw.move(dn, target_ou)
