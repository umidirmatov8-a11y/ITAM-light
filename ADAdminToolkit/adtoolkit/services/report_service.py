"""Ready-made reports and converters from records to report tables."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..ldap.adtypes import utcnow
from ..ldap.dn import container_path
from ..models.records import CheckResult, ComputerRecord, GroupRecord, UserRecord
from ..reports.exporters import ReportTable
from ..security.audit_log import windows_user
from .context import ServiceContext

USER_COLUMNS = [
    ("name", "Имя"), ("sam", "Логин"), ("upn", "UPN"), ("state", "Состояние"), ("department", "Отдел"),
    ("title", "Должность"), ("mail", "Email"), ("phone", "Телефон"), ("manager", "Руководитель"), ("ou", "OU"),
    ("last_logon", "Последний вход (lastLogonTimestamp)"), ("days_since_logon", "Дней без входа"),
    ("pwd_last_set", "Пароль установлен"), ("pwd_expires", "Пароль истекает"), ("pne", "Password Never Expires"),
    ("account_expires", "Срок УЗ"), ("created", "Создана"), ("changed", "Изменена"), ("dn", "DN"),
]
COMPUTER_COLUMNS = [
    ("name", "Имя"), ("dns", "DNS-имя"), ("os", "ОС"), ("os_version", "Версия ОС"), ("os_support", "Поддержка ОС"),
    ("enabled", "Включён"), ("last_logon", "Последняя активность (lastLogonTimestamp)"), ("days_since_logon", "Дней без входа"),
    ("pwd_last_set", "Пароль компьютера сменён"), ("created", "Создан"), ("ou", "OU"), ("description", "Описание"), ("dn", "DN"),
]
GROUP_COLUMNS = [
    ("name", "Имя"), ("sam", "sAMAccountName"), ("scope", "Область"), ("category", "Тип"), ("members", "Прямых участников"),
    ("privileged", "Привилегированная"), ("privileged_reason", "Основание"), ("description", "Описание"), ("ou", "OU"),
    ("dn", "DN"),
]
FINDING_COLUMNS = [("severity", "Критичность"), ("evidence", "Характер"), ("check", "Проверка"), ("title", "Находка"),
                   ("object", "Объект"), ("details", "Подробности"), ("recommendation", "Рекомендация"), ("dn", "DN")]

LASTLOGON_LIMIT = ("lastLogonTimestamp реплицируется с задержкой до ~14–19 дней; пустое значение не доказывает "
                   "отсутствие входов.")


def user_row(u: UserRecord) -> dict:
    return {"name": u.name, "sam": u.sam, "upn": u.upn, "state": u.state.label, "department": u.department,
            "title": u.title, "mail": u.mail, "phone": u.phone, "manager": u.manager_name, "ou": u.ou,
            "last_logon": u.last_logon_timestamp, "days_since_logon": u.days_since_logon(),
            "pwd_last_set": u.pwd_last_set if not u.must_change_password else "сменить при входе",
            "pwd_expires": "никогда" if u.pwd_never_expires else u.pwd_expires, "pne": u.pwd_never_expires,
            "account_expires": u.account_expires or "никогда", "created": u.when_created, "changed": u.when_changed,
            "dn": u.dn, "enabled": u.enabled, "locked": u.locked, "cannot_change": u.cannot_change_password}


def computer_row(c: ComputerRecord) -> dict:
    return {"name": c.name, "dns": c.dns_host_name, "os": c.os, "os_version": c.os_version,
            "os_support": {"supported": "Поддерживается", "outdated": "Устарела", "unknown": "Неизвестно"}[c.os_support.value]
            + (f" ({c.os_note})" if c.os_note else ""), "enabled": c.enabled, "last_logon": c.last_logon_timestamp,
            "days_since_logon": c.days_since_logon(), "pwd_last_set": c.pwd_last_set, "created": c.when_created,
            "ou": c.ou, "description": c.description, "dn": c.dn}


def group_row(g: GroupRecord) -> dict:
    return {"name": g.name, "sam": g.sam, "scope": g.scope, "category": g.category, "members": len(g.members),
            "privileged": g.privileged, "privileged_reason": g.privileged_reason, "description": g.description,
            "ou": g.ou, "dn": g.dn}


def finding_rows(results: list[CheckResult]) -> list[dict]:
    rows = []
    for r in results:
        for f in sorted(r.findings, key=lambda x: x.severity.rank):
            rows.append({"severity": f.severity.label, "severity_key": f.severity.value, "evidence": f.evidence.label,
                         "check": r.title, "title": f.title, "object": f.object_name, "details": f.details,
                         "recommendation": f.recommendation, "dn": f.object_dn})
    return rows


@dataclass
class ReportDef:
    report_id: str
    title: str
    description: str
    params: list[str]
    build: Callable


class ReportService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.gw = ctx.gateway
        self.reports = [
            ReportDef("disabled_users", "Все отключённые пользователи", "Учётные записи с флагом ACCOUNTDISABLE", [], self.r_disabled),
            ReportDef("locked_users", "Заблокированные пользователи", "Текущая блокировка", [], self.r_locked),
            ReportDef("stale_users", "Неактивные пользователи", "Без входа за выбранный период", ["days"], self.r_stale_users),
            ReportDef("stale_computers", "Неактивные компьютеры", "Без входа за выбранный период", ["days"], self.r_stale_computers),
            ReportDef("pne_users", "Пользователи с Password Never Expires", "Пароль без срока действия", [], self.r_pne),
            ReportDef("privileged", "Состав привилегированных групп", "Прямые и вложенные члены", [], self.r_privileged),
            ReportDef("users_groups", "Пользователи и их группы", "Прямое членство (memberOf) и основная группа", [], self.r_users_groups),
            ReportDef("computers_ou_os", "Компьютеры по OU и ОС", "Сводка и полный список", [], self.r_computers_ou_os),
            ReportDef("incomplete_users", "Пользователи с неполными атрибутами", "По списку обязательных атрибутов", [], self.r_incomplete),
            ReportDef("domain_health", "Общий отчёт по состоянию домена", "Статистика + результаты аудита", [], self.r_domain_health),
        ]

    def table(self, title: str, columns, rows, criteria=None, limitations=None, sheet: str = "") -> ReportTable:
        return ReportTable(title=title, columns=list(columns), rows=rows, criteria=dict(criteria or {}),
                           limitations=list(limitations or []), generated_at=utcnow(), domain=self.gw.info.domain_dns,
                           dc=self.gw.info.dc_host, generated_by=windows_user(), sheet_name=sheet)

    def build(self, report_id: str, params: dict | None = None, cancel: CancelToken | None = None,
              progress: Progress = NULL_PROGRESS) -> list[ReportTable]:
        d = next((r for r in self.reports if r.report_id == report_id), None)
        if d is None:
            raise KeyError(report_id)
        return d.build(params or {}, cancel, progress)

    # ------------------------------------------------------------------------------------------------------------
    def _users(self, view, cancel, progress, **kw):
        from .user_service import UserQuery, UserService
        q = UserQuery(view=view, required_attributes=self.ctx.settings.required_user_attributes, limit=0, **kw)
        return UserService(self.ctx).search(q, cancel, progress)

    def r_disabled(self, params, cancel, progress):
        from .user_service import UserView
        res = self._users(UserView.DISABLED, cancel, progress)
        return [self.table("Отключённые пользователи", USER_COLUMNS, [user_row(u) for u in res.items], res.criteria, res.notes)]

    def r_locked(self, params, cancel, progress):
        from .user_service import UserView
        res = self._users(UserView.LOCKED, cancel, progress)
        cols = USER_COLUMNS[:4] + [("lockout", "Заблокирована с")] + USER_COLUMNS[4:]
        rows = []
        for u in res.items:
            r = user_row(u)
            r["lockout"] = u.lockout_time
            rows.append(r)
        return [self.table("Заблокированные пользователи", cols, rows, res.criteria, res.notes)]

    def r_stale_users(self, params, cancel, progress):
        from .user_service import UserView
        days = int(params.get("days") or self.ctx.settings.stale_user_days)
        res = self._users(UserView.STALE, cancel, progress, stale_days=days)
        return [self.table(f"Неактивные пользователи (> {days} дн.)", USER_COLUMNS, [user_row(u) for u in res.items],
                           res.criteria, res.notes)]

    def r_stale_computers(self, params, cancel, progress):
        from .computer_service import ComputerQuery, ComputerService, ComputerView
        days = int(params.get("days") or self.ctx.settings.stale_computer_days)
        res = ComputerService(self.ctx).search(ComputerQuery(view=ComputerView.STALE, stale_days=days, limit=0), cancel, progress)
        return [self.table(f"Неактивные компьютеры (> {days} дн.)", COMPUTER_COLUMNS, [computer_row(c) for c in res.items],
                           res.criteria, res.notes)]

    def r_pne(self, params, cancel, progress):
        from .user_service import UserView
        res = self._users(UserView.PNE, cancel, progress)
        return [self.table("Пользователи с Password Never Expires", USER_COLUMNS, [user_row(u) for u in res.items],
                           res.criteria, res.notes)]

    def r_privileged(self, params, cancel, progress):
        from .group_service import GroupService
        progress(None, "Разбор привилегированных групп…")
        rows = GroupService(self.ctx).privileged_composition(cancel)
        for r in rows:
            r["critical"] = "Критичная" if r["critical"] else ""
            r["type"] = {"user": "Пользователь", "computer": "Компьютер", "group": "Группа"}.get(r["type"], r["type"])
        cols = [("group", "Группа"), ("critical", "Уровень"), ("member", "Участник"), ("sam", "Логин"), ("type", "Тип"),
                ("enabled", "Включён"), ("via", "Членство"), ("dn", "DN")]
        return [self.table("Состав привилегированных групп", cols, rows,
                           {"Определение": "по SID встроенных групп + дополнительные из настроек"},
                           ["Включено вложенное членство и основная группа (primaryGroupID)."])]

    def r_users_groups(self, params, cancel, progress):
        from ..ldap.dn import rdn_value
        from .user_service import UserView
        res = self._users(UserView.ALL, cancel, progress)
        rows = []
        for u in res.items:
            groups = sorted(rdn_value(g) for g in u.member_of)
            rows.append({"name": u.name, "sam": u.sam, "state": u.state.label, "department": u.department,
                         "primary": u.primary_group_id, "count": len(groups), "groups": "; ".join(groups), "dn": u.dn})
        cols = [("name", "Имя"), ("sam", "Логин"), ("state", "Состояние"), ("department", "Отдел"),
                ("primary", "Основная группа (RID)"), ("count", "Групп (прямо)"), ("groups", "Группы (memberOf)"), ("dn", "DN")]
        return [self.table("Пользователи и их группы", cols, rows, res.criteria,
                           ["memberOf показывает прямое членство в группах домена/леса; вложенность и основная группа "
                            "(обычно Domain Users, RID 513) — см. карточку пользователя."])]

    def r_computers_ou_os(self, params, cancel, progress):
        from .computer_service import ComputerQuery, ComputerService
        res = ComputerService(self.ctx).search(ComputerQuery(limit=0), cancel, progress)
        summary: dict[tuple[str, str], int] = {}
        for c in res.items:
            key = (container_path(c.dn), c.os or "(не указана)")
            summary[key] = summary.get(key, 0) + 1
        srows = [{"ou": k[0], "os": k[1], "count": v} for k, v in sorted(summary.items())]
        return [self.table("Компьютеры по OU и ОС — сводка", [("ou", "OU"), ("os", "ОС"), ("count", "Количество")], srows,
                           res.criteria, res.notes, sheet="Сводка"),
                self.table("Компьютеры — полный список", COMPUTER_COLUMNS, [computer_row(c) for c in res.items],
                           res.criteria, res.notes, sheet="Компьютеры")]

    def r_incomplete(self, params, cancel, progress):
        from .user_service import UserView
        res = self._users(UserView.MISSING_ATTRS, cancel, progress)
        req = self.ctx.settings.required_user_attributes
        rows = []
        for u in res.items:
            r = user_row(u)
            vals = {"department": u.department, "title": u.title, "mail": u.mail, "telephoneNumber": u.phone,
                    "manager": u.manager_dn, "company": u.company, "employeeID": u.employee_id}
            r["missing"] = ", ".join(a for a in req if not vals.get(a, "x"))
            rows.append(r)
        cols = USER_COLUMNS[:4] + [("missing", "Не заполнено")] + USER_COLUMNS[4:]
        return [self.table("Пользователи с неполными атрибутами", cols, rows,
                           {**res.criteria, "Обязательные атрибуты": ", ".join(req)}, res.notes)]

    def r_domain_health(self, params, cancel, progress):
        from .audit_service import AuditService
        from .dashboard_service import DashboardService
        stats = DashboardService(self.ctx).collect(cancel, Progress(lambda p, m: progress(int((p or 0) * 0.3), m)))
        srows = [{"metric": m.title, "value": "ошибка: " + m.error if m.error else m.value,
                  "note": ("" if m.exact else "приблизительно; ") + m.note} for m in stats.metrics.values()]
        audit = AuditService(self.ctx)
        results = audit.run(None, cancel, Progress(lambda p, m: progress(30 + int((p or 0) * 0.7), m)))
        summary = audit.summary(results)
        checks = [{"check": r.title, "findings": len(r.findings), "error": r.error, "limitations": r.limitations,
                   "duration": r.duration_s} for r in results]
        info = self.gw.info
        dom = [{"k": "Домен (DNS)", "v": info.domain_dns}, {"k": "NetBIOS", "v": info.netbios_name},
               {"k": "Base DN", "v": info.base_dn}, {"k": "Контроллер", "v": info.dc_host},
               {"k": "Функциональный уровень домена", "v": info.level_text(info.domain_functionality)},
               {"k": "Функциональный уровень леса", "v": info.level_text(info.forest_functionality)},
               {"k": "Контроллеры домена", "v": ", ".join(info.domain_controllers)},
               {"k": "Подключение", "v": info.security_label}]
        sev = summary["by_severity"]
        dom += [{"k": f"Находки: {s.label}", "v": n} for s, n in sev.items()]
        return [
            self.table("Сведения о домене", [("k", "Параметр"), ("v", "Значение")], dom, sheet="Домен"),
            self.table("Статистика домена", [("metric", "Показатель"), ("value", "Значение"), ("note", "Примечание")], srows,
                       {"Период неактивности": f"{self.ctx.settings.stale_user_days} дн."}, [LASTLOGON_LIMIT], sheet="Статистика"),
            self.table("Проверки аудита", [("check", "Проверка"), ("findings", "Находок"), ("error", "Ошибка"),
                                           ("limitations", "Ограничения"), ("duration", "Время, с")], checks, sheet="Проверки"),
            self.table("Находки аудита", FINDING_COLUMNS, finding_rows(results), {},
                       ["«Требует проверки» — индикатор для анализа, а не доказательство нарушения.",
                        "Журнал приложения не является полным аудитом AD; события безопасности — в журналах DC."],
                       sheet="Находки"),
        ]
