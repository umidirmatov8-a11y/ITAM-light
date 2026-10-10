"""Security and hygiene audit of the directory.

Every finding is labelled as a *fact* (read directly from AD), an indicator that *requires review*, or a value with
*limited precision*. An inactive account is an object to review — not evidence of compromise.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import OperationCancelledError, ToolkitError
from ..ldap.adtypes import UAC, utcnow
from ..ldap.dn import is_descendant, normalize_dn, rdn_value
from ..ldap.filters import And, Equals, Not, Or, Present, in_chain
from ..models.records import CheckResult, ComputerRecord, Evidence, Finding, OsSupport, Severity, UserRecord
from . import ad_queries as Q
from .common import TYPE_LABELS, object_type_of, resolve_dns
from .computer_service import classify_os
from .context import ServiceContext
from .user_service import LASTLOGON_NOTE


@dataclass
class CheckDef:
    check_id: str
    title: str
    description: str
    fn: Callable


class AuditService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.gw = ctx.gateway
        self._priv_members: dict[str, list[str]] | None = None
        self.checks: list[CheckDef] = [
            CheckDef("disabled_users", "Отключённые пользователи", "Учётные записи с флагом ACCOUNTDISABLE", self.check_disabled_users),
            CheckDef("locked_users", "Заблокированные пользователи", "Текущая блокировка (вычисляемый флаг)", self.check_locked_users),
            CheckDef("stale_users", "Неактивные пользователи", "Включённые УЗ без входа дольше заданного периода", self.check_stale_users),
            CheckDef("stale_computers", "Неактивные компьютеры", "Включённые компьютеры без входа дольше периода", self.check_stale_computers),
            CheckDef("pne", "Password Never Expires", "Пароль без срока действия", self.check_pne),
            CheckDef("account_expiry_policy", "Учётные записи без срока действия", "УЗ без accountExpires в OU, где политика требует срок", self.check_expiry_policy),
            CheckDef("privileged", "Члены привилегированных групп", "Прямое и вложенное членство в админ-группах", self.check_privileged),
            CheckDef("unusual_membership", "Необычные членства", "Вложенные группы в критичных группах, циклы, orphaned adminCount", self.check_unusual_membership),
            CheckDef("incomplete", "Неполные атрибуты", "Отсутствуют обязательные атрибуты организации", self.check_incomplete),
            CheckDef("suspicious", "Подозрительные/несогласованные атрибуты", "Опасные флаги UAC, SPN у привилегированных, старые пароли", self.check_suspicious),
            CheckDef("outdated_os", "Устаревшие ОС", "Компьютеры с ОС вне поддержки (по правилам настроек)", self.check_outdated_os),
            CheckDef("recent", "Недавно созданные объекты", "Пользователи, компьютеры, группы за период", self.check_recent),
            CheckDef("dc_availability", "Доступность контроллеров домена", "DNS, TCP 389/636/88, TLS-сертификат", self.check_dcs),
            CheckDef("connection", "Корректность подключения", "Шифрование, права учётной записи подключения, квоты", self.check_connection),
        ]

    def run(self, check_ids: list[str] | None = None, cancel: CancelToken | None = None,
            progress: Progress = NULL_PROGRESS) -> list[CheckResult]:
        selected = [c for c in self.checks if not check_ids or c.check_id in check_ids]
        results = []
        for i, c in enumerate(selected):
            if cancel:
                cancel.raise_if_cancelled()
            progress(int(i * 100 / max(1, len(selected))), f"Проверка: {c.title}")
            res = CheckResult(c.check_id, c.title, c.description)
            t = time.monotonic()
            try:
                c.fn(res, cancel)
            except OperationCancelledError:
                raise
            except ToolkitError as exc:
                res.error = exc.message
            except Exception as exc:  # noqa: BLE001 - a broken check must not stop the audit
                res.error = f"{type(exc).__name__}: {exc}"
            res.duration_s = round(time.monotonic() - t, 2)
            results.append(res)
        progress(100, "Аудит завершён")
        return results

    @staticmethod
    def summary(results: list[CheckResult]) -> dict:
        counts = {s: 0 for s in Severity}
        evidence = {e: 0 for e in Evidence}
        for r in results:
            for f in r.findings:
                counts[f.severity] += 1
                evidence[f.evidence] += 1
        return {"by_severity": counts, "by_evidence": evidence, "checks": len(results),
                "failed_checks": [r.title for r in results if r.error], "total": sum(counts.values())}

    # ---------------------------------------------------------------------------------------------------------
    def _users(self, flt, attrs=None, cancel=None) -> list[UserRecord]:
        policy = self.ctx.policy
        now = utcnow()
        return [UserRecord.from_entry(e, policy, now)
                for e in self.gw.search(self.ctx.base_dn, flt, attrs or Q.USER_ATTRIBUTES, cancel=cancel)]

    def _privileged_members(self, cancel=None) -> dict[str, list[str]]:
        """normalized member DN -> list of privileged group names (transitive)."""
        if self._priv_members is not None:
            return self._priv_members
        out: dict[str, list[str]] = {}
        for g in self.ctx.privileged.load().values():
            for e in self.gw.search(self.ctx.base_dn, in_chain("memberOf", g.dn), ["1.1"], cancel=cancel):
                out.setdefault(normalize_dn(e.dn), []).append(g.name)
        self._priv_members = out
        return out

    def check_disabled_users(self, res: CheckResult, cancel):
        for u in self._users(Q.USERS_DISABLED, cancel=cancel):
            res.findings.append(Finding("disabled_users", "Отключённая учётная запись", Severity.INFO, Evidence.FACT, u.dn,
                                        u.name, f"Изменена: {u.when_changed:%Y-%m-%d}" if u.when_changed else "",
                                        "Проверьте срок хранения отключённых УЗ по регламенту; удаляйте после истечения."))

    def check_locked_users(self, res: CheckResult, cancel):
        for u in self._users(Q.USERS_LOCKED_CANDIDATES, cancel=cancel):
            if not u.locked:
                continue
            res.findings.append(Finding("locked_users", "Учётная запись заблокирована", Severity.MEDIUM,
                                        Evidence.FACT if u.locked_exact else Evidence.LIMITED, u.dn, u.name,
                                        f"lockoutTime: {u.lockout_time:%Y-%m-%d %H:%M}" if u.lockout_time else "",
                                        "Выясните источник неверных паролей (событие 4740 на PDC-эмуляторе) до разблокировки."))

    def check_stale_users(self, res: CheckResult, cancel):
        days = self.ctx.settings.stale_user_days
        now = utcnow()
        flt = And(Q.IS_USER, Q.ENABLED, Q.stale_logon_filter(days, now), Q.created_before(days, now))
        res.limitations = LASTLOGON_NOTE
        for u in self._users(flt, cancel=cancel):
            d = u.days_since_logon(now)
            text = f"Последний вход (lastLogonTimestamp): {d} дн. назад" if d is not None else "Данных о входе нет (lastLogonTimestamp пуст)"
            res.findings.append(Finding("stale_users", "Неактивная учётная запись", Severity.MEDIUM,
                                        Evidence.LIMITED if d is None else Evidence.REVIEW, u.dn, u.name, text,
                                        "Уточните у владельца/руководителя; при подтверждении — отключите (Dry Run в массовых операциях). "
                                        "Это объект для проверки, а не признак компрометации."))

    def check_stale_computers(self, res: CheckResult, cancel):
        days = self.ctx.settings.stale_computer_days
        now = utcnow()
        flt = And(Q.IS_COMPUTER, Q.ENABLED, Q.stale_logon_filter(days, now), Q.created_before(days, now))
        res.limitations = "По lastLogonTimestamp; сетевую доступность проверяйте отдельно."
        for e in self.gw.search(self.ctx.base_dn, flt, Q.COMPUTER_ATTRIBUTES, cancel=cancel):
            c = ComputerRecord.from_entry(e)
            if c.is_dc:
                continue
            d = c.days_since_logon(now)
            res.findings.append(Finding("stale_computers", "Неактивный компьютер", Severity.LOW, Evidence.REVIEW, c.dn, c.name,
                                        f"Последний вход: {d} дн. назад" if d is not None else "Данных о входе нет",
                                        "Проверьте доступность (ping/TCP) и наличие в CMDB; затем отключите и переместите."))

    def check_pne(self, res: CheckResult, cancel):
        priv = self._privileged_members(cancel)
        for u in self._users(And(Q.IS_USER, Q.ENABLED, Q.PASSWORD_NEVER_EXPIRES), cancel=cancel):
            p = priv.get(normalize_dn(u.dn))
            sev = Severity.HIGH if p else Severity.MEDIUM
            details = ("Привилегированная УЗ: " + ", ".join(p) + ". ") if p else ""
            if u.pwd_last_set:
                details += f"Пароль установлен: {u.pwd_last_set:%Y-%m-%d}"
            res.findings.append(Finding("pne", "Пароль без срока действия", sev, Evidence.FACT, u.dn, u.name, details,
                                        "Для сервисов используйте gMSA; для людей — уберите флаг."))

    def check_expiry_policy(self, res: CheckResult, cancel):
        ous = self.ctx.settings.require_account_expiry_ous
        if not ous:
            res.limitations = "Политика не задана: укажите OU в Настройки → «OU с обязательным сроком действия УЗ»."
            return
        users = self._users(And(Q.IS_USER, Q.ENABLED), cancel=cancel)
        for ou in ous:
            for u in users:
                if is_descendant(u.dn, ou) and u.account_expires is None:
                    res.findings.append(Finding("account_expiry_policy", "Нет срока действия УЗ", Severity.MEDIUM,
                                                Evidence.FACT, u.dn, u.name, f"OU политики: {ou}",
                                                "Установите срок действия согласно договору (подрядчики, временные сотрудники)."))

    def check_privileged(self, res: CheckResult, cancel):
        priv = self._privileged_members(cancel)
        if not priv:
            res.limitations = "Привилегированные группы не найдены или нет прав на чтение."
            return
        attrs = Q.USER_ATTRIBUTES + ["servicePrincipalName"]
        policy = self.ctx.policy
        now = utcnow()
        resolved = resolve_dns(self.gw, [e for e in priv], attrs, cancel=cancel)
        for nd, groups in priv.items():
            e = resolved.get(nd)
            if e is None:
                continue
            if "user" not in e.object_classes or "computer" in e.object_classes:
                if "group" in e.object_classes:
                    continue
                res.findings.append(Finding("privileged", "Компьютер/иной объект в привилегированной группе", Severity.HIGH,
                                            Evidence.REVIEW, e.dn, rdn_value(e.dn), "Группы: " + ", ".join(groups),
                                            "Проверьте обоснованность членства."))
                continue
            u = UserRecord.from_entry(e, policy, now)
            sev = Severity.INFO
            notes = []
            if not u.enabled:
                sev, notes = Severity.MEDIUM, ["отключена, но остаётся в группе"]
            if u.pwd_never_expires:
                sev = Severity.HIGH
                notes.append("Password Never Expires")
            d = u.days_since_logon(now)
            if u.enabled and (d is None or d > self.ctx.settings.stale_user_days):
                sev = min(sev, Severity.MEDIUM, key=lambda x: x.rank)
                notes.append("давно не входила" if d is not None else "нет данных о входе")
            if e.values("servicePrincipalName"):
                sev = Severity.HIGH
                notes.append("имеет SPN (возможен Kerberoasting)")
            if u.sam.lower().startswith(("svc", "srv", "service")):
                sev = Severity.HIGH if sev.rank > Severity.HIGH.rank else sev
                notes.append("сервисная УЗ в админ-группе")
            res.findings.append(Finding("privileged", "Член привилегированной группы", sev,
                                        Evidence.FACT if sev is Severity.INFO else Evidence.REVIEW, u.dn, u.name,
                                        "Группы: " + ", ".join(sorted(set(groups))) + ("; " + "; ".join(notes) if notes else ""),
                                        "Минимизируйте состав; используйте отдельные админ-УЗ и модель уровней (tiering)."))

    def check_unusual_membership(self, res: CheckResult, cancel):
        from .group_service import GroupService
        gs = GroupService(self.ctx)
        priv = self.ctx.privileged.load()
        for pg in priv.values():
            if not pg.critical:
                continue
            for row in gs.direct_members(pg.dn, cancel, include_primary=False):
                if row.object_type == "group" and normalize_dn(row.dn) not in priv:
                    res.findings.append(Finding("unusual_membership", "Вложенная группа в критичной группе", Severity.HIGH,
                                                Evidence.REVIEW, row.dn, row.name, f"Вложена в {pg.name}",
                                                "Все члены вложенной группы получают права администратора — проверьте необходимость."))
        # orphaned adminCount: adminCount=1 but no longer in protected groups (permissions inheritance stays disabled)
        priv_members = self._privileged_members(cancel)
        for e in self.gw.search(self.ctx.base_dn, And(Q.IS_USER, Equals("adminCount", 1)), ["cn", "sAMAccountName"], cancel=cancel):
            if normalize_dn(e.dn) not in priv_members:
                res.findings.append(Finding("unusual_membership", "adminCount=1 без членства в защищённых группах",
                                            Severity.LOW, Evidence.REVIEW, e.dn, e.str("cn"),
                                            "Наследование разрешений могло остаться отключённым (AdminSDHolder).",
                                            "Проверьте и при необходимости сбросьте adminCount и включите наследование."))
        # membership cycles among groups
        seen_cycle: set[str] = set()
        groups = {normalize_dn(e.dn): e for e in self.gw.search(self.ctx.base_dn, And(Q.IS_GROUP, Present("member")),
                                                                 ["member"], cancel=cancel)}
        for start, ge in groups.items():
            stack = [(start, [start])]
            while stack:
                cur, path = stack.pop()
                cur_e = groups.get(cur)
                if cur_e is None or len(path) > 30:
                    continue
                for m in cur_e.values("member"):
                    nm = normalize_dn(m)
                    if nm == start:
                        key = "|".join(sorted(path))
                        if key not in seen_cycle:
                            seen_cycle.add(key)
                            res.findings.append(Finding("unusual_membership", "Циклическое вложение групп", Severity.LOW,
                                                        Evidence.FACT, ge.dn, rdn_value(ge.dn),
                                                        "Цикл: " + " → ".join(rdn_value(groups[p].dn) for p in path) + f" → {rdn_value(ge.dn)}",
                                                        "Разорвите цикл: он усложняет анализ прав и не нужен."))
                    elif nm in groups and nm not in path:
                        stack.append((nm, path + [nm]))

    def check_incomplete(self, res: CheckResult, cancel):
        req = self.ctx.settings.required_user_attributes or ["department", "title", "mail"]
        flt = And(Q.IS_USER, Q.ENABLED, Q.missing_any(req), Not(Equals("isCriticalSystemObject", "TRUE")))
        for e in self.gw.search(self.ctx.base_dn, flt, ["cn", "displayName"] + req, cancel=cancel):
            missing = [a for a in req if not e.has(a)]
            res.findings.append(Finding("incomplete", "Неполные атрибуты", Severity.LOW, Evidence.FACT, e.dn,
                                        e.str("displayName") or e.str("cn"), "Не заполнены: " + ", ".join(missing),
                                        "Заполните из кадровой системы; для сервисных УЗ — исключите их OU из проверки."))

    def check_suspicious(self, res: CheckResult, cancel):
        now = utcnow()
        priv = self._privileged_members(cancel)
        attrs = Q.USER_ATTRIBUTES + ["servicePrincipalName"]
        checks = [
            (UAC.PASSWD_NOTREQD, "Флаг PASSWD_NOTREQD (пароль не требуется)", Severity.HIGH),
            (UAC.DONT_REQ_PREAUTH, "Kerberos без предварительной аутентификации (AS-REP roasting)", Severity.HIGH),
            (UAC.ENCRYPTED_TEXT_PWD_ALLOWED, "Хранение пароля с обратимым шифрованием", Severity.HIGH),
            (UAC.USE_DES_KEY_ONLY, "Только DES для Kerberos", Severity.MEDIUM),
            (UAC.TRUSTED_FOR_DELEGATION, "Неограниченное делегирование у пользователя", Severity.HIGH),
        ]
        policy = self.ctx.policy
        for e in self.gw.search(self.ctx.base_dn, Q.IS_USER, attrs, cancel=cancel):
            u = UserRecord.from_entry(e, policy, now)
            for flag, title, sev in checks:
                if u.uac & flag and u.enabled:
                    res.findings.append(Finding("suspicious", title, sev, Evidence.FACT, u.dn, u.name,
                                                f"userAccountControl={u.uac}", "Уберите флаг, если он не требуется явно."))
            if u.sam.lower() == "guest" and u.enabled:
                res.findings.append(Finding("suspicious", "Включена учётная запись Guest", Severity.HIGH, Evidence.FACT, u.dn,
                                            u.name, "", "Отключите встроенную учётную запись Гость."))
            if u.sam.lower() == "krbtgt" and u.pwd_last_set and (now - u.pwd_last_set).days > 180:
                res.findings.append(Finding("suspicious", "Пароль krbtgt не менялся более 180 дней", Severity.MEDIUM,
                                            Evidence.FACT, u.dn, u.name, f"pwdLastSet: {u.pwd_last_set:%Y-%m-%d}",
                                            "Выполните плановую двойную смену пароля krbtgt по процедуре Microsoft."))
            if e.values("servicePrincipalName") and normalize_dn(u.dn) in priv and u.enabled:
                res.findings.append(Finding("suspicious", "SPN у привилегированной учётной записи", Severity.HIGH,
                                            Evidence.REVIEW, u.dn, u.name, "; ".join(map(str, e.values("servicePrincipalName")))[:300],
                                            "Используйте gMSA и длинные пароли; уберите УЗ из админ-групп."))
            if u.enabled and u.pwd_last_set and (now - u.pwd_last_set).days > 365 and u.sam.lower() != "krbtgt":
                res.findings.append(Finding("suspicious", "Пароль не менялся более года", Severity.MEDIUM if u.pwd_never_expires else Severity.LOW,
                                            Evidence.FACT, u.dn, u.name, f"pwdLastSet: {u.pwd_last_set:%Y-%m-%d}",
                                            "Проверьте необходимость УЗ и смените пароль."))
            if u.enabled and "уволен" in (u.description or "").lower():
                res.findings.append(Finding("suspicious", "Описание «уволен», но учётная запись включена", Severity.HIGH,
                                            Evidence.REVIEW, u.dn, u.name, u.description,
                                            "Проверьте статус сотрудника и выполните процедуру увольнения."))
            if u.enabled and u.account_expired:
                res.findings.append(Finding("suspicious", "Срок действия истёк, флаг включения сохраняется", Severity.INFO,
                                            Evidence.FACT, u.dn, u.name,
                                            f"accountExpires: {u.account_expires:%Y-%m-%d}" if u.account_expires else "",
                                            "Вход невозможен; при необходимости отключите явно для наглядности."))

    def check_outdated_os(self, res: CheckResult, cancel):
        res.limitations = "operatingSystem заполняет сам компьютер при входе — значение может быть устаревшим."
        for e in self.gw.search(self.ctx.base_dn, And(Q.IS_COMPUTER, Q.ENABLED), Q.COMPUTER_ATTRIBUTES, cancel=cancel):
            c = ComputerRecord.from_entry(e)
            classify_os(c, self.ctx.settings.outdated_os)
            if c.os_support is OsSupport.OUTDATED:
                res.findings.append(Finding("outdated_os", "Устаревшая ОС", Severity.HIGH if "Server" in c.os else Severity.MEDIUM,
                                            Evidence.FACT, c.dn, c.name, f"{c.os} {c.os_version}. {c.os_note}",
                                            "Обновите ОС или изолируйте узел; при наличии ESU отметьте исключение."))

    def check_recent(self, res: CheckResult, cancel):
        days = self.ctx.settings.recent_days
        flt = And(Q.created_since(days), Or(Q.IS_USER, Q.IS_COMPUTER, Q.IS_GROUP))
        for e in self.gw.search(self.ctx.base_dn, flt, ["cn", "objectClass", "whenCreated", "displayName"], cancel=cancel):
            t = TYPE_LABELS.get(object_type_of(e), "Объект")
            wc = e.first("whenCreated")
            res.findings.append(Finding("recent", f"Создан объект: {t}", Severity.INFO, Evidence.FACT, e.dn,
                                        e.str("displayName") or e.str("cn"), f"whenCreated: {wc:%Y-%m-%d %H:%M}" if wc else "",
                                        "Сверьте с заявками на создание объектов."))

    def check_dcs(self, res: CheckResult, cancel):
        from . import network_service as N
        dcs = self.gw.info.domain_controllers or [self.gw.info.dc_host]
        timeout = float(self.ctx.settings.network_timeout_s)
        if self.gw.is_demo:
            res.limitations = "Демо-режим: сетевые проверки к вымышленным контроллерам не выполняются."
            for dc in dcs:
                res.findings.append(Finding("dc_availability", "Сетевая проверка не выполнялась (демо)", Severity.INFO,
                                            Evidence.LIMITED, "", dc, "", ""))
            return
        for dc in dcs:
            if cancel:
                cancel.raise_if_cancelled()
            probes = [N.resolve(dc, timeout), N.tcp_check(dc, 389, timeout, "LDAP"), N.tcp_check(dc, 636, timeout, "LDAPS"),
                      N.tcp_check(dc, 88, timeout, "Kerberos"), N.tls_probe(dc, 636, timeout + 2)]
            for p in probes:
                if p.ok is False:
                    sev = Severity.HIGH if "LDAP" in p.check or "DNS" in p.check else Severity.MEDIUM
                    res.findings.append(Finding("dc_availability", f"{p.check}: недоступно", sev, Evidence.FACT, "", dc,
                                                p.message, "Проверьте службы DC, брандмауэр, DNS и сертификат."))
                elif p.ok and p.details.get("days_left") is not None and p.details["days_left"] < 30:
                    res.findings.append(Finding("dc_availability", "Сертификат LDAPS скоро истекает", Severity.MEDIUM,
                                                Evidence.FACT, "", dc, p.message, "Обновите сертификат контроллера домена."))
            if all(p.ok for p in probes):
                res.findings.append(Finding("dc_availability", "Контроллер доступен", Severity.INFO, Evidence.FACT, "", dc,
                                            "DNS, LDAP 389/636, Kerberos 88 и TLS — OK", ""))

    def check_connection(self, res: CheckResult, cancel):
        info = self.gw.info
        if not info.encrypted:
            res.findings.append(Finding("connection", "Подключение не зашифровано", Severity.HIGH, Evidence.FACT, "",
                                        info.dc_host, "Данные каталога передаются открыто",
                                        "Используйте LDAPS или StartTLS."))
        else:
            res.findings.append(Finding("connection", "Соединение зашифровано", Severity.INFO, Evidence.FACT, "", info.dc_host,
                                        info.security_label, ""))
        for w in info.warnings:
            res.findings.append(Finding("connection", "Предупреждение подключения", Severity.LOW, Evidence.FACT, "",
                                        info.dc_host, w, ""))
        summary = self.ctx.permissions.rights_summary(self.ctx.privileged)
        if summary.privileged_groups:
            res.findings.append(Finding("connection", "Подключение под привилегированной учётной записью", Severity.MEDIUM,
                                        Evidence.FACT, summary.user_dn, summary.identity,
                                        "Группы: " + ", ".join(summary.privileged_groups),
                                        "Для ежедневной работы используйте учётную запись с делегированными правами "
                                        "только на нужные OU (принцип минимальных привилегий)."))
        quota = info.policy.machine_account_quota
        if quota:
            res.findings.append(Finding("connection", "ms-DS-MachineAccountQuota > 0", Severity.LOW, Evidence.FACT,
                                        info.base_dn, info.domain_dns,
                                        f"Обычные пользователи могут добавить в домен до {quota} компьютеров",
                                        "Рассмотрите установку 0 и делегирование присоединения к домену."))
        if not self.gw.read_only:
            res.findings.append(Finding("connection", "Режим изменений включён", Severity.INFO, Evidence.FACT, "",
                                        "Приложение", "Режим «только чтение» отключён", "Включайте режим изменений только на время работ."))
        lockout = info.policy
        if lockout.lockout_threshold == 0:
            res.findings.append(Finding("connection", "Блокировка учётных записей не настроена", Severity.MEDIUM, Evidence.FACT,
                                        info.base_dn, info.domain_dns, "lockoutThreshold = 0",
                                        "Настройте порог блокировки в Default Domain Policy (с учётом риска DoS)."))
        if info.policy.min_pwd_length and info.policy.min_pwd_length < 12:
            res.findings.append(Finding("connection", "Минимальная длина пароля менее 12", Severity.LOW, Evidence.FACT,
                                        info.base_dn, info.domain_dns, f"minPwdLength = {info.policy.min_pwd_length}",
                                        "Рекомендуется 12–14+ символов или парольные фразы."))

