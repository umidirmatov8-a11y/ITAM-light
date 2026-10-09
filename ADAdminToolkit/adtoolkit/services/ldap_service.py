"""Connection management: connect / test / demo mode, discovery and rights check of the bound account."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.app_config import AppSettings
from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import ToolkitError
from ..ldap.gateway import DirectoryGateway
from ..ldap.ldap3_gateway import Ldap3Gateway
from ..models.connection import ConnectionProfile, SecurityMode
from ..security.audit_log import OperationJournal
from ..security.permissions import RightsSummary
from . import network_service as N
from .context import ServiceContext


@dataclass
class TestStep:
    name: str
    ok: bool | None
    message: str


@dataclass
class ConnectionTestReport:
    steps: list[TestStep] = field(default_factory=list)
    rights: RightsSummary | None = None

    @property
    def success(self) -> bool:
        return all(s.ok is not False for s in self.steps) and bool(self.steps)


class ConnectionService:
    def __init__(self, journal: OperationJournal, settings: AppSettings):
        self.journal = journal
        self.settings = settings

    def connect(self, profile: ConnectionProfile, password: str | None, gateway_factory=None) -> ServiceContext:
        gw: DirectoryGateway = (gateway_factory or Ldap3Gateway)(profile, password)
        try:
            gw.connect()
        except ToolkitError as exc:
            self.journal.record("connect", profile.server, "failed", error=exc.message,
                                details={"profile": profile.name, "security": profile.security.value, "auth": profile.auth.value})
            raise
        ctx = ServiceContext(gw, self.settings, self.journal)
        self.journal.record("connect", gw.info.dc_host, "success",
                            details={"profile": profile.name, "security": profile.security.value, "auth": profile.auth.value,
                                     "read_only": profile.read_only})
        return ctx

    def connect_demo(self, read_only: bool = True) -> ServiceContext:
        from ..ldap.demo_data import create_demo_gateway
        gw = create_demo_gateway(read_only=read_only)
        ctx = ServiceContext(gw, self.settings, self.journal)
        self.journal.record("connect.demo", gw.info.dc_host, "success", details={"read_only": read_only})
        return ctx

    def test(self, profile: ConnectionProfile, password: str | None, cancel: CancelToken | None = None,
             progress: Progress = NULL_PROGRESS, gateway_factory=None) -> ConnectionTestReport:
        """Step-by-step check: DNS, TCP, TLS certificate, bind, RootDSE, WhoAmI, rights. Nothing is simulated."""
        report = ConnectionTestReport()
        host = profile.server.strip()
        timeout = float(profile.connect_timeout)
        try:
            N.validate_host(host)
        except ToolkitError as exc:
            report.steps.append(TestStep("Адрес сервера", False, exc.message))
            return report
        progress(5, "DNS…")
        r = N.resolve(host, timeout)
        report.steps.append(TestStep("Разрешение имени (DNS)", r.ok, r.message))
        if cancel:
            cancel.raise_if_cancelled()
        progress(20, f"TCP {profile.port}…")
        t = N.tcp_check(host, int(profile.port), timeout)
        report.steps.append(TestStep(f"Доступность TCP {profile.port}", t.ok, t.message))
        if not t.ok:
            return report
        if profile.security in (SecurityMode.LDAPS, SecurityMode.STARTTLS):
            progress(40, "Проверка сертификата…")
            tls = N.tls_probe(host, int(profile.port), timeout, profile.ca_file or None, profile.tls_server_name or None,
                              starttls=profile.security is SecurityMode.STARTTLS)
            report.steps.append(TestStep("TLS и сертификат контроллера", tls.ok, tls.message))
            if not tls.ok:
                return report
        else:
            report.steps.append(TestStep("Шифрование", False if not profile.allow_unencrypted_kerberos else None,
                                         "Соединение НЕ зашифровано: пароль отправлен не будет; разрешён только Kerberos"))
        if cancel:
            cancel.raise_if_cancelled()
        progress(60, "Аутентификация…")
        gw = (gateway_factory or Ldap3Gateway)(profile, password)
        try:
            info = gw.connect()
        except ToolkitError as exc:
            report.steps.append(TestStep("Аутентификация (bind)", False, exc.full_text()))
            return report
        try:
            report.steps.append(TestStep("Аутентификация (bind)", True, f"Успешно: {info.bound_identity or profile.username}"))
            report.steps.append(TestStep("RootDSE / каталог", True,
                                         f"Домен {info.domain_dns}, DC {info.dc_host}, Base DN {info.base_dn}"))
            for w in info.warnings:
                report.steps.append(TestStep("Предупреждение", None, w))
            progress(80, "Проверка прав…")
            ctx = ServiceContext(gw, self.settings, self.journal)
            rights = ctx.permissions.rights_summary(ctx.privileged)
            report.rights = rights
            msg = "Чтение каталога: " + ("да" if rights.can_read_directory else "нет")
            if rights.create_user_in_default is not None:
                msg += f"; создание пользователей в CN=Users: {'да' if rights.create_user_in_default else 'нет'}"
            if rights.privileged_groups:
                msg += "; привилегированные группы: " + ", ".join(rights.privileged_groups)
            report.steps.append(TestStep("Права учётной записи", rights.can_read_directory, msg))
        finally:
            gw.close()
        progress(100, "Проверка завершена")
        return report
