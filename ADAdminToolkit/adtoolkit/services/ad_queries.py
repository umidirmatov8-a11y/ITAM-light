"""Reusable, pre-built Active Directory filters and attribute lists (all built with the escaping filter AST)."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..ldap.adtypes import UAC, GROUP_TYPE_SECURITY, datetime_to_filetime, to_generalized_time, utcnow
from ..ldap.filters import (And, Equals, Not, Or, Present, bit_and, ge, in_chain, le, text_search)

USER_ATTRIBUTES = [
    "distinguishedName", "objectClass", "sAMAccountName", "userPrincipalName", "displayName", "givenName", "sn", "cn", "mail",
    "department", "title", "company", "manager", "telephoneNumber", "mobile", "physicalDeliveryOfficeName",
    "description", "employeeID", "userAccountControl", "msDS-User-Account-Control-Computed",
    "msDS-UserPasswordExpiryTimeComputed", "lockoutTime", "pwdLastSet", "accountExpires", "lastLogonTimestamp",
    "whenCreated", "whenChanged", "adminCount", "memberOf", "primaryGroupID", "objectSid", "badPwdCount",
    "streetAddress", "l", "st", "postalCode", "info",
]

COMPUTER_ATTRIBUTES = [
    "distinguishedName", "objectClass", "cn", "sAMAccountName", "dNSHostName", "operatingSystem", "operatingSystemVersion",
    "operatingSystemServicePack", "userAccountControl", "lastLogonTimestamp", "pwdLastSet", "whenCreated",
    "whenChanged", "description", "managedBy", "location", "primaryGroupID",
]

GROUP_ATTRIBUTES = [
    "distinguishedName", "objectClass", "cn", "sAMAccountName", "description", "groupType", "member", "memberOf", "managedBy",
    "whenCreated", "whenChanged", "objectSid", "adminCount", "mail", "info",
]

USER_SEARCH_ATTRIBUTES = ["displayName", "sAMAccountName", "userPrincipalName", "givenName", "sn", "cn", "mail",
                          "department", "title", "description", "employeeID", "distinguishedName"]

IS_USER = And(Equals("objectCategory", "person"), Equals("objectClass", "user"))
IS_COMPUTER = Equals("objectCategory", "computer")
IS_GROUP = Equals("objectCategory", "group")
IS_OU = Equals("objectClass", "organizationalUnit")
IS_CONTAINER_LIKE = Or(Equals("objectClass", "organizationalUnit"), Equals("objectClass", "container"),
                       Equals("objectClass", "builtinDomain"))

DISABLED = bit_and("userAccountControl", int(UAC.ACCOUNTDISABLE))
ENABLED = Not(DISABLED)
PASSWORD_NEVER_EXPIRES = bit_and("userAccountControl", int(UAC.DONT_EXPIRE_PASSWORD))
PASSWD_NOTREQD = bit_and("userAccountControl", int(UAC.PASSWD_NOTREQD))
LOCKOUT_CANDIDATE = ge("lockoutTime", 1)
SECURITY_GROUP = bit_and("groupType", GROUP_TYPE_SECURITY)
DC_ACCOUNT = bit_and("userAccountControl", int(UAC.SERVER_TRUST_ACCOUNT))

USERS_DISABLED = And(IS_USER, DISABLED)
USERS_LOCKED_CANDIDATES = And(IS_USER, LOCKOUT_CANDIDATE)
COMPUTERS_DISABLED = And(IS_COMPUTER, DISABLED)


def filetime_cutoff(days: int, now: datetime | None = None) -> int:
    return datetime_to_filetime((now or utcnow()) - timedelta(days=int(days)))


def stale_logon_filter(days: int, now: datetime | None = None):
    """lastLogonTimestamp older than *days* OR never replicated a logon — the second case needs verification."""
    cutoff = filetime_cutoff(days, now)
    return Or(le("lastLogonTimestamp", cutoff), Not(Present("lastLogonTimestamp")))


def created_before(days: int, now: datetime | None = None):
    return le("whenCreated", to_generalized_time((now or utcnow()) - timedelta(days=int(days))))


def created_since(days: int, now: datetime | None = None):
    return ge("whenCreated", to_generalized_time((now or utcnow()) - timedelta(days=int(days))))


def account_expired(now: datetime | None = None):
    nowft = datetime_to_filetime(now or utcnow())
    return And(ge("accountExpires", 1), le("accountExpires", nowft))


def missing_any(attrs: list[str]):
    return Or(*[Not(Present(a)) for a in attrs])


def member_of_transitive(group_dn: str):
    return in_chain("memberOf", group_dn)


def groups_of_member_transitive(member_dn: str):
    return And(IS_GROUP, in_chain("member", member_dn))


def user_text_filter(text: str):
    return text_search(USER_SEARCH_ATTRIBUTES, text)


# Example filters shown in LDAP Explorer (rendered through the AST so escaping is guaranteed).
EXAMPLE_FILTERS = {
    "Отключённые пользователи": USERS_DISABLED,
    "Кандидаты в заблокированные пользователи (lockoutTime ≥ 1)": USERS_LOCKED_CANDIDATES,
    "Все компьютеры": IS_COMPUTER,
    "Отключённые компьютеры": COMPUTERS_DISABLED,
    "Пользователи с Password Never Expires": And(IS_USER, PASSWORD_NEVER_EXPIRES),
    "Группы безопасности": And(IS_GROUP, SECURITY_GROUP),
    "Пустые группы (без атрибута member)": And(IS_GROUP, Not(Present("member"))),
    "Учётные записи с adminCount=1": And(IS_USER, Equals("adminCount", 1)),
    "Контроллеры домена": And(IS_COMPUTER, DC_ACCOUNT),
    "Пользователи без email": And(IS_USER, Not(Present("mail"))),
}
