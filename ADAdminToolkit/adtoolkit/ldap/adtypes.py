"""Active Directory data types: userAccountControl, groupType, FILETIME, SID, GUID and attribute decoding."""
from __future__ import annotations

import struct
import uuid
from datetime import datetime, timedelta, timezone
from enum import IntFlag

# ----------------------------------------------------------------------------------------------------------------
# userAccountControl
# ----------------------------------------------------------------------------------------------------------------


class UAC(IntFlag):
    SCRIPT = 0x0001
    ACCOUNTDISABLE = 0x0002
    HOMEDIR_REQUIRED = 0x0008
    LOCKOUT = 0x0010
    PASSWD_NOTREQD = 0x0020
    PASSWD_CANT_CHANGE = 0x0040
    ENCRYPTED_TEXT_PWD_ALLOWED = 0x0080
    TEMP_DUPLICATE_ACCOUNT = 0x0100
    NORMAL_ACCOUNT = 0x0200
    INTERDOMAIN_TRUST_ACCOUNT = 0x0800
    WORKSTATION_TRUST_ACCOUNT = 0x1000
    SERVER_TRUST_ACCOUNT = 0x2000
    DONT_EXPIRE_PASSWORD = 0x10000
    MNS_LOGON_ACCOUNT = 0x20000
    SMARTCARD_REQUIRED = 0x40000
    TRUSTED_FOR_DELEGATION = 0x80000
    NOT_DELEGATED = 0x100000
    USE_DES_KEY_ONLY = 0x200000
    DONT_REQ_PREAUTH = 0x400000
    PASSWORD_EXPIRED = 0x800000
    TRUSTED_TO_AUTH_FOR_DELEGATION = 0x1000000
    PARTIAL_SECRETS_ACCOUNT = 0x4000000


UAC_DESCRIPTIONS_RU = {
    UAC.SCRIPT: "Выполняется сценарий входа",
    UAC.ACCOUNTDISABLE: "Учётная запись отключена",
    UAC.HOMEDIR_REQUIRED: "Требуется домашний каталог",
    UAC.LOCKOUT: "Заблокирована (вычисляемый флаг)",
    UAC.PASSWD_NOTREQD: "Пароль не требуется",
    UAC.PASSWD_CANT_CHANGE: "Запрет смены пароля (флаг; фактически определяется ACL)",
    UAC.ENCRYPTED_TEXT_PWD_ALLOWED: "Хранение пароля с обратимым шифрованием",
    UAC.TEMP_DUPLICATE_ACCOUNT: "Локальная учётная запись-дубликат",
    UAC.NORMAL_ACCOUNT: "Обычная учётная запись",
    UAC.INTERDOMAIN_TRUST_ACCOUNT: "Учётная запись доверия между доменами",
    UAC.WORKSTATION_TRUST_ACCOUNT: "Учётная запись компьютера (рабочая станция/сервер)",
    UAC.SERVER_TRUST_ACCOUNT: "Учётная запись контроллера домена",
    UAC.DONT_EXPIRE_PASSWORD: "Срок действия пароля не ограничен (Password Never Expires)",
    UAC.MNS_LOGON_ACCOUNT: "MNS logon account",
    UAC.SMARTCARD_REQUIRED: "Требуется смарт-карта",
    UAC.TRUSTED_FOR_DELEGATION: "Доверен для делегирования (неограниченное)",
    UAC.NOT_DELEGATED: "Учётная запись важна и не может быть делегирована",
    UAC.USE_DES_KEY_ONLY: "Только DES-шифрование Kerberos",
    UAC.DONT_REQ_PREAUTH: "Без предварительной проверки подлинности Kerberos",
    UAC.PASSWORD_EXPIRED: "Пароль истёк (вычисляемый флаг)",
    UAC.TRUSTED_TO_AUTH_FOR_DELEGATION: "Доверен для делегирования с переходом протоколов",
    UAC.PARTIAL_SECRETS_ACCOUNT: "Контроллер домена только для чтения (RODC)",
}


def uac_flags_text(value: int | None) -> list[str]:
    if value is None:
        return []
    return [text for flag, text in UAC_DESCRIPTIONS_RU.items() if int(value) & int(flag)]


# ----------------------------------------------------------------------------------------------------------------
# groupType
# ----------------------------------------------------------------------------------------------------------------

GROUP_TYPE_SYSTEM = 0x00000001
GROUP_TYPE_GLOBAL = 0x00000002
GROUP_TYPE_DOMAIN_LOCAL = 0x00000004
GROUP_TYPE_UNIVERSAL = 0x00000008
GROUP_TYPE_APP_BASIC = 0x00000010
GROUP_TYPE_APP_QUERY = 0x00000020
GROUP_TYPE_SECURITY = 0x80000000

SCOPE_GLOBAL = "Глобальная"
SCOPE_DOMAIN_LOCAL = "Локальная в домене"
SCOPE_UNIVERSAL = "Универсальная"
SCOPE_BUILTIN = "Встроенная локальная"
CATEGORY_SECURITY = "Безопасности"
CATEGORY_DISTRIBUTION = "Распространения"

GROUP_SCOPES = {
    "global": GROUP_TYPE_GLOBAL,
    "domainlocal": GROUP_TYPE_DOMAIN_LOCAL,
    "universal": GROUP_TYPE_UNIVERSAL,
}


def group_type_unsigned(value: int | None) -> int:
    return (int(value) & 0xFFFFFFFF) if value is not None else 0


def group_type_signed(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def group_scope(value: int | None) -> str:
    v = group_type_unsigned(value)
    if v & GROUP_TYPE_SYSTEM and v & GROUP_TYPE_DOMAIN_LOCAL:
        return SCOPE_BUILTIN
    if v & GROUP_TYPE_GLOBAL:
        return SCOPE_GLOBAL
    if v & GROUP_TYPE_DOMAIN_LOCAL:
        return SCOPE_DOMAIN_LOCAL
    if v & GROUP_TYPE_UNIVERSAL:
        return SCOPE_UNIVERSAL
    return "Неизвестно"


def group_category(value: int | None) -> str:
    return CATEGORY_SECURITY if group_type_unsigned(value) & GROUP_TYPE_SECURITY else CATEGORY_DISTRIBUTION


def make_group_type(scope: str, security: bool) -> int:
    if scope not in GROUP_SCOPES:
        raise ValueError(f"Неизвестная область действия группы: {scope}")
    value = GROUP_SCOPES[scope] | (GROUP_TYPE_SECURITY if security else 0)
    return group_type_signed(value)


# ----------------------------------------------------------------------------------------------------------------
# Time
# ----------------------------------------------------------------------------------------------------------------

FILETIME_NEVER = 0x7FFFFFFFFFFFFFFF
_EPOCH_1601 = datetime(1601, 1, 1, tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def filetime_to_datetime(value) -> datetime | None:
    """Convert AD FILETIME (100 ns since 1601-01-01 UTC). 0 and 'never' map to ``None``."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    if v <= 0 or v >= FILETIME_NEVER:
        return None
    try:
        return _EPOCH_1601 + timedelta(microseconds=v // 10)
    except OverflowError:
        return None


def datetime_to_filetime(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = dt.astimezone(timezone.utc) - _EPOCH_1601
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


def interval_to_timedelta(value) -> timedelta | None:
    """Negative 100-ns intervals used by maxPwdAge / lockoutDuration. ``None`` means 'never' / not set."""
    if value is None:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    if v == 0 or v == -0x8000000000000000:
        return None
    return timedelta(microseconds=abs(v) // 10)


def parse_generalized_time(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = value.decode("ascii", "ignore") if isinstance(value, bytes) else str(value)
    s = s.strip()
    if not s:
        return None
    tz = timezone.utc
    if s.endswith("Z"):
        s = s[:-1]
    elif len(s) > 5 and s[-5] in "+-":
        sign = 1 if s[-5] == "+" else -1
        tz = timezone(sign * timedelta(hours=int(s[-4:-2]), minutes=int(s[-2:])))
        s = s[:-5]
    frac = 0.0
    if "." in s or "," in s:
        s, _, f = s.replace(",", ".").partition(".")
        frac = float("0." + (f or "0"))
    try:
        dt = datetime.strptime(s[:14].ljust(14, "0"), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return (dt + timedelta(seconds=frac)).replace(tzinfo=tz).astimezone(timezone.utc)


def to_generalized_time(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S.0Z")


def format_dt(dt: datetime | None, empty: str = "") -> str:
    if dt is None:
        return empty
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


# ----------------------------------------------------------------------------------------------------------------
# SID / GUID
# ----------------------------------------------------------------------------------------------------------------


def sid_to_str(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    raw = bytes(raw)
    if len(raw) < 8:
        raise ValueError("Некорректный SID")
    revision = raw[0]
    count = raw[1]
    authority = int.from_bytes(raw[2:8], "big")
    subs = struct.unpack("<" + "I" * count, raw[8:8 + 4 * count])
    return "S-{}-{}".format(revision, authority) + "".join(f"-{s}" for s in subs)


def str_to_sid(text: str) -> bytes:
    parts = text.strip().upper().split("-")
    if len(parts) < 3 or parts[0] != "S":
        raise ValueError(f"Некорректная строка SID: {text}")
    revision = int(parts[1])
    authority = int(parts[2])
    subs = [int(p) for p in parts[3:]]
    return bytes([revision, len(subs)]) + authority.to_bytes(6, "big") + b"".join(struct.pack("<I", s) for s in subs)


def sid_rid(sid) -> int | None:
    s = sid_to_str(sid) if not isinstance(sid, str) else sid
    try:
        return int(s.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None


def sid_domain_part(sid) -> str:
    s = sid_to_str(sid) if not isinstance(sid, str) else sid
    return s.rsplit("-", 1)[0]


def guid_to_str(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return str(uuid.UUID(bytes_le=bytes(raw)))


def str_to_guid_bytes(text: str) -> bytes:
    return uuid.UUID(text.strip("{}")).bytes_le


# ----------------------------------------------------------------------------------------------------------------
# Attribute syntax table and decoding of raw LDAP values
# ----------------------------------------------------------------------------------------------------------------

INTEGER_ATTRIBUTES = {
    "useraccountcontrol", "grouptype", "primarygroupid", "admincount", "badpwdcount", "logoncount",
    "msds-user-account-control-computed", "samaccounttype", "instancetype", "systemflags", "msds-behavior-version",
    "pwdproperties", "minpwdlength", "pwdhistorylength", "lockoutthreshold", "primarygrouptoken",
    "msds-supportedencryptiontypes", "countrycode", "codepage", "domainfunctionality", "forestfunctionality",
    "domaincontrollerfunctionality", "ms-ds-machineaccountquota", "msds-logontimesyncinterval",
    "maxpwdage", "minpwdage", "lockoutduration", "lockoutobservationwindow", "forcelogoff",
    "lastlogon", "lastlogontimestamp", "pwdlastset", "accountexpires", "lockouttime", "badpasswordtime",
    "msds-userpasswordexpirytimecomputed", "lastlogoff", "usncreated", "usnchanged", "highestcommittedusn",
    "msds-minimumpasswordlength", "msds-passwordhistorylength", "msds-lockoutthreshold",
    "msds-passwordsettingsprecedence", "msds-maximumpasswordage", "msds-minimumpasswordage",
    "msds-lockoutduration", "msds-lockoutobservationwindow", "operatingsystemservicepackversion_int",
}

FILETIME_ATTRIBUTES = {
    "lastlogon", "lastlogontimestamp", "pwdlastset", "accountexpires", "lockouttime", "badpasswordtime",
    "msds-userpasswordexpirytimecomputed", "lastlogoff",
}

INTERVAL_ATTRIBUTES = {
    "maxpwdage", "minpwdage", "lockoutduration", "lockoutobservationwindow", "forcelogoff",
    "msds-maximumpasswordage", "msds-minimumpasswordage", "msds-lockoutduration", "msds-lockoutobservationwindow",
}

GENERALIZED_TIME_ATTRIBUTES = {
    "whencreated", "whenchanged", "currenttime", "dscorepropagationdata", "createtimestamp", "modifytimestamp",
    "msds-lastsuccessfulinteractivelogontime",
}

BOOLEAN_ATTRIBUTES = {"issynchronized", "isglobalcatalogready", "msds-passwordcomplexityenabled",
                      "msds-passwordreversibleencryptionenabled", "showinadvancedviewonly", "iscriticalsystemobject"}

BINARY_ATTRIBUTES = {
    "objectsid", "objectguid", "ntsecuritydescriptor", "tokengroups", "tokengroupsglobalanduniversal",
    "thumbnailphoto", "jpegphoto", "usercertificate", "cacertificate", "ms-ds-consistencyguid", "msds-generationid",
    "sidhistory", "logonhours", "msds-allowedtoactonbehalfofotheridentity", "msexchmailboxguid", "msexchmailboxsecuritydescriptor",
    "msds-keycredentiallink", "replicationsignature", "dnsrecord", "dsasignature", "repluptodatevector",
    "repsfrom", "repsto", "schemaidguid", "attributesecurityguid", "objectclasscategory_bin", "msds-managedpasswordid",
    "msds-managedpassword", "msds-groupmsamembership", "unicodepwd", "dbcspwd", "supplementalcredentials",
    "msmqdigests", "msmqsigncertificates", "msds-cloudanchor_bin", "msds-externaldirectoryobjectid_bin",
    "terminalserver", "usersmimecertificate", "msds-revealedusers_bin",
}

SECRET_ATTRIBUTES = {"unicodepwd", "dbcspwd", "supplementalcredentials", "ntpwdhistory", "lmpwdhistory",
                     "msds-managedpassword", "userpassword", "unixuserpassword", "mssfu30password"}


def attribute_kind(name: str) -> str:
    n = name.lower().split(";", 1)[0]
    if n in BINARY_ATTRIBUTES:
        return "binary"
    if n in GENERALIZED_TIME_ATTRIBUTES:
        return "gentime"
    if n in INTEGER_ATTRIBUTES:
        return "int"
    if n in BOOLEAN_ATTRIBUTES:
        return "bool"
    return "str"


def decode_value(name: str, raw):
    """Normalise one raw LDAP value (bytes) to a Python value according to the attribute syntax table."""
    kind = attribute_kind(name)
    if kind == "binary":
        return bytes(raw) if not isinstance(raw, (bytes, bytearray)) else bytes(raw)
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return bytes(raw)
    else:
        text = raw
    if kind == "int":
        try:
            return int(text)
        except (TypeError, ValueError):
            return text
    if kind == "gentime":
        parsed = parse_generalized_time(text)
        return parsed if parsed is not None else text
    if kind == "bool":
        return str(text).upper() == "TRUE"
    return text


def decode_attributes(raw_attributes: dict) -> dict[str, list]:
    """Decode an ldap3 ``raw_attributes`` mapping; merges ranged values (``member;range=0-1499``)."""
    out: dict[str, list] = {}
    ranged: dict[str, list] = {}
    for name, values in (raw_attributes or {}).items():
        if not isinstance(values, (list, tuple)):
            values = [values]
        base, _, opt = name.partition(";")
        if opt.lower().startswith("range="):
            ranged.setdefault(base, []).extend(values)
            continue
        if name.lower().split(";", 1)[0] in SECRET_ATTRIBUTES:
            continue  # never keep secret material, even if a DC returned it
        out[name] = [decode_value(name, v) for v in values]
    for base, values in ranged.items():
        if not any(k.lower() == base.lower() for k in out):
            out[base] = [decode_value(base, v) for v in values]
    return out


def display_value(name: str, value) -> str:
    """Readable representation of a decoded value (used by the raw attribute viewers)."""
    n = name.lower()
    if value is None:
        return ""
    if n in ("objectsid", "sidhistory") and isinstance(value, (bytes, bytearray)):
        try:
            return sid_to_str(value)
        except Exception:
            pass
    if n == "tokengroups" and isinstance(value, (bytes, bytearray)):
        return sid_to_str(value)
    if n in ("objectguid", "ms-ds-consistencyguid", "schemaidguid") and isinstance(value, (bytes, bytearray)) and len(value) == 16:
        return "{" + guid_to_str(value) + "}"
    if isinstance(value, (bytes, bytearray)):
        head = bytes(value[:32]).hex(" ")
        return f"<{len(value)} байт> {head}{' …' if len(value) > 32 else ''}"
    if n in FILETIME_ATTRIBUTES and isinstance(value, int):
        if value == 0:
            return "0 (не задано)"
        if value >= FILETIME_NEVER:
            return f"{value} (никогда)"
        dt = filetime_to_datetime(value)
        return f"{format_dt(dt)} ({value})" if dt else str(value)
    if n in INTERVAL_ATTRIBUTES and isinstance(value, int):
        td = interval_to_timedelta(value)
        return f"{td} ({value})" if td else f"не ограничено ({value})"
    if n == "useraccountcontrol" and isinstance(value, int):
        return f"{value} (0x{value:X}): " + "; ".join(uac_flags_text(value))
    if n == "grouptype" and isinstance(value, int):
        return f"{value}: {group_scope(value)}, {group_category(value)}"
    if isinstance(value, datetime):
        return format_dt(value)
    return str(value)
