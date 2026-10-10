"""Typed views over directory entries used by services, reports and UI tables."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ..ldap.adtypes import (FILETIME_NEVER, UAC, filetime_to_datetime, group_category, group_scope,
                            group_type_unsigned, GROUP_TYPE_SECURITY, sid_rid, sid_to_str, utcnow)
from ..ldap.dn import container_path, rdn_value
from ..ldap.gateway import Entry
from .connection import DomainPolicy


class AccountState(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"
    EXPIRED = "expired"
    PASSWORD_EXPIRED = "pwd_expired"

    @property
    def label(self) -> str:
        return {
            "active": "Активна", "disabled": "Отключена", "locked": "Заблокирована",
            "expired": "Срок УЗ истёк", "pwd_expired": "Пароль истёк",
        }[self.value]


@dataclass
class UserRecord:
    dn: str
    sam: str = ""
    upn: str = ""
    display_name: str = ""
    given_name: str = ""
    surname: str = ""
    mail: str = ""
    department: str = ""
    title: str = ""
    company: str = ""
    manager_dn: str = ""
    phone: str = ""
    mobile: str = ""
    office: str = ""
    description: str = ""
    employee_id: str = ""
    uac: int = 0
    enabled: bool = True
    locked: bool = False
    locked_exact: bool = True             # False when estimated from lockoutTime + lockoutDuration
    lockout_time: datetime | None = None
    pwd_last_set: datetime | None = None
    must_change_password: bool = False
    pwd_expires: datetime | None = None
    pwd_expired: bool = False
    pwd_never_expires: bool = False
    pwd_not_required: bool = False
    account_expires: datetime | None = None
    account_expired: bool = False
    last_logon_timestamp: datetime | None = None
    when_created: datetime | None = None
    when_changed: datetime | None = None
    admin_count: int = 0
    member_of: list[str] = field(default_factory=list)
    primary_group_id: int | None = None
    sid: str = ""
    bad_pwd_count: int | None = None
    cannot_change_password: bool | None = None   # None = not determined (needs nTSecurityDescriptor)

    @property
    def manager_name(self) -> str:
        return rdn_value(self.manager_dn) if self.manager_dn else ""

    @property
    def ou(self) -> str:
        return container_path(self.dn)

    @property
    def name(self) -> str:
        return self.display_name or rdn_value(self.dn)

    @property
    def rid(self) -> int | None:
        return sid_rid(self.sid) if self.sid else None

    @property
    def state(self) -> AccountState:
        if not self.enabled:
            return AccountState.DISABLED
        if self.locked:
            return AccountState.LOCKED
        if self.account_expired:
            return AccountState.EXPIRED
        if self.pwd_expired:
            return AccountState.PASSWORD_EXPIRED
        return AccountState.ACTIVE

    def days_since_logon(self, now: datetime | None = None) -> int | None:
        if not self.last_logon_timestamp:
            return None
        return ((now or utcnow()) - self.last_logon_timestamp).days

    @classmethod
    def from_entry(cls, e: Entry, policy: DomainPolicy | None = None, now: datetime | None = None) -> "UserRecord":
        now = now or utcnow()
        uac = e.int("userAccountControl", 0) or 0
        computed = e.int("msDS-User-Account-Control-Computed")
        lockout_raw = e.int("lockoutTime", 0) or 0
        lockout_time = filetime_to_datetime(lockout_raw)
        if computed is not None:
            locked, locked_exact = bool(computed & UAC.LOCKOUT), True
        else:
            locked_exact = False
            if lockout_raw > 0:
                duration = policy.lockout_duration_minutes if policy else None
                locked = duration is None or (lockout_time is not None and lockout_time + timedelta(minutes=duration) > now)
            else:
                locked = False
        pls_raw = e.first("pwdLastSet")
        pls_int = int(pls_raw) if pls_raw is not None else None
        pne = bool(uac & UAC.DONT_EXPIRE_PASSWORD)
        expiry_raw = e.int("msDS-UserPasswordExpiryTimeComputed")
        if expiry_raw is not None:
            pwd_expires = None if expiry_raw in (0, FILETIME_NEVER) else filetime_to_datetime(expiry_raw)
        elif pls_int and not pne and policy and policy.max_pwd_age_days:
            base = filetime_to_datetime(pls_int)
            pwd_expires = base + timedelta(days=policy.max_pwd_age_days) if base else None
        else:
            pwd_expires = None
        if computed is not None:
            pwd_expired = bool(computed & UAC.PASSWORD_EXPIRED)
        else:
            pwd_expired = (pls_int == 0 and not pne) or (pwd_expires is not None and pwd_expires < now)
        acct_exp_raw = e.int("accountExpires")
        account_expires = filetime_to_datetime(acct_exp_raw) if acct_exp_raw not in (None, 0, FILETIME_NEVER) else None
        return cls(
            dn=e.dn, sam=e.str("sAMAccountName"), upn=e.str("userPrincipalName"), display_name=e.str("displayName"),
            given_name=e.str("givenName"), surname=e.str("sn"), mail=e.str("mail"), department=e.str("department"),
            title=e.str("title"), company=e.str("company"), manager_dn=e.str("manager"),
            phone=e.str("telephoneNumber"), mobile=e.str("mobile"), office=e.str("physicalDeliveryOfficeName"),
            description=e.str("description"), employee_id=e.str("employeeID"), uac=uac,
            enabled=not bool(uac & UAC.ACCOUNTDISABLE), locked=locked, locked_exact=locked_exact,
            lockout_time=lockout_time if lockout_raw else None, pwd_last_set=filetime_to_datetime(pls_int),
            must_change_password=pls_int == 0, pwd_expires=pwd_expires, pwd_expired=pwd_expired,
            pwd_never_expires=pne, pwd_not_required=bool(uac & UAC.PASSWD_NOTREQD),
            account_expires=account_expires, account_expired=bool(account_expires and account_expires <= now),
            last_logon_timestamp=filetime_to_datetime(e.first("lastLogonTimestamp")),
            when_created=e.first("whenCreated") if isinstance(e.first("whenCreated"), datetime) else None,
            when_changed=e.first("whenChanged") if isinstance(e.first("whenChanged"), datetime) else None,
            admin_count=e.int("adminCount", 0) or 0, member_of=[str(v) for v in e.values("memberOf")],
            primary_group_id=e.int("primaryGroupID"),
            sid=sid_to_str(e.first("objectSid")) if e.first("objectSid") else "",
            bad_pwd_count=e.int("badPwdCount"),
        )


class OsSupport(str, Enum):
    SUPPORTED = "supported"
    OUTDATED = "outdated"
    UNKNOWN = "unknown"


@dataclass
class ComputerRecord:
    dn: str
    name: str = ""
    sam: str = ""
    dns_host_name: str = ""
    os: str = ""
    os_version: str = ""
    os_service_pack: str = ""
    uac: int = 0
    enabled: bool = True
    is_dc: bool = False
    last_logon_timestamp: datetime | None = None
    pwd_last_set: datetime | None = None
    when_created: datetime | None = None
    when_changed: datetime | None = None
    description: str = ""
    managed_by: str = ""
    location: str = ""
    os_support: OsSupport = OsSupport.UNKNOWN
    os_note: str = ""

    @property
    def ou(self) -> str:
        return container_path(self.dn)

    def days_since_logon(self, now: datetime | None = None) -> int | None:
        if not self.last_logon_timestamp:
            return None
        return ((now or utcnow()) - self.last_logon_timestamp).days

    @classmethod
    def from_entry(cls, e: Entry) -> "ComputerRecord":
        uac = e.int("userAccountControl", 0) or 0
        return cls(
            dn=e.dn, name=e.str("cn") or rdn_value(e.dn), sam=e.str("sAMAccountName"), dns_host_name=e.str("dNSHostName"),
            os=e.str("operatingSystem"), os_version=e.str("operatingSystemVersion"),
            os_service_pack=e.str("operatingSystemServicePack"), uac=uac,
            enabled=not bool(uac & UAC.ACCOUNTDISABLE), is_dc=bool(uac & UAC.SERVER_TRUST_ACCOUNT),
            last_logon_timestamp=filetime_to_datetime(e.first("lastLogonTimestamp")),
            pwd_last_set=filetime_to_datetime(e.first("pwdLastSet")),
            when_created=e.first("whenCreated") if isinstance(e.first("whenCreated"), datetime) else None,
            when_changed=e.first("whenChanged") if isinstance(e.first("whenChanged"), datetime) else None,
            description=e.str("description"), managed_by=e.str("managedBy"), location=e.str("location"),
        )


@dataclass
class GroupRecord:
    dn: str
    name: str = ""
    sam: str = ""
    description: str = ""
    group_type: int = 0
    members: list[str] = field(default_factory=list)
    member_of: list[str] = field(default_factory=list)
    managed_by: str = ""
    when_created: datetime | None = None
    sid: str = ""
    mail: str = ""
    privileged: bool = False
    privileged_reason: str = ""

    @property
    def scope(self) -> str:
        return group_scope(self.group_type)

    @property
    def category(self) -> str:
        return group_category(self.group_type)

    @property
    def is_security(self) -> bool:
        return bool(group_type_unsigned(self.group_type) & GROUP_TYPE_SECURITY)

    @property
    def rid(self) -> int | None:
        return sid_rid(self.sid) if self.sid else None

    @property
    def ou(self) -> str:
        return container_path(self.dn)

    @classmethod
    def from_entry(cls, e: Entry) -> "GroupRecord":
        return cls(
            dn=e.dn, name=e.str("cn") or rdn_value(e.dn), sam=e.str("sAMAccountName"), description=e.str("description"),
            group_type=e.int("groupType", 0) or 0, members=[str(v) for v in e.values("member")],
            member_of=[str(v) for v in e.values("memberOf")], managed_by=e.str("managedBy"),
            when_created=e.first("whenCreated") if isinstance(e.first("whenCreated"), datetime) else None,
            sid=sid_to_str(e.first("objectSid")) if e.first("objectSid") else "", mail=e.str("mail"),
        )


@dataclass
class OUNode:
    dn: str
    name: str
    kind: str = "organizationalUnit"       # organizationalUnit | container | domain | builtinDomain
    description: str = ""
    children: list["OUNode"] = field(default_factory=list)
    direct_users: int = 0
    direct_computers: int = 0
    direct_groups: int = 0
    direct_other: int = 0
    total_objects: int = 0
    protected: bool | None = None

    @property
    def direct_total(self) -> int:
        return self.direct_users + self.direct_computers + self.direct_groups + self.direct_other

    @property
    def is_empty(self) -> bool:
        return self.direct_total == 0 and not self.children

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def label(self) -> str:
        return {"critical": "Критический", "high": "Высокий", "medium": "Средний", "low": "Низкий",
                "info": "Информация"}[self.value]

    @property
    def rank(self) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}[self.value]


class Evidence(str, Enum):
    FACT = "fact"              # directly read from the directory
    REVIEW = "review"          # indicator that requires human review (not proof of a problem)
    LIMITED = "limited"        # data is incomplete / precision limited

    @property
    def label(self) -> str:
        return {"fact": "Факт", "review": "Требует проверки", "limited": "Ограниченная точность"}[self.value]


@dataclass
class Finding:
    check_id: str
    title: str
    severity: Severity
    evidence: Evidence
    object_dn: str = ""
    object_name: str = ""
    details: str = ""
    recommendation: str = ""


@dataclass
class CheckResult:
    check_id: str
    title: str
    description: str
    findings: list[Finding] = field(default_factory=list)
    error: str = ""
    limitations: str = ""
    duration_s: float = 0.0
