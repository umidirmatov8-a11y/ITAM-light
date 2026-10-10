"""Bulk operations wizard back-end: CSV import, identity resolution, pre-check plan, Dry Run, rate-limited execution.

Safety rules:
* a plan is always built (and shown) before execution: selected objects, intended change, skipped objects and the
  reasons of pre-check errors;
* Dry Run (default) only simulates and journals the planned changes;
* privileged accounts are skipped unless the organisation enabled it in settings *and* the operator confirmed it
  separately; privileged target groups require a separate typed confirmation;
* each object is processed independently (one failure never stops the batch), with a configurable rate limit.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import OperationCancelledError, ToolkitError, ValidationError
from ..ldap.adtypes import UAC, utcnow
from ..ldap.dn import first_rdn, normalize_dn, parent_dn, rdn_value
from ..ldap.filters import And, Equals, Or
from ..reports.exporters import ReportTable
from ..security.audit_log import RESULT_DRY_RUN, RESULT_FAILED, RESULT_SKIPPED, RESULT_SUCCESS, windows_user
from . import ad_queries as Q
from .common import object_type_of
from .context import ServiceContext


class BulkOperation(str, Enum):
    DISABLE = "disable"
    ENABLE = "enable"
    UNLOCK = "unlock"
    ADD_TO_GROUP = "add_to_group"
    REMOVE_FROM_GROUP = "remove_from_group"
    MOVE_TO_OU = "move_to_ou"
    PREPARE_PASSWORD_RESET = "prepare_password_reset"

    @property
    def label(self) -> str:
        return {
            "disable": "Отключить учётные записи", "enable": "Включить учётные записи", "unlock": "Разблокировать пользователей",
            "add_to_group": "Добавить в группу", "remove_from_group": "Удалить из группы",
            "move_to_ou": "Переместить в OU", "prepare_password_reset": "Подготовить список для сброса паролей (без изменений)",
        }[self.value]

    @property
    def modifies(self) -> bool:
        return self is not BulkOperation.PREPARE_PASSWORD_RESET


STATUS_READY = "ready"
STATUS_SKIP = "skip"
STATUS_ERROR = "error"
STATUS_LABELS = {STATUS_READY: "Будет изменён", STATUS_SKIP: "Пропуск", STATUS_ERROR: "Ошибка проверки"}

IDENTITY_COLUMNS = ["distinguishedname", "dn", "samaccountname", "sam", "login", "логин", "userprincipalname", "upn",
                    "mail", "email", "почта", "employeeid", "табельный", "name", "имя", "computer", "компьютер", "host"]


@dataclass
class BulkItem:
    source: str
    dn: str = ""
    name: str = ""
    sam: str = ""
    object_type: str = ""
    current: str = ""
    planned: str = ""
    status: str = STATUS_READY
    reason: str = ""
    result: str = ""
    error: str = ""
    privileged: str = ""


@dataclass
class BulkPlan:
    operation: BulkOperation
    items: list[BulkItem]
    params: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    blocked_reason: str = ""                        # plan-level block (e.g. privileged target group not confirmed)
    target_privileged: str = ""
    batch_id: str = ""
    executed: bool = False
    dry_run: bool = True
    finished_at: datetime | None = None

    @property
    def ready(self) -> list[BulkItem]:
        return [i for i in self.items if i.status == STATUS_READY]

    def counts(self) -> dict[str, int]:
        out = {STATUS_READY: 0, STATUS_SKIP: 0, STATUS_ERROR: 0}
        for i in self.items:
            out[i.status] = out.get(i.status, 0) + 1
        return out

    def result_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in self.items:
            if i.result:
                out[i.result] = out.get(i.result, 0) + 1
        return out


def read_csv_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValidationError("Не удалось определить кодировку CSV (ожидается UTF-8 или Windows-1251)")


def parse_csv(source: str | Path | bytes, max_rows: int = 20000) -> tuple[list[str], list[dict]]:
    if isinstance(source, (str, Path)) and Path(source).exists():
        data = Path(source).read_bytes()
    elif isinstance(source, bytes):
        data = source
    else:
        data = str(source).encode("utf-8")
    text = read_csv_text(data)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [r for r in reader if any(c.strip() for c in r) and not r[0].lstrip().startswith("#")]
    if not rows:
        raise ValidationError("CSV-файл пуст")
    headers = [h.strip() for h in rows[0]]
    if len(headers) == 1 and not any(h.lower() in IDENTITY_COLUMNS for h in headers):
        # single column without a recognised header: treat every line as an identity
        headers = ["identity"]
        body = rows
    else:
        body = rows[1:]
    if len(body) > max_rows:
        raise ValidationError(f"Слишком много строк ({len(body)}); максимум {max_rows}")
    out = []
    for r in body:
        out.append({headers[i] if i < len(headers) else f"col{i}": (r[i].strip() if i < len(r) else "") for i in range(len(headers))})
    return headers, out


def guess_identity_column(headers: list[str]) -> str:
    lowered = {h.lower().replace(" ", ""): h for h in headers}
    for cand in IDENTITY_COLUMNS:
        for low, orig in lowered.items():
            if low == cand or low.startswith(cand):
                return orig
    return headers[0]


class BulkService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.gw = ctx.gateway

    # ---------------------------------------------------------------------------------------------------------
    def resolve(self, identities: list[str], object_kind: str = "user", cancel: CancelToken | None = None,
                progress: Progress = NULL_PROGRESS) -> list[BulkItem]:
        items: list[BulkItem] = []
        seen: set[str] = set()
        attrs = ["sAMAccountName", "displayName", "cn", "objectClass", "userAccountControl", "lockoutTime", "adminCount",
                 "msDS-User-Account-Control-Computed", "memberOf"]
        base_flt = {"computer": Q.IS_COMPUTER, "group": Q.IS_GROUP}.get(object_kind, Q.IS_USER)
        total = len(identities)
        for n, raw in enumerate(identities):
            if cancel:
                cancel.raise_if_cancelled()
            if n % 20 == 0:
                progress(int(n * 100 / max(1, total)), f"Поиск объектов: {n}/{total}")
            ident = (raw or "").strip()
            item = BulkItem(source=ident)
            items.append(item)
            if not ident:
                item.status, item.reason = STATUS_ERROR, "Пустой идентификатор"
                continue
            try:
                if "=" in ident and "," in ident:
                    e = self.gw.get(ident, attrs)
                    found = [e] if e is not None else []
                else:
                    key = ident.split("\\", 1)[1] if "\\" in ident else ident
                    clauses = [Equals("sAMAccountName", key), Equals("userPrincipalName", key), Equals("mail", key),
                               Equals("employeeID", key), Equals("cn", key)]
                    if object_kind == "computer":
                        clauses += [Equals("sAMAccountName", key.rstrip("$") + "$"), Equals("dNSHostName", key)]
                    found = self.gw.search_list(self.ctx.base_dn, And(base_flt, Or(*clauses)), attrs, size_limit=3)
            except ToolkitError as exc:
                item.status, item.reason = STATUS_ERROR, exc.message
                continue
            if not found:
                item.status, item.reason = STATUS_ERROR, "Объект не найден"
                continue
            if len(found) > 1:
                item.status, item.reason = STATUS_ERROR, f"Неоднозначно: найдено {len(found)} объектов"
                continue
            e = found[0]
            t = object_type_of(e)
            if t != object_kind:
                item.status, item.reason = STATUS_ERROR, f"Тип объекта «{t}» не соответствует операции"
                continue
            item.dn, item.sam = e.dn, e.str("sAMAccountName")
            item.name = e.str("displayName") or e.str("cn") or rdn_value(e.dn)
            item.object_type = t
            nd = normalize_dn(e.dn)
            if nd in seen:
                item.status, item.reason = STATUS_SKIP, "Дубликат в списке"
                continue
            seen.add(nd)
        progress(100, "Объекты найдены")
        return items

    def items_from_dns(self, dns: list[str], object_kind: str = "user", cancel: CancelToken | None = None) -> list[BulkItem]:
        return self.resolve(dns, object_kind, cancel)

    # ---------------------------------------------------------------------------------------------------------
    def plan(self, operation: BulkOperation, items: list[BulkItem], params: dict | None = None, *,
             privileged_target_confirmed: bool = False, cancel: CancelToken | None = None,
             progress: Progress = NULL_PROGRESS) -> BulkPlan:
        params = dict(params or {})
        plan = BulkPlan(operation, items, params)
        settings = self.ctx.settings
        active = [i for i in items if i.status == STATUS_READY]
        if len(active) > settings.bulk_max_items:
            plan.blocked_reason = (f"Превышен лимит массовой операции: {len(active)} объектов при максимуме "
                                   f"{settings.bulk_max_items} (Настройки → Массовые операции)")
            for i in active:
                i.status, i.reason = STATUS_ERROR, "Превышен лимит количества объектов"
            return plan
        group_dn = params.get("group_dn", "")
        target_ou = params.get("target_ou", "")
        group_members: set[str] = set()
        group_writable = True
        ou_ok = True
        ou_reason = ""
        if operation in (BulkOperation.ADD_TO_GROUP, BulkOperation.REMOVE_FROM_GROUP):
            if not group_dn:
                raise ValidationError("Не выбрана группа")
            g = self.gw.get(group_dn, ["member", "cn"])
            if g is None:
                raise ValidationError(f"Группа не найдена: {group_dn}")
            group_members = {normalize_dn(m) for m in g.values("member")}
            privileged, reason, _ = self.ctx.privileged.classify_group(group_dn)
            if privileged:
                plan.target_privileged = reason
                if not privileged_target_confirmed:
                    plan.blocked_reason = (f"Целевая группа «{rdn_value(group_dn)}» привилегированная ({reason}). "
                                           "Требуется отдельное подтверждение вводом имени группы.")
            try:
                group_writable = self.ctx.permissions.can_write(group_dn, ["member"])
            except ToolkitError:
                group_writable = False
        if operation is BulkOperation.MOVE_TO_OU:
            if not target_ou:
                raise ValidationError("Не выбрано целевое OU")
            t = self.gw.get(target_ou, ["objectClass"])
            if t is None:
                raise ValidationError(f"Целевое OU не найдено: {target_ou}")
            kinds = {i.object_type for i in active} or {"user"}
            try:
                allowed = self.ctx.permissions.effective_child_classes(target_ou)
                missing = [k for k in kinds if k not in allowed]
                if missing:
                    ou_ok, ou_reason = False, f"Нет права создавать объекты {', '.join(missing)} в целевом OU"
            except ToolkitError as exc:
                ou_ok, ou_reason = False, exc.message

        priv_members = self._privileged_member_set(cancel) if operation.modifies else set()
        attrs = ["userAccountControl", "lockoutTime", "msDS-User-Account-Control-Computed", "adminCount", "allowedAttributesEffective"]
        for n, item in enumerate(active):
            if cancel:
                cancel.raise_if_cancelled()
            if n % 10 == 0:
                progress(int(n * 100 / max(1, len(active))), f"Предварительная проверка: {n}/{len(active)}")
            try:
                e = self.gw.get(item.dn, attrs)
            except ToolkitError as exc:
                item.status, item.reason = STATUS_ERROR, exc.message
                continue
            if e is None:
                item.status, item.reason = STATUS_ERROR, "Объект больше не существует"
                continue
            uac = e.int("userAccountControl", 0) or 0
            computed = e.int("msDS-User-Account-Control-Computed")
            locked = bool(computed & UAC.LOCKOUT) if computed is not None else bool(e.int("lockoutTime", 0))
            allowed_attrs = {str(a).lower() for a in e.values("allowedAttributesEffective")}
            item.current = ("отключена" if uac & UAC.ACCOUNTDISABLE else "включена") + (", заблокирована" if locked else "")
            nd = normalize_dn(item.dn)
            if nd in priv_members or e.int("adminCount") == 1:
                item.privileged = "привилегированная" if nd in priv_members else "adminCount=1"
                if operation.modifies and not (settings.bulk_allow_privileged and params.get("privileged_accounts_confirmed")):
                    item.status, item.reason = STATUS_SKIP, ("Привилегированная учётная запись: массовые изменения запрещены "
                                                             "(измените индивидуально с подтверждением)")
                    continue
            if uac & (UAC.SERVER_TRUST_ACCOUNT | UAC.PARTIAL_SECRETS_ACCOUNT) and operation.modifies:
                item.status, item.reason = STATUS_SKIP, "Контроллер домена — не изменяется"
                continue
            if item.sam.lower() in ("krbtgt", "administrator", "guest") and operation.modifies:
                item.status, item.reason = STATUS_SKIP, "Встроенная учётная запись — массово не изменяется"
                continue
            op = operation
            if item.object_type == "group" and op not in (BulkOperation.ADD_TO_GROUP, BulkOperation.REMOVE_FROM_GROUP):
                item.status, item.reason = STATUS_ERROR, "Операция не применима к группам"
                continue
            if item.object_type == "computer" and op is BulkOperation.UNLOCK:
                item.status, item.reason = STATUS_ERROR, "Разблокировка применима только к пользователям"
                continue
            if op is BulkOperation.DISABLE:
                if uac & UAC.ACCOUNTDISABLE:
                    item.status, item.reason = STATUS_SKIP, "Уже отключена"
                elif "useraccountcontrol" not in allowed_attrs:
                    item.status, item.reason = STATUS_ERROR, "Нет права записи userAccountControl"
                else:
                    item.planned = "userAccountControl: установить ACCOUNTDISABLE"
            elif op is BulkOperation.ENABLE:
                if not uac & UAC.ACCOUNTDISABLE:
                    item.status, item.reason = STATUS_SKIP, "Уже включена"
                elif "useraccountcontrol" not in allowed_attrs:
                    item.status, item.reason = STATUS_ERROR, "Нет права записи userAccountControl"
                else:
                    item.planned = "userAccountControl: снять ACCOUNTDISABLE"
            elif op is BulkOperation.UNLOCK:
                if not locked:
                    item.status, item.reason = STATUS_SKIP, "Не заблокирована"
                elif "lockouttime" not in allowed_attrs:
                    item.status, item.reason = STATUS_ERROR, "Нет права записи lockoutTime"
                else:
                    item.planned = "lockoutTime: 0"
            elif op is BulkOperation.ADD_TO_GROUP:
                if nd in group_members:
                    item.status, item.reason = STATUS_SKIP, "Уже член группы"
                elif not group_writable:
                    item.status, item.reason = STATUS_ERROR, "Нет права изменять состав группы"
                else:
                    item.planned = f"member += {item.name} → {rdn_value(group_dn)}"
            elif op is BulkOperation.REMOVE_FROM_GROUP:
                if nd not in group_members:
                    item.status, item.reason = STATUS_SKIP, "Не является прямым членом группы"
                elif not group_writable:
                    item.status, item.reason = STATUS_ERROR, "Нет права изменять состав группы"
                else:
                    item.planned = f"member −= {item.name} ← {rdn_value(group_dn)}"
            elif op is BulkOperation.MOVE_TO_OU:
                if normalize_dn(parent_dn(item.dn)) == normalize_dn(target_ou):
                    item.status, item.reason = STATUS_SKIP, "Уже находится в целевом OU"
                elif not ou_ok:
                    item.status, item.reason = STATUS_ERROR, ou_reason
                elif self.gw.get(f"{first_rdn(item.dn)},{target_ou}", ["1.1"]) is not None:
                    item.status, item.reason = STATUS_ERROR, "В целевом OU уже есть объект с таким именем"
                else:
                    item.planned = f"{rdn_value(parent_dn(item.dn))} → {rdn_value(target_ou)}"
            elif op is BulkOperation.PREPARE_PASSWORD_RESET:
                item.planned = "Включить в список на сброс пароля (изменения в AD не выполняются)"
        progress(100, "Предварительная проверка завершена")
        return plan

    def _privileged_member_set(self, cancel) -> set[str]:
        from ..ldap.filters import in_chain
        out: set[str] = set()
        for g in self.ctx.privileged.load().values():
            for e in self.gw.search(self.ctx.base_dn, in_chain("memberOf", g.dn), ["1.1"], cancel=cancel):
                out.add(normalize_dn(e.dn))
        return out

    # ---------------------------------------------------------------------------------------------------------
    def execute(self, plan: BulkPlan, *, dry_run: bool = True, rate_per_second: float | None = None,
                cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> BulkPlan:
        if plan.blocked_reason:
            raise ValidationError("Выполнение заблокировано: " + plan.blocked_reason)
        if not plan.operation.modifies:
            dry_run = True
        if not dry_run:
            self.gw._guard_write()
        rate = rate_per_second or self.ctx.settings.bulk_rate_per_second
        delay = 1.0 / max(0.2, rate)
        plan.batch_id = self.ctx.journal.new_batch_id()
        plan.dry_run = dry_run
        ready = plan.ready
        from .computer_service import ComputerService
        from .group_service import GroupService
        from .user_service import UserService
        us, gs, cs = UserService(self.ctx), GroupService(self.ctx), ComputerService(self.ctx)
        op_name = f"bulk.{plan.operation.value}"
        with self.ctx.journal.batch(plan.batch_id):
            self.ctx.journal.record(op_name + ".start", f"{len(ready)} объектов", RESULT_DRY_RUN if dry_run else RESULT_SUCCESS,
                                    details={"params": plan.params, "dry_run": dry_run, "operator": windows_user()})
            for item in plan.items:
                if item.status != STATUS_READY:
                    item.result = "Пропущено" if item.status == STATUS_SKIP else "Не выполнено (ошибка проверки)"
            for n, item in enumerate(ready):
                if cancel and cancel.cancelled:
                    for rest in ready[n:]:
                        rest.result = "Отменено"
                    self.ctx.journal.record(op_name + ".cancelled", f"остановлено на {n}/{len(ready)}", RESULT_SKIPPED)
                    break
                progress(int(n * 100 / max(1, len(ready))), f"{'Моделирование' if dry_run else 'Выполнение'}: {n + 1}/{len(ready)} {item.name}")
                if dry_run:
                    item.result = "Dry Run: изменение смоделировано"
                    self.ctx.journal.record(op_name, item.dn, RESULT_DRY_RUN, details={"planned": item.planned})
                    continue
                try:
                    changed = self._apply(plan, item, us, gs, cs)
                    item.result = "Выполнено" if changed else "Без изменений (уже в нужном состоянии)"
                except OperationCancelledError:
                    item.result = "Отменено"
                    raise
                except ToolkitError as exc:
                    item.result, item.error = "Ошибка", exc.message + (f" ({exc.details})" if exc.details else "")
                except Exception as exc:  # noqa: BLE001 - one object must never stop the batch
                    item.result, item.error = "Ошибка", f"{type(exc).__name__}: {exc}"
                if cancel:
                    if cancel.wait(delay):
                        continue
                else:
                    import time
                    time.sleep(delay)
            counts = plan.result_counts()
            self.ctx.journal.record(op_name + ".finish", f"{len(ready)} объектов",
                                    RESULT_DRY_RUN if dry_run else (RESULT_FAILED if counts.get("Ошибка") else RESULT_SUCCESS),
                                    details={"results": counts})
        plan.executed = True
        plan.finished_at = utcnow()
        progress(100, "Готово")
        return plan

    def _apply(self, plan: BulkPlan, item: BulkItem, us, gs, cs) -> bool:
        op = plan.operation
        if op in (BulkOperation.DISABLE, BulkOperation.ENABLE):
            enable = op is BulkOperation.ENABLE
            if item.object_type == "computer":
                return cs.set_enabled(item.dn, enable)
            return us.set_enabled(item.dn, enable, privileged_confirmed=bool(item.privileged))
        if op is BulkOperation.UNLOCK:
            return us.unlock(item.dn)
        if op is BulkOperation.ADD_TO_GROUP:
            return gs.add_member(plan.params["group_dn"], item.dn, privileged_confirmed=bool(plan.target_privileged))
        if op is BulkOperation.REMOVE_FROM_GROUP:
            return gs.remove_member(plan.params["group_dn"], item.dn, privileged_confirmed=bool(plan.target_privileged))
        if op is BulkOperation.MOVE_TO_OU:
            if item.object_type == "computer":
                cs.move(item.dn, plan.params["target_ou"])
            else:
                us.move(item.dn, plan.params["target_ou"])
            return True
        return False

    # ---------------------------------------------------------------------------------------------------------
    def report(self, plan: BulkPlan) -> ReportTable:
        rows = [{"source": i.source, "name": i.name, "sam": i.sam, "type": i.object_type, "current": i.current,
                 "planned": i.planned, "status": STATUS_LABELS.get(i.status, i.status), "reason": i.reason,
                 "privileged": i.privileged, "result": i.result, "error": i.error, "dn": i.dn} for i in plan.items]
        cols = [("source", "Исходное значение"), ("name", "Объект"), ("sam", "Логин"), ("type", "Тип"),
                ("current", "Текущее состояние"), ("planned", "Планируемое изменение"), ("status", "Предпроверка"),
                ("reason", "Причина пропуска/ошибки"), ("privileged", "Привилегии"), ("result", "Результат"),
                ("error", "Ошибка"), ("dn", "DN")]
        crit = {"Операция": plan.operation.label, "Режим": "Dry Run (без изменений)" if plan.dry_run else "Выполнение",
                "Пакет (batch id)": plan.batch_id, **{k: v for k, v in plan.params.items() if not k.endswith("confirmed")}}
        title = "Результаты массовой операции" if plan.executed else "План массовой операции"
        return ReportTable(title=title, columns=cols, rows=rows, criteria=crit,
                           limitations=["Результат по каждому объекту независим; ошибки одного объекта не прерывают пакет."],
                           generated_at=utcnow(), domain=self.gw.info.domain_dns, dc=self.gw.info.dc_host,
                           generated_by=windows_user())
