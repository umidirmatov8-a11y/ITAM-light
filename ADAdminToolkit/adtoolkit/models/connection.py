"""Connection profile and discovered directory information."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum


class SecurityMode(str, Enum):
    LDAPS = "ldaps"          # TLS from the first byte, TCP 636
    STARTTLS = "starttls"    # TCP 389 upgraded with StartTLS before bind
    PLAIN = "plain"          # TCP 389 without TLS — allowed only for Kerberos with explicit consent

    @property
    def label(self) -> str:
        return {
            "ldaps": "LDAPS (TLS, порт 636)",
            "starttls": "StartTLS (TLS поверх порта 389)",
            "plain": "LDAP без шифрования (только Kerberos, небезопасно)",
        }[self.value]

    @property
    def default_port(self) -> int:
        return 636 if self is SecurityMode.LDAPS else 389


class AuthMethod(str, Enum):
    SIMPLE = "simple"        # UPN or DN + password (only over TLS)
    NTLM = "ntlm"            # DOMAIN\\user + password (only over TLS)
    KERBEROS = "kerberos"    # current Windows logon session (SASL GSSAPI, winkerberos)

    @property
    def label(self) -> str:
        return {
            "simple": "Простая (UPN/DN + пароль)",
            "ntlm": "NTLM (DOMAIN\\user + пароль)",
            "kerberos": "Kerberos — текущие учётные данные Windows",
        }[self.value]

    @property
    def needs_password(self) -> bool:
        return self is not AuthMethod.KERBEROS


@dataclass
class ConnectionProfile:
    name: str = "Новое подключение"
    server: str = ""
    port: int = 636
    security: SecurityMode = SecurityMode.LDAPS
    auth: AuthMethod = AuthMethod.SIMPLE
    base_dn: str = ""                       # empty -> defaultNamingContext from RootDSE
    username: str = ""
    ca_file: str = ""                       # optional PEM bundle; empty -> Windows/OS trusted roots
    tls_server_name: str = ""               # optional expected certificate name if server is an IP address
    connect_timeout: int = 10
    operation_timeout: int = 60
    page_size: int = 500
    reconnect_attempts: int = 3
    allow_unencrypted_kerberos: bool = False
    use_credential_manager: bool = False    # explicit consent to keep the password in Windows Credential Manager
    read_only: bool = True                  # safe default — writes must be enabled explicitly

    def to_dict(self) -> dict:
        d = asdict(self)
        d["security"] = self.security.value
        d["auth"] = self.auth.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectionProfile":
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in (data or {}).items() if k in known}
        if "security" in clean:
            clean["security"] = SecurityMode(clean["security"])
        if "auth" in clean:
            clean["auth"] = AuthMethod(clean["auth"])
        for key in ("port", "connect_timeout", "operation_timeout", "page_size", "reconnect_attempts"):
            if key in clean:
                clean[key] = int(clean[key])
        return cls(**clean)

    @property
    def encrypted(self) -> bool:
        return self.security in (SecurityMode.LDAPS, SecurityMode.STARTTLS)

    def credential_target(self) -> str:
        return f"ADAdminToolkit:{self.server.lower()}:{self.username.lower()}"


@dataclass
class DomainPolicy:
    min_pwd_length: int = 0
    pwd_history_length: int = 0
    complexity: bool = False
    max_pwd_age_days: float | None = None
    min_pwd_age_days: float | None = None
    lockout_threshold: int = 0
    lockout_duration_minutes: float | None = None   # None => until an administrator unlocks
    logon_sync_interval_days: int = 14
    machine_account_quota: int | None = None


@dataclass
class DirectoryInfo:
    domain_dns: str = ""
    netbios_name: str = ""
    base_dn: str = ""
    default_naming_context: str = ""
    configuration_nc: str = ""
    schema_nc: str = ""
    root_domain_nc: str = ""
    dc_host: str = ""
    dc_server_name: str = ""
    domain_sid: str = ""
    domain_functionality: int | None = None
    forest_functionality: int | None = None
    dc_functionality: int | None = None
    bound_identity: str = ""
    bound_user_dn: str = ""
    connected_at: datetime | None = None
    last_success_at: datetime | None = None
    security_label: str = ""
    encrypted: bool = False
    certificate_subject: str = ""
    certificate_issuer: str = ""
    certificate_not_after: str = ""
    supported_controls: list[str] = field(default_factory=list)
    supported_sasl: list[str] = field(default_factory=list)
    policy: DomainPolicy = field(default_factory=DomainPolicy)
    domain_controllers: list[str] = field(default_factory=list)
    is_demo: bool = False
    warnings: list[str] = field(default_factory=list)

    FUNCTIONAL_LEVELS = {0: "2000", 1: "2003 interim", 2: "2003", 3: "2008", 4: "2008 R2", 5: "2012", 6: "2012 R2",
                         7: "2016", 10: "2025"}

    def level_text(self, value: int | None) -> str:
        if value is None:
            return "неизвестно"
        return f"Windows Server {self.FUNCTIONAL_LEVELS.get(value, str(value))}"
