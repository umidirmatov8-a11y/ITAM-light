"""Active Directory access through ldap3.

Security rules enforced here:

* TLS certificates are always validated (``ssl.CERT_REQUIRED`` + host name check). There is no option to turn
  validation off — a custom CA bundle may be supplied instead.
* Passwords are only sent over LDAPS or StartTLS. Over plain LDAP (TCP 389 without TLS) only Kerberos (SASL GSSAPI,
  no password on the wire) is possible, and only with an explicit opt-in; writes of secrets are refused.
* ldap3 2.9 does not implement SASL integrity/confidentiality layers, therefore "SASL signing+sealing" on 389 is
  not offered; TLS (LDAPS/StartTLS) is used for confidentiality instead.
* Reads are retried transparently after a reconnect; writes are never retried automatically because their outcome
  is unknown after a network failure.
"""
from __future__ import annotations

import logging
import ssl
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Iterable, Iterator

from ..core import errors as E
from ..core.cancel import CancelToken
from ..models.connection import AuthMethod, ConnectionProfile, DirectoryInfo, DomainPolicy, SecurityMode
from . import error_mapping as EM
from .adtypes import decode_attributes, interval_to_timedelta, sid_to_str
from .dn import dn_to_dns_domain
from .filters import FilterNode
from .gateway import Changes, DirectoryGateway, Entry, ModOp, Scope, SearchStats

log = logging.getLogger(__name__)

PAGED_RESULTS_OID = "1.2.840.113556.1.4.319"

ROOT_DSE_ATTRIBUTES = [
    "defaultNamingContext", "configurationNamingContext", "schemaNamingContext", "rootDomainNamingContext",
    "dnsHostName", "serverName", "domainFunctionality", "forestFunctionality", "domainControllerFunctionality",
    "supportedControl", "supportedSASLMechanisms", "currentTime", "isSynchronized", "isGlobalCatalogReady",
    "ldapServiceName", "supportedLDAPVersion",
]

DOMAIN_ATTRIBUTES = [
    "objectSid", "name", "minPwdLength", "pwdHistoryLength", "pwdProperties", "maxPwdAge", "minPwdAge",
    "lockoutThreshold", "lockoutDuration", "lockOutObservationWindow", "msDS-LogonTimeSyncInterval",
    "ms-DS-MachineAccountQuota",
]


def _import_ldap3():
    import ldap3  # imported lazily so that the UI can start and show a clear error if the package is missing
    return ldap3


class Ldap3Gateway(DirectoryGateway):
    def __init__(self, profile: ConnectionProfile, password: str | None = None, *,
                 connection_factory: Callable[["Ldap3Gateway"], object] | None = None):
        super().__init__()
        self.profile = profile
        self._password = password
        self._conn = None
        self._lock = threading.RLock()
        self._connection_factory = connection_factory
        self.read_only = profile.read_only
        self.default_page_size = max(1, min(int(profile.page_size or 500), 1000))
        self._connected = False

    # ------------------------------------------------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------------------------------------------------
    def validate_profile(self) -> None:
        p = self.profile
        if not p.server.strip():
            raise E.ConfigurationError("Не указан сервер LDAP / контроллер домена")
        if not (1 <= int(p.port) <= 65535):
            raise E.ConfigurationError("Некорректный порт")
        if p.auth.needs_password:
            if not p.username.strip():
                raise E.ConfigurationError("Не указано имя пользователя")
            if not self._password:
                raise E.ConfigurationError("Не указан пароль")
            if p.security is SecurityMode.PLAIN:
                raise E.InsecureConnectionError(
                    "Пароль не будет отправлен по незашифрованному соединению",
                    hint="Выберите LDAPS (636) или StartTLS, либо Kerberos с текущими учётными данными Windows.")
        if p.auth is AuthMethod.NTLM and "\\" not in p.username:
            raise E.ConfigurationError("Для NTLM укажите имя в формате ДОМЕН\\пользователь")
        if p.security is SecurityMode.PLAIN and not p.allow_unencrypted_kerberos:
            raise E.InsecureConnectionError(
                "Незашифрованное LDAP-соединение не разрешено в профиле",
                hint="Используйте LDAPS/StartTLS или явно разрешите Kerberos без TLS (данные каталога будут передаваться открыто).")

    def _build_connection(self):
        if self._connection_factory:
            return self._connection_factory(self)
        ldap3 = _import_ldap3()
        p = self.profile
        tls = None
        if p.security in (SecurityMode.LDAPS, SecurityMode.STARTTLS):
            tls = ldap3.Tls(
                validate=ssl.CERT_REQUIRED,
                version=ssl.PROTOCOL_TLS_CLIENT,
                ca_certs_file=p.ca_file or None,
                valid_names=[p.tls_server_name] if p.tls_server_name else None,
            )
        server = ldap3.Server(
            p.server.strip(), port=int(p.port), use_ssl=p.security is SecurityMode.LDAPS, tls=tls,
            get_info=ldap3.NONE, connect_timeout=int(p.connect_timeout),
        )
        kwargs = dict(
            auto_bind=ldap3.AUTO_BIND_NONE, raise_exceptions=False, auto_range=True, read_only=False,
            receive_timeout=int(p.operation_timeout), return_empty_attributes=False, check_names=True,
            client_strategy=ldap3.SYNC, auto_referrals=False,
        )
        if p.auth is AuthMethod.SIMPLE:
            kwargs.update(user=p.username.strip(), password=self._password, authentication=ldap3.SIMPLE)
        elif p.auth is AuthMethod.NTLM:
            kwargs.update(user=p.username.strip(), password=self._password, authentication=ldap3.NTLM)
        else:
            # Kerberos via the current Windows logon session (winkerberos). Target SPN is ldap/<server>.
            kwargs.update(authentication=ldap3.SASL, sasl_mechanism=ldap3.KERBEROS)
        return ldap3.Connection(server, **kwargs)

    def connect(self) -> DirectoryInfo:
        self.validate_profile()
        with self._lock:
            self._close_quietly()
            try:
                conn = self._build_connection()
                if not conn.open() and getattr(conn, "closed", False):
                    raise E.ConnectionFailedError("Не удалось открыть соединение")
                if self.profile.security is SecurityMode.STARTTLS:
                    if not conn.start_tls():
                        raise E.CertificateError("Не удалось установить StartTLS", details=str(conn.result))
                if not conn.bind():
                    raise EM.map_bind_result(conn.result)
            except E.ToolkitError:
                self._close_quietly()
                raise
            except Exception as exc:  # ldap3 / socket / ssl exceptions
                self._close_quietly()
                raise EM.map_exception(exc, "connect") from None
            self._conn = conn
            self._connected = True
        self.info = self._discover()
        self._notify("connected", f"Подключено к {self.info.dc_host or self.profile.server}")
        return self.info

    def _close_quietly(self):
        if self._conn is not None:
            try:
                self._conn.unbind()
            except Exception:
                pass
        self._conn = None
        self._connected = False

    def close(self) -> None:
        with self._lock:
            self._close_quietly()
        self._password = None
        self._notify("disconnected", "Отключено")

    @property
    def connected(self) -> bool:
        conn = self._conn
        return bool(conn is not None and self._connected and getattr(conn, "bound", False) and not getattr(conn, "closed", False))

    def reconnect(self) -> None:
        attempts = max(1, int(self.profile.reconnect_attempts))
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            self._notify("reconnecting", f"Повторное подключение ({attempt}/{attempts})…")
            try:
                with self._lock:
                    self._close_quietly()
                    conn = self._build_connection()
                    conn.open()
                    if self.profile.security is SecurityMode.STARTTLS and not conn.start_tls():
                        raise E.CertificateError("Не удалось установить StartTLS")
                    if not conn.bind():
                        raise EM.map_bind_result(conn.result)
                    self._conn = conn
                    self._connected = True
                self.info.last_success_at = datetime.now(timezone.utc)
                self._notify("connected", "Соединение восстановлено")
                return
            except (E.AuthenticationError, E.CertificateError, E.InsecureConnectionError) as exc:
                self._notify("disconnected", exc.message)
                raise
            except Exception as exc:
                last = exc
                time.sleep(min(2 ** attempt, 10))
        self._notify("disconnected", "Не удалось восстановить соединение")
        raise EM.map_exception(last, "connect") if last else E.ConnectionFailedError()

    def clone_for_host(self, host: str) -> "Ldap3Gateway":
        profile = ConnectionProfile.from_dict(self.profile.to_dict())
        profile.server = host
        profile.tls_server_name = ""
        profile.read_only = True
        profile.reconnect_attempts = 1
        clone = Ldap3Gateway(profile, self._password, connection_factory=self._connection_factory)
        clone.validate_profile()
        with clone._lock:
            try:
                conn = clone._build_connection()
                conn.open()
                if profile.security is SecurityMode.STARTTLS and not conn.start_tls():
                    raise E.CertificateError("Не удалось установить StartTLS")
                if not conn.bind():
                    raise EM.map_bind_result(conn.result)
            except E.ToolkitError:
                raise
            except Exception as exc:
                raise EM.map_exception(exc, "connect") from None
            clone._conn = conn
            clone._connected = True
        clone.info = DirectoryInfo(base_dn=self.info.base_dn, dc_host=host, encrypted=self.info.encrypted)
        return clone

    # ------------------------------------------------------------------------------------------------------------
    # Low level call wrapper
    # ------------------------------------------------------------------------------------------------------------
    def _ensure_connected(self):
        if self._conn is None:
            raise E.NotConnectedError()
        if getattr(self._conn, "closed", False) or not getattr(self._conn, "bound", True):
            self.reconnect()

    def _call(self, fn: Callable[[object], object], *, idempotent: bool, operation: str):
        """Run ``fn(conn)`` under the connection lock; returns (status, result, response)."""
        with self._lock:
            self._ensure_connected()
            try:
                status = fn(self._conn)
                result = dict(self._conn.result or {})
                response = list(self._conn.response or [])
            except Exception as exc:
                mapped = EM.map_exception(exc, operation)
                if not isinstance(mapped, E.ConnectionFailedError):
                    raise mapped from None
                self._connected = False
                if not idempotent:
                    self._notify("disconnected", "Связь с контроллером потеряна")
                    if operation == "search":
                        raise E.ConnectionLostError(
                            "Связь потеряна во время постраничного поиска — результат неполный",
                            hint="Повторите операцию после восстановления соединения.", details=mapped.details) from None
                    raise E.ConnectionLostError(
                        "Связь с контроллером потеряна во время операции изменения — результат неизвестен",
                        hint="Переподключитесь и обновите объект, чтобы проверить, было ли изменение применено.",
                        details=mapped.details) from None
                self.reconnect()
                status = fn(self._conn)
                result = dict(self._conn.result or {})
                response = list(self._conn.response or [])
        if result.get("result") in EM.RETRYABLE_READ_CODES and idempotent:
            time.sleep(1)
            with self._lock:
                status = fn(self._conn)
                result = dict(self._conn.result or {})
                response = list(self._conn.response or [])
        self.info.last_success_at = datetime.now(timezone.utc) if result.get("result") in (0, 4) else self.info.last_success_at
        return status, result, response

    # ------------------------------------------------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------------------------------------------------
    def search(self, base: str, flt: FilterNode | str, attributes: Iterable[str] | None = None,
               scope: Scope = Scope.SUBTREE, *, page_size: int | None = None, size_limit: int = 0,
               cancel: CancelToken | None = None, stats: SearchStats | None = None,
               sd_flags: int | None = None) -> Iterator[Entry]:
        ldap3 = _import_ldap3()
        filter_text = self.filter_text(flt)
        attrs = list(attributes) if attributes else ["*"]
        scope_value = getattr(ldap3, {Scope.BASE: "BASE", Scope.ONELEVEL: "LEVEL", Scope.SUBTREE: "SUBTREE"}[scope])
        if page_size is None:
            page_size = self.default_page_size
        if scope is Scope.BASE:
            page_size = 0
        controls = None
        if sd_flags is not None:
            from ldap3.protocol.microsoft import security_descriptor_control
            controls = security_descriptor_control(sdflags=sd_flags)
        stats = stats if stats is not None else SearchStats()
        cookie = None
        while True:
            if cancel:
                cancel.raise_if_cancelled()
            kwargs = dict(search_base=base, search_filter=filter_text, search_scope=scope_value, attributes=attrs,
                          size_limit=size_limit, time_limit=int(self.profile.operation_timeout), controls=controls)
            if page_size:
                kwargs.update(paged_size=page_size, paged_cookie=cookie)
            if cookie is not None:
                # cookies are bound to the connection; never transparently restart a paged search on a new one
                _, result, response = self._call(lambda c: c.search(**kwargs), idempotent=False, operation="search")
            else:
                _, result, response = self._call(lambda c: c.search(**kwargs), idempotent=True, operation="search")
            code = result.get("result")
            if code not in (EM.SUCCESS, EM.SIZE_LIMIT_EXCEEDED):
                if code == EM.NO_SUCH_OBJECT and scope is Scope.BASE:
                    raise EM.map_result(result, "search", base)
                raise EM.map_result(result, "search", base)
            stats.pages += 1
            for item in response:
                if item.get("type") == "searchResRef":
                    stats.referrals += 1
                    continue
                if item.get("type") != "searchResEntry":
                    continue
                entry = Entry(item.get("dn", ""), decode_attributes(item.get("raw_attributes") or {}))
                stats.entries += 1
                yield entry
            if code == EM.SIZE_LIMIT_EXCEEDED:
                stats.truncated = True
                return
            if not page_size:
                return
            cookie = (((result.get("controls") or {}).get(PAGED_RESULTS_OID) or {}).get("value") or {}).get("cookie")
            if not cookie:
                return

    def root_dse(self) -> Entry:
        items = list(self.search("", "(objectClass=*)", ROOT_DSE_ATTRIBUTES, Scope.BASE))
        if not items:
            raise E.ConnectionFailedError("Не удалось прочитать RootDSE")
        return items[0]

    def who_am_i(self) -> str:
        def op(c):
            return c.extend.standard.who_am_i()
        status, _, _ = self._call(op, idempotent=True, operation="whoami")
        if isinstance(status, bytes):
            status = status.decode("utf-8", "replace")
        return str(status or "")

    def ping(self) -> bool:
        try:
            self.root_dse()
            return True
        except E.ToolkitError:
            return False

    def _discover(self) -> DirectoryInfo:
        info = DirectoryInfo()
        root = self.root_dse()
        info.default_naming_context = root.str("defaultNamingContext")
        info.base_dn = self.profile.base_dn.strip() or info.default_naming_context
        info.configuration_nc = root.str("configurationNamingContext")
        info.schema_nc = root.str("schemaNamingContext")
        info.root_domain_nc = root.str("rootDomainNamingContext")
        info.dc_host = root.str("dnsHostName") or self.profile.server
        info.dc_server_name = root.str("serverName")
        info.domain_functionality = root.int("domainFunctionality")
        info.forest_functionality = root.int("forestFunctionality")
        info.dc_functionality = root.int("domainControllerFunctionality")
        info.supported_controls = [str(v) for v in root.values("supportedControl")]
        info.supported_sasl = [str(v) for v in root.values("supportedSASLMechanisms")]
        info.domain_dns = dn_to_dns_domain(info.default_naming_context)
        info.encrypted = self.profile.security in (SecurityMode.LDAPS, SecurityMode.STARTTLS)
        info.security_label = self.profile.security.label + " · " + self.profile.auth.label
        info.connected_at = info.last_success_at = datetime.now(timezone.utc)
        if not info.encrypted:
            info.warnings.append("Соединение не зашифровано: данные каталога передаются в открытом виде. "
                                 "Операции с паролями заблокированы.")
        self._read_certificate(info)
        try:
            info.bound_identity = self.who_am_i()
        except E.ToolkitError as exc:
            info.warnings.append(f"Не удалось выполнить WhoAmI: {exc.message}")
        if PAGED_RESULTS_OID not in info.supported_controls and info.supported_controls:
            info.warnings.append("Сервер не объявил поддержку постраничной выдачи (Paged Results)")
        self.info = info
        self._discover_domain(info)
        return info

    def _read_certificate(self, info: DirectoryInfo):
        sock = getattr(self._conn, "socket", None)
        try:
            cert = sock.getpeercert() if sock is not None and hasattr(sock, "getpeercert") else None
        except Exception:
            cert = None
        if not cert:
            return
        def name(parts):
            return ", ".join("=".join(x) for rdn in parts for x in rdn)
        info.certificate_subject = name(cert.get("subject", ()))
        info.certificate_issuer = name(cert.get("issuer", ()))
        info.certificate_not_after = cert.get("notAfter", "")

    def _discover_domain(self, info: DirectoryInfo) -> None:
        nc = info.default_naming_context
        if not nc:
            info.warnings.append("RootDSE не вернул defaultNamingContext")
            return
        try:
            dom = self.get(nc, DOMAIN_ATTRIBUTES)
        except E.ToolkitError as exc:
            info.warnings.append(f"Не удалось прочитать объект домена: {exc.message}")
            dom = None
        if dom:
            info.domain_sid = sid_to_str(dom.first("objectSid")) if dom.first("objectSid") else ""
            info.policy = policy_from_entry(dom)
        if info.configuration_nc:
            try:
                from .filters import And, Equals
                refs = self.search_list(f"CN=Partitions,{info.configuration_nc}",
                                        And(Equals("objectClass", "crossRef"), Equals("nCName", nc)),
                                        ["nETBIOSName"], Scope.ONELEVEL)
                if refs:
                    info.netbios_name = refs[0].str("nETBIOSName")
            except E.ToolkitError as exc:
                info.warnings.append(f"NetBIOS-имя домена не определено: {exc.message}")
        try:
            from .filters import And, Equals, bit_and
            dcs = self.search_list(nc, And(Equals("objectCategory", "computer"), bit_and("userAccountControl", 0x2000)),
                                   ["dNSHostName"], Scope.SUBTREE)
            info.domain_controllers = sorted({d.str("dNSHostName") for d in dcs if d.str("dNSHostName")})
        except E.ToolkitError as exc:
            info.warnings.append(f"Список контроллеров домена не получен: {exc.message}")

    # ------------------------------------------------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------------------------------------------------
    def _ldap_op(self, op: ModOp):
        ldap3 = _import_ldap3()
        return {ModOp.ADD: ldap3.MODIFY_ADD, ModOp.DELETE: ldap3.MODIFY_DELETE, ModOp.REPLACE: ldap3.MODIFY_REPLACE}[op]

    def modify(self, dn: str, changes: Changes) -> None:
        self._guard_write()
        if any(a.lower() == "unicodepwd" for a in changes):
            raise E.ValidationError("Изменение пароля выполняется только через функцию сброса пароля")
        ldap_changes = {attr: [(self._ldap_op(op), list(values)) for op, values in ops] for attr, ops in changes.items()}
        _, result, _ = self._call(lambda c: c.modify(dn, ldap_changes), idempotent=False, operation="modify")
        if result.get("result") != EM.SUCCESS:
            raise EM.map_result(result, "изменение объекта", dn)

    def add(self, dn: str, object_classes: list[str], attributes: dict) -> None:
        self._guard_write()
        attrs = {k: v for k, v in attributes.items() if v not in (None, "", [])}
        if any(a.lower() == "unicodepwd" for a in attrs):
            raise E.ValidationError("Пароль задаётся отдельной операцией после создания объекта")
        _, result, _ = self._call(lambda c: c.add(dn, object_classes, attrs), idempotent=False, operation="add")
        if result.get("result") != EM.SUCCESS:
            raise EM.map_result(result, "создание объекта", dn)

    def delete(self, dn: str) -> None:
        self._guard_write()
        _, result, _ = self._call(lambda c: c.delete(dn), idempotent=False, operation="delete")
        if result.get("result") != EM.SUCCESS:
            raise EM.map_result(result, "удаление объекта", dn)

    def move(self, dn: str, new_parent: str, new_rdn: str | None = None) -> str:
        self._guard_write()
        from .dn import first_rdn
        rdn = new_rdn or first_rdn(dn)
        _, result, _ = self._call(lambda c: c.modify_dn(dn, rdn, new_superior=new_parent), idempotent=False,
                                  operation="move")
        if result.get("result") != EM.SUCCESS:
            raise EM.map_result(result, "перемещение объекта", dn)
        return f"{rdn},{new_parent}"

    def set_password(self, dn: str, new_password: str) -> None:
        self._guard_write()
        self._require_encryption("Установка пароля")
        if not new_password:
            raise E.ValidationError("Пустой пароль")

        def op(c):
            return c.extend.microsoft.modify_password(dn, new_password)
        try:
            _, result, _ = self._call(op, idempotent=False, operation="set_password")
        except E.ToolkitError as exc:
            raise type(exc)(exc.message, details=exc.details, hint=exc.hint, code=exc.code) from None
        if result.get("result") != EM.SUCCESS:
            raise EM.map_result(result, "установка пароля", dn)


def policy_from_entry(dom: Entry) -> DomainPolicy:
    policy = DomainPolicy()
    policy.min_pwd_length = dom.int("minPwdLength", 0) or 0
    policy.pwd_history_length = dom.int("pwdHistoryLength", 0) or 0
    policy.complexity = bool((dom.int("pwdProperties", 0) or 0) & 0x1)
    max_age = interval_to_timedelta(dom.first("maxPwdAge"))
    policy.max_pwd_age_days = max_age.total_seconds() / 86400 if max_age else None
    min_age = interval_to_timedelta(dom.first("minPwdAge"))
    policy.min_pwd_age_days = min_age.total_seconds() / 86400 if min_age else None
    policy.lockout_threshold = dom.int("lockoutThreshold", 0) or 0
    duration = interval_to_timedelta(dom.first("lockoutDuration"))
    policy.lockout_duration_minutes = duration.total_seconds() / 60 if duration else None
    policy.logon_sync_interval_days = dom.int("msDS-LogonTimeSyncInterval", 14) or 14
    policy.machine_account_quota = dom.int("ms-DS-MachineAccountQuota")
    return policy
