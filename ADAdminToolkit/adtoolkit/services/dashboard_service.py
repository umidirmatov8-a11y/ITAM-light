"""Domain statistics for the dashboard (one paged pass per object class; exact values or explicit error/notes)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import OperationCancelledError, ToolkitError
from ..ldap.adtypes import UAC, utcnow
from ..models.records import UserRecord
from . import ad_queries as Q
from .context import ServiceContext


@dataclass
class Metric:
    key: str
    title: str
    value: int | None = None
    note: str = ""
    error: str = ""
    exact: bool = True
    severity: str = "normal"      # normal | warning | danger


@dataclass
class DomainStats:
    metrics: dict[str, Metric] = field(default_factory=dict)
    collected_at: datetime | None = None
    duration_s: float = 0.0
    recent_users: list[UserRecord] = field(default_factory=list)
    domain: str = ""
    dc: str = ""
    errors: list[str] = field(default_factory=list)

    def add(self, m: Metric) -> Metric:
        self.metrics[m.key] = m
        return m


class DashboardService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.gw = ctx.gateway

    def collect(self, cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> DomainStats:
        start = utcnow()
        stats = DomainStats(domain=self.gw.info.domain_dns, dc=self.gw.info.dc_host)
        base = self.ctx.base_dn
        s = self.ctx.settings
        policy = self.ctx.policy
        user_keys = [("users_total", "Пользователи"), ("users_enabled", "Активные"), ("users_disabled", "Отключённые"),
                     ("users_locked", "Заблокированные"), ("users_pwd_expired", "Пароль истёк"),
                     ("users_pne", "Password Never Expires"), ("users_recent", f"Созданы за {s.recent_days} дн."),
                     ("users_stale", f"Не входили > {s.stale_user_days} дн.")]
        for key, title in user_keys:
            stats.add(Metric(key, title))
        try:
            progress(5, "Сбор статистики пользователей…")
            total = enabled = disabled = locked = pwd_expired = pne = stale = 0
            locked_exact = True
            recent_cutoff = start - timedelta(days=s.recent_days)
            stale_cutoff = start - timedelta(days=s.stale_user_days)
            recent: list[UserRecord] = []
            attrs = ["userAccountControl", "msDS-User-Account-Control-Computed", "msDS-UserPasswordExpiryTimeComputed",
                     "lockoutTime", "pwdLastSet", "lastLogonTimestamp", "whenCreated", "displayName", "sAMAccountName",
                     "department", "title"]
            for e in self.gw.search(base, Q.IS_USER, attrs, cancel=cancel):
                total += 1
                r = UserRecord.from_entry(e, policy, start)
                if r.enabled:
                    enabled += 1
                else:
                    disabled += 1
                if r.locked:
                    locked += 1
                    locked_exact = locked_exact and r.locked_exact
                if r.enabled and r.pwd_expired:
                    pwd_expired += 1
                if r.pwd_never_expires:
                    pne += 1
                if r.when_created and r.when_created >= recent_cutoff:
                    recent.append(r)
                if r.enabled and r.when_created and r.when_created < stale_cutoff and (
                        r.last_logon_timestamp is None or r.last_logon_timestamp < stale_cutoff):
                    stale += 1
                if total % 500 == 0:
                    progress(10, f"Пользователи: обработано {total}…")
            values = {"users_total": total, "users_enabled": enabled, "users_disabled": disabled, "users_locked": locked,
                      "users_pwd_expired": pwd_expired, "users_pne": pne, "users_recent": len(recent), "users_stale": stale}
            for k, v in values.items():
                stats.metrics[k].value = v
            stats.metrics["users_locked"].exact = locked_exact
            if not locked_exact:
                stats.metrics["users_locked"].note = "оценка по lockoutTime/lockoutDuration"
            stats.metrics["users_locked"].severity = "danger" if locked else "normal"
            stats.metrics["users_pwd_expired"].note = "среди включённых"
            stats.metrics["users_pne"].severity = "warning" if pne else "normal"
            stats.metrics["users_stale"].note = "по lastLogonTimestamp (точность ±14–19 дн.)"
            stats.metrics["users_stale"].exact = False
            stats.recent_users = sorted(recent, key=lambda r: r.when_created, reverse=True)[:50]
        except OperationCancelledError:
            raise
        except ToolkitError as exc:
            for key, _ in user_keys:
                stats.metrics[key].error = exc.message
            stats.errors.append(f"Пользователи: {exc.message}")

        comp_keys = [("computers_total", "Компьютеры"), ("computers_disabled", "Отключённые компьютеры"),
                     ("computers_stale", f"Компьютеры без входа > {s.stale_computer_days} дн.")]
        for key, title in comp_keys:
            stats.add(Metric(key, title))
        try:
            progress(55, "Сбор статистики компьютеров…")
            total = disabled = stale = 0
            cutoff = start - timedelta(days=s.stale_computer_days)
            from ..ldap.adtypes import filetime_to_datetime
            for e in self.gw.search(base, Q.IS_COMPUTER, ["userAccountControl", "lastLogonTimestamp", "whenCreated"], cancel=cancel):
                total += 1
                uac = e.int("userAccountControl", 0) or 0
                if uac & UAC.ACCOUNTDISABLE:
                    disabled += 1
                else:
                    llt = filetime_to_datetime(e.first("lastLogonTimestamp"))
                    created = e.first("whenCreated")
                    if (llt is None or llt < cutoff) and isinstance(created, datetime) and created < cutoff:
                        stale += 1
            stats.metrics["computers_total"].value = total
            stats.metrics["computers_disabled"].value = disabled
            stats.metrics["computers_stale"].value = stale
            stats.metrics["computers_stale"].exact = False
            stats.metrics["computers_stale"].note = "по lastLogonTimestamp; доступность в сети не проверялась"
        except OperationCancelledError:
            raise
        except ToolkitError as exc:
            for key, _ in comp_keys:
                stats.metrics[key].error = exc.message
            stats.errors.append(f"Компьютеры: {exc.message}")

        stats.add(Metric("groups_security", "Группы безопасности"))
        stats.add(Metric("groups_total", "Все группы"))
        try:
            progress(85, "Сбор статистики групп…")
            total = security = 0
            from ..ldap.adtypes import GROUP_TYPE_SECURITY, group_type_unsigned
            for e in self.gw.search(base, Q.IS_GROUP, ["groupType"], cancel=cancel):
                total += 1
                if group_type_unsigned(e.int("groupType", 0)) & GROUP_TYPE_SECURITY:
                    security += 1
            stats.metrics["groups_total"].value = total
            stats.metrics["groups_security"].value = security
        except OperationCancelledError:
            raise
        except ToolkitError as exc:
            stats.metrics["groups_total"].error = stats.metrics["groups_security"].error = exc.message
            stats.errors.append(f"Группы: {exc.message}")
        stats.collected_at = utcnow()
        stats.duration_s = (stats.collected_at - start).total_seconds()
        progress(100, "Статистика обновлена")
        return stats
