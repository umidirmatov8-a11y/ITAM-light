"""User accounts: search / views and safe administrative operations."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from enum import Enum

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import (ConflictError, PasswordPolicyError, ProtectedObjectError, ToolkitError, ValidationError)
from ..ldap import error_mapping as EM
from ..ldap.adtypes import UAC, datetime_to_filetime, utcnow
from ..ldap.demo_data import translit
from ..ldap.dn import child_dn, first_rdn, normalize_dn, parent_dn, rdn_value
from ..ldap.filters import And, Equals, Not, Or, Present, Substring, in_chain
from ..ldap.gateway import ModOp, Scope
from ..ldap.security_descriptor import SD_FLAGS_DACL, cannot_change_password
from ..models.records import UserRecord
from ..security.audit_log import RESULT_SKIPPED
from . import ad_queries as Q
from .common import (QueryResult, ensure_conflict_free, get_or_fail, membership_paths, optimistic_value_change,
                     require_dn, search_records)
from .context import ServiceContext
from .password_service import validate_against_policy


class UserView(str, Enum):
    ALL = "all"
    ENABLED = "enabled"
    DISABLED = "disabled"
    LOCKED = "locked"
    ACCOUNT_EXPIRED = "account_expired"
    ACCOUNT_EXPIRING = "account_expiring"
    PWD_EXPIRED = "pwd_expired"
    PWD_EXPIRING = "pwd_expiring"
    MUST_CHANGE = "must_change"
    PNE = "pne"
    CANNOT_CHANGE = "cannot_change"
    PWD_NOT_REQUIRED = "pwd_not_required"
    STALE = "stale"
    NEVER_LOGGED = "never_logged"
    MISSING_ATTRS = "missing_attrs"
    RECENT = "recent"
    PRIVILEGED = "privileged"

    @property
    def label(self) -> str:
        return USER_VIEW_LABELS[self]


USER_VIEW_LABELS = {
    UserView.ALL: "Все пользователи",
    UserView.ENABLED: "Активные (включённые)",
    UserView.DISABLED: "Отключённые",
    UserView.LOCKED: "Заблокированные",
    UserView.ACCOUNT_EXPIRED: "Срок действия УЗ истёк",
    UserView.ACCOUNT_EXPIRING: "Срок действия УЗ скоро истечёт",
    UserView.PWD_EXPIRED: "Пароль истёк",
    UserView.PWD_EXPIRING: "Пароль скоро истечёт",
    UserView.MUST_CHANGE: "Смена пароля при следующем входе",
    UserView.PNE: "Password Never Expires",
    UserView.CANNOT_CHANGE: "User Cannot Change Password",
    UserView.PWD_NOT_REQUIRED: "Пароль не требуется (PASSWD_NOTREQD)",
    UserView.STALE: "Неактивные (давно не входили)",
    UserView.NEVER_LOGGED: "Нет данных о входе",
    UserView.MISSING_ATTRS: "Неполные атрибуты (отдел/должность/email)",
    UserView.RECENT: "Недавно созданные",
    UserView.PRIVILEGED: "Привилегированные (члены админ-групп)",
}

LASTLOGON_NOTE = ("lastLogonTimestamp реплицируется с задержкой (msDS-LogonTimeSyncInterval, по умолчанию 14 дней "
                  "минус до 5 дней случайно), поэтому «давность входа» может быть занижена до ~19 дней. "
                  "Отсутствие значения не доказывает, что входов не было (вход мог быть до повышения уровня домена, "
                  "по NTLM на другом DC без репликации и т.п.). Точное значение — «Точный последний вход» (опрос всех DC).")

EDITABLE_ATTRIBUTES = {
    "givenName": "Имя", "sn": "Фамилия", "displayName": "Отображаемое имя", "description": "Описание",
    "title": "Должность", "department": "Отдел", "company": "Организация", "mail": "Email",
    "telephoneNumber": "Телефон", "mobile": "Мобильный", "physicalDeliveryOfficeName": "Офис",
    "employeeID": "Табельный номер", "streetAddress": "Адрес", "l": "Город", "st": "Регион",
    "postalCode": "Индекс", "manager": "Руководитель (DN)", "info": "Заметки",
}

COPYABLE_ATTRIBUTES = ["department", "company", "title", "physicalDeliveryOfficeName", "streetAddress", "l", "st",
                       "postalCode", "manager"]

SAM_INVALID = re.compile(r'["/\\\[\]:;|=,+*?<>@]')
MAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class UserQuery:
    view: UserView = UserView.ALL
    text: str = ""
    ou_dn: str = ""
    department: str = ""
    title: str = ""
    stale_days: int = 90
    expiring_days: int = 14
    recent_days: int = 14
    required_attributes: list[str] = field(default_factory=lambda: ["department", "title", "mail"])
    include_disabled_in_stale: bool = False
    limit: int = 5000


@dataclass
class NewUserSpec:
    ou_dn: str
    given_name: str
    surname: str
    sam: str
    upn: str = ""
    display_name: str = ""
    password: str | None = None
    must_change: bool = True
    enabled: bool = True
    attributes: dict = field(default_factory=dict)
    groups: list[str] = field(default_factory=list)
    privileged_groups_confirmed: bool = False
    account_expires: date | None = None

    def __repr__(self) -> str:  # never show the password
        return f"NewUserSpec(ou={self.ou_dn!r}, sam={self.sam!r}, groups={len(self.groups)})"


@dataclass
class CreateResult:
    dn: str
    warnings: list[str] = field(default_factory=list)
    enabled: bool = False


def make_sam(pattern: str, given: str, sn: str) -> str:
    g, s = given.strip(), sn.strip()
    values = {
        "given": g.lower(), "sn": s.lower(), "g": g[:1].lower(), "s": s[:1].lower(),
        "given_lat": translit(g), "sn_lat": translit(s), "g_lat": translit(g)[:1], "s_lat": translit(s)[:1],
    }
    try:
        out = (pattern or "{g_lat}.{sn_lat}").format(**values)
    except (KeyError, IndexError) as exc:
        raise ValidationError(f"Некорректный шаблон имени входа: {pattern}", details=str(exc)) from None
    out = re.sub(r"[^A-Za-z0-9._-]", "", out)
    return out[:20]


def expiry_to_filetime(d: date | None) -> int:
    """AD semantics (as in ADUC): the account expires at the *start of the next day* in local time."""
    if d is None:
        return 0
    local_next = datetime.combine(d + timedelta(days=1), dtime.min).astimezone()
    return datetime_to_filetime(local_next)


class UserService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.gw = ctx.gateway

    # ==========================================================================================================
    # Search & views
    # ==========================================================================================================
    def build_filter(self, q: UserQuery):
        now = utcnow()
        notes: list[str] = []
        parts = [Q.IS_USER]
        text = (q.text or "").strip()
        if text:
            parts.append(Q.user_text_filter(text))
        if q.department.strip():
            parts.append(Substring("department", any=(q.department.strip(),)))
        if q.title.strip():
            parts.append(Substring("title", any=(q.title.strip(),)))
        v = q.view
        if v is UserView.ENABLED:
            parts.append(Q.ENABLED)
        elif v is UserView.DISABLED:
            parts.append(Q.DISABLED)
        elif v is UserView.LOCKED:
            parts.append(Q.LOCKOUT_CANDIDATE)
            notes.append("Блокировка определяется по вычисляемому атрибуту msDS-User-Account-Control-Computed "
                         "(учитывает автоматическую разблокировку по lockoutDuration).")
        elif v is UserView.ACCOUNT_EXPIRED:
            parts.append(Q.account_expired(now))
        elif v is UserView.ACCOUNT_EXPIRING:
            from ..ldap.filters import ge, le
            parts += [ge("accountExpires", datetime_to_filetime(now)),
                      le("accountExpires", datetime_to_filetime(now + timedelta(days=q.expiring_days)))]
        elif v in (UserView.PWD_EXPIRED, UserView.PWD_EXPIRING):
            parts += [Q.ENABLED, Not(Q.PASSWORD_NEVER_EXPIRES)]
            notes.append("Срок действия пароля — по msDS-UserPasswordExpiryTimeComputed (учитывает PSO).")
        elif v is UserView.MUST_CHANGE:
            parts.append(Equals("pwdLastSet", 0))
        elif v is UserView.PNE:
            parts.append(Q.PASSWORD_NEVER_EXPIRES)
        elif v is UserView.PWD_NOT_REQUIRED:
            parts.append(Q.PASSWD_NOTREQD)
        elif v is UserView.STALE:
            if not q.include_disabled_in_stale:
                parts.append(Q.ENABLED)
            parts += [Q.stale_logon_filter(q.stale_days, now), Q.created_before(q.stale_days, now)]
            notes.append(LASTLOGON_NOTE)
        elif v is UserView.NEVER_LOGGED:
            parts.append(Not(Present("lastLogonTimestamp")))
            notes.append(LASTLOGON_NOTE)
        elif v is UserView.MISSING_ATTRS:
            parts.append(Q.missing_any(q.required_attributes or ["department", "title", "mail"]))
        elif v is UserView.RECENT:
            parts.append(Q.created_since(q.recent_days, now))
        elif v is UserView.CANNOT_CHANGE:
            notes.append("«User cannot change password» хранится не в userAccountControl, а в ACL объекта "
                         "(запрещающие ACE «Change Password» для Everyone/SELF). Требуется право чтения nTSecurityDescriptor.")
        return And(*parts), notes

    def search(self, q: UserQuery, cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> QueryResult:
        base = q.ou_dn.strip() or self.ctx.base_dn
        require_dn(base, "контейнер поиска")
        flt, notes = self.build_filter(q)
        policy = self.ctx.policy
        now = utcnow()
        progress(None, "Поиск пользователей…")
        attrs = list(Q.USER_ATTRIBUTES)
        sd_flags = None
        if q.view is UserView.CANNOT_CHANGE:
            attrs.append("nTSecurityDescriptor")
            sd_flags = SD_FLAGS_DACL
        text = (q.text or "").strip()
        if text and "=" in text and "," in text:
            # looks like a DN — substring matching is not supported for DN syntax in AD, so read it directly
            e = self.gw.get(text, attrs)
            entries = [e] if e is not None else []
            from ..ldap.gateway import SearchStats
            stats = SearchStats(entries=len(entries))
            records = [UserRecord.from_entry(e, policy, now) for e in entries if "user" in e.object_classes and "computer" not in e.object_classes]
        else:
            records_entries, stats = search_records(self.gw, base, flt, attrs, lambda e: e, limit=q.limit, cancel=cancel,
                                                    sd_flags=sd_flags)
            records = []
            for e in records_entries:
                r = UserRecord.from_entry(e, policy, now)
                if sd_flags is not None:
                    raw = e.first("nTSecurityDescriptor")
                    if raw:
                        try:
                            r.cannot_change_password, _ = cannot_change_password(raw)
                        except ValueError:
                            r.cannot_change_password = None
                    if not r.cannot_change_password and r.uac & UAC.PASSWD_CANT_CHANGE:
                        r.cannot_change_password = True
                records.append(r)
        records = self._post_filter(q, records, now)
        if q.view is UserView.PRIVILEGED:
            records = self._privileged_only(records, cancel)
        if q.view is UserView.CANNOT_CHANGE and any(r.cannot_change_password is None for r in records):
            notes.append("Для части объектов дескриптор безопасности не прочитан (нет прав) — результат неполный.")
        if records and all(not r.locked_exact for r in records) and q.view is UserView.LOCKED:
            notes.append("Вычисляемый атрибут блокировки недоступен — состояние оценено по lockoutTime и lockoutDuration.")
        if stats.truncated:
            notes.append(f"Показаны первые {len(records)} объектов — уточните условия поиска.")
        progress(100, f"Найдено: {len(records)}")
        return QueryResult(items=records, truncated=stats.truncated, notes=notes, filter_text=flt.to_ldap(), base_dn=base,
                           criteria={"Представление": q.view.label, "Текст": q.text, "OU": base,
                                     "Отдел": q.department, "Должность": q.title,
                                     **({"Период неактивности, дней": q.stale_days} if q.view is UserView.STALE else {}),
                                     **({"Окно, дней": q.expiring_days} if q.view in (UserView.PWD_EXPIRING, UserView.ACCOUNT_EXPIRING) else {}),
                                     **({"Создано за, дней": q.recent_days} if q.view is UserView.RECENT else {})})

    def _post_filter(self, q: UserQuery, records: list[UserRecord], now: datetime) -> list[UserRecord]:
        v = q.view
        if v is UserView.LOCKED:
            return [r for r in records if r.locked]
        if v is UserView.PWD_EXPIRED:
            return [r for r in records if r.pwd_expired]
        if v is UserView.PWD_EXPIRING:
            horizon = now + timedelta(days=q.expiring_days)
            return [r for r in records if not r.pwd_expired and r.pwd_expires and now <= r.pwd_expires <= horizon]
        if v is UserView.CANNOT_CHANGE:
            return [r for r in records if r.cannot_change_password is not False]
        return records

    def _privileged_only(self, records: list[UserRecord], cancel: CancelToken | None) -> list[UserRecord]:
        priv = self.ctx.privileged.load()
        members: set[str] = set()
        for g in priv.values():
            if cancel:
                cancel.raise_if_cancelled()
            for e in self.gw.search(self.ctx.base_dn, And(Q.IS_USER, in_chain("memberOf", g.dn)), ["1.1"], cancel=cancel):
                members.add(normalize_dn(e.dn))
        return [r for r in records if normalize_dn(r.dn) in members or r.admin_count]

    def get(self, dn: str) -> UserRecord:
        e = get_or_fail(self.gw, dn, Q.USER_ATTRIBUTES + ["nTSecurityDescriptor"])
        r = UserRecord.from_entry(e, self.ctx.policy)
        raw = e.first("nTSecurityDescriptor")
        if raw:
            try:
                r.cannot_change_password, _ = cannot_change_password(raw)
            except ValueError:
                pass
        return r

    def get_with_sd(self, dn: str) -> tuple[UserRecord, list[str]]:
        e = self.gw.get(require_dn(dn), Q.USER_ATTRIBUTES + ["nTSecurityDescriptor"], sd_flags=SD_FLAGS_DACL)
        if e is None:
            from ..core.errors import ObjectNotFoundError
            raise ObjectNotFoundError(f"Объект не найден: {dn}")
        r = UserRecord.from_entry(e, self.ctx.policy)
        who: list[str] = []
        raw = e.first("nTSecurityDescriptor")
        if raw:
            r.cannot_change_password, who = cannot_change_password(raw)
        return r, who

    def raw_attributes(self, dn: str) -> dict:
        e = get_or_fail(self.gw, dn, ["*", "msDS-User-Account-Control-Computed", "msDS-UserPasswordExpiryTimeComputed",
                                      "memberOf", "allowedAttributesEffective"])
        return dict(e.attributes.items())

    def find_by_identity(self, identity: str, attributes: list[str] | None = None) -> list:
        ident = (identity or "").strip()
        if not ident:
            return []
        if "=" in ident and "," in ident:
            e = self.gw.get(ident, attributes or Q.USER_ATTRIBUTES)
            return [e] if e is not None else []
        if "\\" in ident:
            ident = ident.split("\\", 1)[1]
        flt = And(Q.IS_USER, Or(Equals("sAMAccountName", ident), Equals("userPrincipalName", ident),
                                Equals("mail", ident), Equals("employeeID", ident)))
        return self.gw.search_list(self.ctx.base_dn, flt, attributes or Q.USER_ATTRIBUTES, size_limit=10)

    def group_paths(self, dn: str, cancel: CancelToken | None = None) -> list[dict]:
        return membership_paths(self.gw, dn, cancel=cancel)

    def precise_last_logon(self, dn: str, cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> list[dict]:
        """Query lastLogon (not replicated) on every domain controller."""
        dcs = list(self.gw.info.domain_controllers) or [self.gw.info.dc_host]
        out = []
        for i, host in enumerate(dcs):
            if cancel:
                cancel.raise_if_cancelled()
            progress(int(i * 100 / max(1, len(dcs))), f"Опрос {host}…")
            row = {"dc": host, "last_logon": None, "error": ""}
            try:
                clone = self.gw.clone_for_host(host) if host != self.gw.info.dc_host else self.gw
                try:
                    e = clone.get(dn, ["lastLogon"])
                    from ..ldap.adtypes import filetime_to_datetime
                    row["last_logon"] = filetime_to_datetime(e.first("lastLogon")) if e else None
                finally:
                    if clone is not self.gw:
                        clone.close()
            except ToolkitError as exc:
                row["error"] = exc.message
            except NotImplementedError:
                row["error"] = "Не поддерживается"
            out.append(row)
        progress(100, "Готово")
        return out

    # ==========================================================================================================
    # Privileged account protection
    # ==========================================================================================================
    def privileged_reason(self, dn: str) -> str:
        groups = self.ctx.privileged.privileged_memberships(dn)
        if groups:
            return "Член привилегированных групп: " + ", ".join(sorted({g.name for g in groups}))
        e = self.gw.get(dn, ["adminCount"])
        if e is not None and e.int("adminCount") == 1:
            return "adminCount=1 (объект был/является членом защищённой группы)"
        return ""

    def _guard_privileged(self, dn: str, confirmed: bool, action: str) -> None:
        reason = self.privileged_reason(dn)
        if reason and not confirmed:
            raise ProtectedObjectError(f"«{action}» для привилегированной учётной записи требует отдельного подтверждения",
                                       details=reason)

    # ==========================================================================================================
    # Administrative operations (each: permission pre-check, journal, typed errors)
    # ==========================================================================================================
    def set_enabled(self, dn: str, enabled: bool, *, privileged_confirmed: bool = False) -> bool:
        """Returns False if the account was already in the requested state (recorded as skipped)."""
        action = "Включение учётной записи" if enabled else "Отключение учётной записи"
        op = "user.enable" if enabled else "user.disable"
        self.gw._guard_write()
        e = get_or_fail(self.gw, dn, ["userAccountControl", "sAMAccountName"])
        uac = e.int("userAccountControl", 0) or 0
        new = (uac & ~int(UAC.ACCOUNTDISABLE)) if enabled else (uac | int(UAC.ACCOUNTDISABLE))
        if new == uac:
            self.ctx.journal.record(op, dn, RESULT_SKIPPED, details={"reason": "уже в требуемом состоянии"})
            return False
        with self.ctx.journal.track(op, dn):
            if e.str("sAMAccountName").lower() == "krbtgt":
                raise ProtectedObjectError("Учётная запись krbtgt не изменяется через приложение")
            if not enabled:
                self._guard_privileged(dn, privileged_confirmed, action)
            self.ctx.permissions.require_write(dn, ["userAccountControl"], action)
            self.gw.modify(dn, optimistic_value_change("userAccountControl", uac, new))
        return True

    def unlock(self, dn: str) -> bool:
        self.gw._guard_write()
        e = get_or_fail(self.gw, dn, ["lockoutTime"])
        if not (e.int("lockoutTime", 0) or 0):
            self.ctx.journal.record("user.unlock", dn, RESULT_SKIPPED, details={"reason": "не заблокирована"})
            return False
        with self.ctx.journal.track("user.unlock", dn):
            self.ctx.permissions.require_write(dn, ["lockoutTime"], "Разблокировка")
            self.gw.modify(dn, {"lockoutTime": [(ModOp.REPLACE, [0])]})
        return True

    def reset_password(self, dn: str, new_password: str, *, must_change: bool = True, unlock: bool = False,
                       privileged_confirmed: bool = False) -> None:
        details = {"must_change": must_change, "unlock": unlock}
        with self.ctx.journal.track("user.reset_password", dn, details=details):
            self.gw._guard_write()
            self.gw._require_encryption("Сброс пароля")
            e = get_or_fail(self.gw, dn, ["sAMAccountName", "displayName"])
            self._guard_privileged(dn, privileged_confirmed, "Сброс пароля")
            problems = validate_against_policy(new_password, self.ctx.policy, e.str("sAMAccountName"), e.str("displayName"))
            if problems:
                raise PasswordPolicyError("Пароль не соответствует политике домена: " + "; ".join(problems))
            try:
                self.gw.set_password(dn, new_password)
            except ToolkitError as exc:
                if exc.code == EM.INSUFFICIENT_ACCESS_RIGHTS:
                    exc.hint = "Для сброса требуется расширенное право «Reset Password» на объект."
                raise
            if must_change:
                self.gw.modify(dn, {"pwdLastSet": [(ModOp.REPLACE, [0])]})
            if unlock:
                self.gw.modify(dn, {"lockoutTime": [(ModOp.REPLACE, [0])]})

    def set_must_change(self, dn: str, must_change: bool) -> None:
        with self.ctx.journal.track("user.must_change_password", dn, details={"value": must_change}):
            self.ctx.permissions.require_write(dn, ["pwdLastSet"], "Смена пароля при следующем входе")
            # 0 = must change; -1 = set pwdLastSet to the current time (clears the flag)
            self.gw.modify(dn, {"pwdLastSet": [(ModOp.REPLACE, [0 if must_change else -1])]})

    def update_attributes(self, dn: str, new_values: dict, original: dict) -> list[str]:
        """Change editable attributes with optimistic concurrency; returns the list of changed attributes."""
        unknown = [a for a in new_values if a not in EDITABLE_ATTRIBUTES]
        if unknown:
            raise ValidationError("Эти атрибуты нельзя изменять через форму: " + ", ".join(unknown))
        changes = {}
        for attr, new in new_values.items():
            new = (new or "").strip() if isinstance(new, str) else new
            old = original.get(attr)
            if attr == "mail" and new and not MAIL_RE.match(new):
                raise ValidationError(f"Некорректный email: {new}")
            if attr == "manager" and new:
                require_dn(new, "DN руководителя")
                if self.gw.get(new, ["distinguishedName"]) is None:
                    raise ValidationError(f"Руководитель не найден: {new}")
            if attr == "displayName" and new is not None and len(new) > 256:
                raise ValidationError("Слишком длинное отображаемое имя")
            changes.update(optimistic_value_change(attr, old or None, new or None))
        if not changes:
            return []
        with self.ctx.journal.track("user.update_attributes", dn, details={"attributes": sorted(changes)}):
            self.ctx.permissions.require_write(dn, list(changes), "Изменение атрибутов")
            self.gw.modify(dn, changes)
        return sorted(changes)

    def set_account_expiry(self, dn: str, expires: date | None) -> None:
        value = expiry_to_filetime(expires)
        with self.ctx.journal.track("user.account_expires", dn, details={"expires": str(expires) if expires else "никогда"}):
            self.ctx.permissions.require_write(dn, ["accountExpires"], "Изменение срока действия")
            self.gw.modify(dn, {"accountExpires": [(ModOp.REPLACE, [value])]})

    def move(self, dn: str, target_ou: str) -> str:
        with self.ctx.journal.track("user.move", dn, details={"target": target_ou}):
            from .ou_service import OUService
            OUService(self.ctx).validate_move_target(dn, target_ou, "user")
            return self.gw.move(dn, target_ou)

    # ==========================================================================================================
    # Creation
    # ==========================================================================================================
    def validate_new_user(self, spec: NewUserSpec) -> list[str]:
        problems = []
        if not spec.given_name.strip() and not spec.surname.strip():
            problems.append("Укажите имя или фамилию")
        sam = spec.sam.strip()
        if not sam:
            problems.append("Не задано имя входа (sAMAccountName)")
        elif len(sam) > 20:
            problems.append("sAMAccountName длиннее 20 символов")
        elif SAM_INVALID.search(sam) or sam.endswith("."):
            problems.append("sAMAccountName содержит недопустимые символы")
        if spec.upn and not re.match(r"^[^@\s]+@[^@\s]+$", spec.upn):
            problems.append("Некорректный UPN")
        if spec.enabled and not spec.password:
            problems.append("Для включённой учётной записи необходимо задать пароль")
        if spec.password:
            problems += validate_against_policy(spec.password, self.ctx.policy, sam,
                                                spec.display_name or f"{spec.surname} {spec.given_name}")
        try:
            require_dn(spec.ou_dn, "OU")
        except ValidationError as exc:
            problems.append(exc.message)
        return problems

    def create_user(self, spec: NewUserSpec) -> CreateResult:
        problems = self.validate_new_user(spec)
        if problems:
            raise ValidationError("Проверка данных не пройдена:\n• " + "\n• ".join(problems))
        display = spec.display_name.strip() or f"{spec.surname.strip()} {spec.given_name.strip()}".strip()
        dn = child_dn(spec.ou_dn, "CN", display)
        with self.ctx.journal.track("user.create", dn, details={"sam": spec.sam, "groups": len(spec.groups)}):
            self.gw._guard_write()
            if spec.password:
                self.gw._require_encryption("Создание пользователя с паролем")
            existing = self.gw.search_list(self.ctx.base_dn, Or(Equals("sAMAccountName", spec.sam),
                                                                 *([Equals("userPrincipalName", spec.upn)] if spec.upn else [])),
                                           ["sAMAccountName"], size_limit=2)
            if existing:
                raise ConflictError(f"Имя входа или UPN уже используется: {existing[0].dn}")
            ensure_conflict_free(self.gw, spec.ou_dn, first_rdn(dn))
            self.ctx.permissions.require_create(spec.ou_dn, "user", "Создание пользователя")
            for g in spec.groups:
                if not spec.privileged_groups_confirmed and self.ctx.privileged.classify_group(g)[0]:
                    raise ProtectedObjectError(f"Добавление в привилегированную группу требует отдельного подтверждения: {rdn_value(g)}")
            attrs = {"givenName": spec.given_name.strip() or None, "sn": spec.surname.strip() or None,
                     "displayName": display, "sAMAccountName": spec.sam.strip(),
                     "userPrincipalName": spec.upn.strip() or None, "userAccountControl": 0x202}
            for k, v in spec.attributes.items():
                if k in EDITABLE_ATTRIBUTES and v not in (None, ""):
                    attrs[k] = v
            if spec.account_expires:
                attrs["accountExpires"] = expiry_to_filetime(spec.account_expires)
            self.gw.add(dn, ["top", "person", "organizationalPerson", "user"], attrs)
            result = CreateResult(dn=dn)
            if spec.password:
                try:
                    self.gw.set_password(dn, spec.password)
                    if spec.must_change:
                        self.gw.modify(dn, {"pwdLastSet": [(ModOp.REPLACE, [0])]})
                    if spec.enabled:
                        self.gw.modify(dn, optimistic_value_change("userAccountControl", 0x202, 0x200))
                        result.enabled = True
                except ToolkitError as exc:
                    result.warnings.append(f"Учётная запись создана ОТКЛЮЧЁННОЙ: пароль не установлен ({exc.message})")
            from .group_service import GroupService
            gs = GroupService(self.ctx)
            for g in spec.groups:
                try:
                    gs.add_member(g, dn, privileged_confirmed=spec.privileged_groups_confirmed)
                except ToolkitError as exc:
                    result.warnings.append(f"Группа {rdn_value(g)}: {exc.message}")
            return result

    def spec_from_template(self, template: dict, given: str, surname: str) -> NewUserSpec:
        sam = make_sam(template.get("sam_pattern") or "{g_lat}.{sn_lat}", given, surname)
        suffix = template.get("upn_suffix") or self.ctx.settings.upn_suffix or self.gw.info.domain_dns
        return NewUserSpec(ou_dn=template.get("ou_dn") or f"CN=Users,{self.ctx.base_dn}", given_name=given,
                           surname=surname, sam=sam, upn=f"{sam}@{suffix}" if suffix else "",
                           must_change=bool(template.get("must_change", True)), enabled=bool(template.get("enabled", True)),
                           attributes=dict(template.get("attributes") or {}), groups=list(template.get("groups") or []))

    def spec_copy_from(self, source_dn: str, given: str, surname: str, *, include_privileged: bool = False) -> tuple[NewUserSpec, list[str]]:
        """Copy allowed attributes and group memberships from an existing user."""
        src = get_or_fail(self.gw, source_dn, COPYABLE_ATTRIBUTES + ["memberOf", "userPrincipalName"])
        notes = []
        groups = []
        for g in src.values("memberOf"):
            privileged, reason, _ = self.ctx.privileged.classify_group(g)
            if privileged and not include_privileged:
                notes.append(f"Не скопирована привилегированная группа {rdn_value(g)} ({reason})")
                continue
            groups.append(g)
        upn_suffix = src.str("userPrincipalName").split("@", 1)[1] if "@" in src.str("userPrincipalName") else self.gw.info.domain_dns
        sam = make_sam("{g_lat}.{sn_lat}", given, surname)
        attrs = {a: src.str(a) for a in COPYABLE_ATTRIBUTES if src.str(a)}
        notes.append("Не копируются: пароль, имя, email, телефон, табельный номер, описание.")
        return NewUserSpec(ou_dn=parent_dn(source_dn), given_name=given, surname=surname, sam=sam,
                           upn=f"{sam}@{upn_suffix}", attributes=attrs, groups=groups), notes

    def scope_note(self) -> str:
        return LASTLOGON_NOTE


__all__ = ["UserService", "UserQuery", "UserView", "NewUserSpec", "CreateResult", "EDITABLE_ATTRIBUTES", "make_sam",
           "LASTLOGON_NOTE", "Scope"]
