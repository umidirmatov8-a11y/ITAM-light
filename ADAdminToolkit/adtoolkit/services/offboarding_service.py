"""Processing of employees who left the organisation (offboarding) with configurable templates.

A plan is always produced first (and can be exported without touching AD — "подготовка списка для отключения").
Execution performs the template steps per user with individual error handling and journal records.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import OperationCancelledError, ToolkitError, ValidationError
from ..ldap.adtypes import UAC, utcnow
from ..ldap.dn import normalize_dn, parent_dn, rdn_value
from ..ldap.filters import And, Substring
from ..reports.exporters import ReportTable
from ..security.audit_log import RESULT_DRY_RUN, windows_user
from . import ad_queries as Q
from .bulk_service import STATUS_ERROR, STATUS_READY, STATUS_SKIP, BulkItem, BulkService
from .common import optimistic_value_change
from .context import ServiceContext
from .password_service import PasswordOptions, generate_password

DEFAULT_TEMPLATE = {
    "name": "Стандартное увольнение",
    "disable": True,
    "set_description": True,
    "description_text": "Уволен {date} {ticket}",
    "remove_groups": True,
    "keep_groups": [],
    "move_to_ou": "",
    "expire_now": True,
    "reset_password": False,
    "clear_manager": False,
    "hide_from_gal": False,
}

STEP_LABELS = {
    "disable": "Отключить учётную запись", "set_description": "Записать причину в описание",
    "remove_groups": "Удалить из групп (кроме основной и исключений)", "move_to_ou": "Переместить в OU",
    "expire_now": "Установить срок действия = сегодня", "reset_password": "Сбросить пароль на случайный (не сохраняется)",
    "clear_manager": "Очистить руководителя", "hide_from_gal": "Скрыть из адресной книги Exchange",
}


@dataclass
class OffboardingRow:
    item: BulkItem
    steps: list[str] = field(default_factory=list)
    groups_to_remove: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)


class OffboardingService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.gw = ctx.gateway

    def templates(self, db) -> list[dict]:
        items = db.templates("offboarding")
        return items or [dict(DEFAULT_TEMPLATE)]

    def find_candidates(self, marker: str = "уволен", cancel: CancelToken | None = None) -> list[str]:
        """Enabled users whose description contains a marker set by HR/ITSM (common practice)."""
        marker = (marker or "").strip()
        if not marker:
            raise ValidationError("Не задан маркер поиска")
        flt = And(Q.IS_USER, Q.ENABLED, Substring("description", any=(marker,)))
        return [e.dn for e in self.gw.search(self.ctx.base_dn, flt, ["1.1"], cancel=cancel)]

    def expired_enabled_candidates(self, cancel: CancelToken | None = None) -> list[str]:
        flt = And(Q.IS_USER, Q.ENABLED, Q.account_expired())
        return [e.dn for e in self.gw.search(self.ctx.base_dn, flt, ["1.1"], cancel=cancel)]

    def plan(self, identities: list[str], template: dict, ticket: str = "", cancel: CancelToken | None = None,
             progress: Progress = NULL_PROGRESS) -> list[OffboardingRow]:
        bulk = BulkService(self.ctx)
        items = bulk.resolve(identities, "user", cancel, progress)
        priv = bulk._privileged_member_set(cancel)
        keep = {k.lower() for k in template.get("keep_groups") or []}
        rows = []
        for item in items:
            row = OffboardingRow(item)
            rows.append(row)
            if item.status != STATUS_READY:
                continue
            e = self.gw.get(item.dn, ["userAccountControl", "memberOf", "description", "adminCount"])
            if e is None:
                item.status, item.reason = STATUS_ERROR, "Объект не найден"
                continue
            if normalize_dn(item.dn) in priv or e.int("adminCount") == 1:
                item.status, item.reason = STATUS_SKIP, "Привилегированная УЗ — обработайте индивидуально"
                item.privileged = "да"
                continue
            uac = e.int("userAccountControl", 0) or 0
            item.current = "отключена" if uac & UAC.ACCOUNTDISABLE else "включена"
            if template.get("disable") and not uac & UAC.ACCOUNTDISABLE:
                row.steps.append("disable")
            if template.get("set_description"):
                row.steps.append("set_description")
            if template.get("remove_groups"):
                row.groups_to_remove = [g for g in e.values("memberOf")
                                        if rdn_value(g).lower() not in keep]
                if row.groups_to_remove:
                    row.steps.append("remove_groups")
            target = (template.get("move_to_ou") or "").strip()
            if target and normalize_dn(parent_dn(item.dn)) != normalize_dn(target):
                row.steps.append("move_to_ou")
            if template.get("expire_now"):
                row.steps.append("expire_now")
            if template.get("reset_password"):
                if self.gw.encrypted:
                    row.steps.append("reset_password")
                else:
                    item.reason = "Сброс пароля пропущен: соединение не зашифровано"
            if template.get("clear_manager"):
                row.steps.append("clear_manager")
            if template.get("hide_from_gal"):
                row.steps.append("hide_from_gal")
            if not row.steps:
                item.status, item.reason = STATUS_SKIP, "Нечего выполнять (уже обработан)"
            item.planned = "; ".join(STEP_LABELS[s] + (f" ({len(row.groups_to_remove)})" if s == "remove_groups" else "")
                                     for s in row.steps)
        return rows

    def execute(self, rows: list[OffboardingRow], template: dict, ticket: str = "", *, dry_run: bool = True,
                cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> list[OffboardingRow]:
        from .group_service import GroupService
        from .user_service import UserService
        if not dry_run:
            self.gw._guard_write()
        us, gs = UserService(self.ctx), GroupService(self.ctx)
        batch = self.ctx.journal.new_batch_id()
        today = date.today().isoformat()
        ready = [r for r in rows if r.item.status == STATUS_READY]
        with self.ctx.journal.batch(batch):
            for n, row in enumerate(ready):
                if cancel and cancel.cancelled:
                    row.item.result = "Отменено"
                    continue
                progress(int(n * 100 / max(1, len(ready))), f"Увольнение: {row.item.name}")
                if dry_run:
                    row.item.result = "Dry Run: смоделировано"
                    self.ctx.journal.record("offboarding", row.item.dn, RESULT_DRY_RUN, details={"steps": row.steps})
                    continue
                errors = []
                for step in row.steps:
                    try:
                        self._step(step, row, template, ticket, today, us, gs)
                        row.results.append(f"{STEP_LABELS[step]}: OK")
                    except OperationCancelledError:
                        raise
                    except ToolkitError as exc:
                        errors.append(f"{STEP_LABELS[step]}: {exc.message}")
                        row.results.append(f"{STEP_LABELS[step]}: ошибка")
                row.item.result = "Выполнено" if not errors else "Частично выполнено"
                row.item.error = "; ".join(errors)
                if cancel:
                    cancel.wait(1.0 / max(0.2, self.ctx.settings.bulk_rate_per_second))
        progress(100, "Готово")
        return rows

    def _step(self, step: str, row: OffboardingRow, template: dict, ticket: str, today: str, us, gs):
        dn = row.item.dn
        if step == "disable":
            us.set_enabled(dn, False)
        elif step == "set_description":
            text = (template.get("description_text") or "Уволен {date}").format(date=today, ticket=ticket).strip()
            current = self.gw.get(dn, ["description"])
            old = current.str("description") if current else ""
            us.update_attributes(dn, {"description": text[:1024]}, {"description": old})
        elif step == "remove_groups":
            for g in list(row.groups_to_remove):
                gs.remove_member(g, dn, privileged_confirmed=False)
        elif step == "move_to_ou":
            row.item.dn = us.move(dn, template["move_to_ou"])
        elif step == "expire_now":
            us.set_account_expiry(dn, date.today() - timedelta(days=1))
        elif step == "reset_password":
            # random password, never shown/stored: makes cached credentials of the leaver useless
            pwd = generate_password(PasswordOptions(length=24))
            us.reset_password(dn, pwd, must_change=True)
            del pwd
        elif step == "clear_manager":
            current = self.gw.get(dn, ["manager"])
            old = current.str("manager") if current else ""
            if old:
                us.update_attributes(dn, {"manager": ""}, {"manager": old})
        elif step == "hide_from_gal":
            with self.ctx.journal.track("user.hide_from_gal", dn):
                self.ctx.permissions.require_write(dn, ["msExchHideFromAddressLists"], "Скрытие из адресной книги")
                e = self.gw.get(dn, ["msExchHideFromAddressLists"])
                old = e.str("msExchHideFromAddressLists") if e else ""
                changes = optimistic_value_change("msExchHideFromAddressLists", old or None, "TRUE")
                if changes:
                    self.gw.modify(dn, changes)

    def report(self, rows: list[OffboardingRow], template: dict, ticket: str, executed: bool, dry_run: bool) -> ReportTable:
        data = [{"source": r.item.source, "name": r.item.name, "sam": r.item.sam, "current": r.item.current,
                 "planned": r.item.planned, "status": {STATUS_READY: "К обработке", STATUS_SKIP: "Пропуск",
                                                       STATUS_ERROR: "Ошибка"}.get(r.item.status, r.item.status),
                 "reason": r.item.reason, "groups": "; ".join(rdn_value(g) for g in r.groups_to_remove),
                 "result": r.item.result, "details": "; ".join(r.results), "error": r.item.error, "dn": r.item.dn}
                for r in rows]
        cols = [("source", "Исходное значение"), ("name", "Сотрудник"), ("sam", "Логин"), ("current", "Состояние"),
                ("planned", "План"), ("status", "Предпроверка"), ("reason", "Причина"), ("groups", "Группы к удалению"),
                ("result", "Результат"), ("details", "Шаги"), ("error", "Ошибки"), ("dn", "DN")]
        title = "Обработка уволенных сотрудников — " + ("результат" if executed else "план (без изменений в AD)")
        return ReportTable(title=title, columns=cols, rows=data,
                           criteria={"Шаблон": template.get("name", ""), "Заявка": ticket,
                                     "Режим": "Dry Run" if dry_run else ("Выполнение" if executed else "Подготовка списка")},
                           limitations=["Привилегированные учётные записи исключаются и обрабатываются индивидуально."],
                           generated_at=utcnow(), domain=self.gw.info.domain_dns, dc=self.gw.info.dc_host,
                           generated_by=windows_user())

