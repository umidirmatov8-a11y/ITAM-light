"""Translate LDAP result codes, Active Directory extended errors and ldap3 exceptions into toolkit errors."""
from __future__ import annotations

import re
import socket
import ssl

from ..core import errors as E
from ..security.masking import mask_text

# RFC 4511 result codes
SUCCESS = 0
OPERATIONS_ERROR = 1
PROTOCOL_ERROR = 2
TIME_LIMIT_EXCEEDED = 3
SIZE_LIMIT_EXCEEDED = 4
AUTH_METHOD_NOT_SUPPORTED = 7
STRONGER_AUTH_REQUIRED = 8
REFERRAL = 10
ADMIN_LIMIT_EXCEEDED = 11
UNAVAILABLE_CRITICAL_EXTENSION = 12
CONFIDENTIALITY_REQUIRED = 13
NO_SUCH_ATTRIBUTE = 16
UNDEFINED_ATTRIBUTE_TYPE = 17
CONSTRAINT_VIOLATION = 19
ATTRIBUTE_OR_VALUE_EXISTS = 20
INVALID_ATTRIBUTE_SYNTAX = 21
NO_SUCH_OBJECT = 32
INVALID_DN_SYNTAX = 34
INVALID_CREDENTIALS = 49
INSUFFICIENT_ACCESS_RIGHTS = 50
BUSY = 51
UNAVAILABLE = 52
UNWILLING_TO_PERFORM = 53
NAMING_VIOLATION = 64
OBJECT_CLASS_VIOLATION = 65
NOT_ALLOWED_ON_NON_LEAF = 66
NOT_ALLOWED_ON_RDN = 67
ENTRY_ALREADY_EXISTS = 68
OTHER = 80

RETRYABLE_READ_CODES = {BUSY, UNAVAILABLE}

# AD bind sub-status ("data XXX" in the diagnostic message)
BIND_SUBCODES = {
    "525": "Пользователь не найден",
    "52e": "Неверное имя пользователя или пароль",
    "530": "Вход в это время запрещён",
    "531": "Вход с этой рабочей станции запрещён",
    "532": "Срок действия пароля истёк",
    "533": "Учётная запись отключена",
    "568": "Слишком много SID в маркере безопасности",
    "701": "Срок действия учётной записи истёк",
    "773": "Пользователь должен сменить пароль перед входом",
    "775": "Учётная запись заблокирована",
}

_AD_WIN32_RE = re.compile(r"^\s*([0-9A-Fa-f]{8}):")
_BIND_DATA_RE = re.compile(r"data\s+([0-9a-fA-F]{3,4})")

# Win32 codes that appear at the beginning of AD diagnostic messages
WIN32_MESSAGES = {
    0x0000052D: ("password", "Пароль не соответствует требованиям политики (длина, сложность, история или минимальный срок действия)"),
    0x00000005: ("access", "Доступ запрещён ACL объекта"),
    0x0000208D: ("notfound", "Объект не найден"),
    0x00002071: ("exists", "Объект с таким именем уже существует"),
    0x000020B1: ("exists", "Объект с таким именем уже существует"),
    0x00000524: ("exists", "Имя входа (sAMAccountName) уже используется"),
    0x0000202B: ("referral", "Получен referral — объект находится в другом домене/разделе"),
    0x00002077: ("constraint", "Нарушено ограничение схемы"),
    0x000020E6: ("constraint", "Нельзя удалить объект: он защищён или является системным"),
    0x00002085: ("constraint", "Атрибут или значение уже существует"),
    0x0000200B: ("constraint", "Недопустимый синтаксис значения атрибута"),
    0x000020EF: ("protected", "Объект защищён от удаления/перемещения (Protect object from accidental deletion)"),
}


def _diagnostic(result: dict) -> str:
    return mask_text((result or {}).get("message") or (result or {}).get("description") or "")


def ad_win32_code(message: str) -> int | None:
    m = _AD_WIN32_RE.match(message or "")
    return int(m.group(1), 16) if m else None


def map_bind_result(result: dict) -> E.ToolkitError:
    code = (result or {}).get("result")
    msg = _diagnostic(result)
    if code == INVALID_CREDENTIALS:
        m = _BIND_DATA_RE.search(msg)
        sub = m.group(1).lower() if m else ""
        text = BIND_SUBCODES.get(sub, "Неверное имя пользователя или пароль")
        return E.AuthenticationError(text, details=msg, code=code)
    if code == STRONGER_AUTH_REQUIRED:
        return E.InsecureConnectionError(
            "Контроллер домена требует подписывания/шифрования LDAP (LDAP signing)",
            hint="Используйте LDAPS (636) или StartTLS.", details=msg, code=code)
    if code == CONFIDENTIALITY_REQUIRED:
        return E.InsecureConnectionError("Контроллер требует зашифрованное соединение", details=msg, code=code,
                                         hint="Используйте LDAPS (636) или StartTLS.")
    if code == AUTH_METHOD_NOT_SUPPORTED:
        return E.AuthenticationError("Способ аутентификации не поддерживается контроллером", details=msg, code=code)
    return map_result(result, "bind", "")


def map_result(result: dict, operation: str, target: str = "") -> E.ToolkitError:
    """Map a non-successful LDAP result to a typed toolkit error."""
    code = (result or {}).get("result")
    msg = _diagnostic(result)
    where = f" ({target})" if target else ""
    win32 = ad_win32_code(msg)
    if win32 in WIN32_MESSAGES:
        kind, text = WIN32_MESSAGES[win32]
        if kind == "password":
            return E.PasswordPolicyError(text, details=msg, code=code)
        if kind == "access":
            return E.PermissionDeniedError(f"Недостаточно прав для операции «{operation}»{where}", details=msg, code=code,
                                           hint="Проверьте делегирование прав на объект/OU для учётной записи подключения.")
        if kind == "exists":
            return E.ConflictError(text + where, details=msg, code=code)
        if kind == "notfound":
            return E.ObjectNotFoundError(text + where, details=msg, code=code)
        if kind == "protected":
            return E.PermissionDeniedError(text + where, details=msg, code=code,
                                           hint="Снимите флаг защиты от случайного удаления, если операция действительно нужна.")
    if code == INSUFFICIENT_ACCESS_RIGHTS:
        return E.PermissionDeniedError(f"Недостаточно прав для операции «{operation}»{where}", details=msg, code=code,
                                       hint="Проверьте делегирование прав на объект/OU для учётной записи подключения.")
    if code == NO_SUCH_OBJECT:
        return E.ObjectNotFoundError(f"Объект не найден{where}", details=msg, code=code)
    if code == ENTRY_ALREADY_EXISTS:
        return E.ConflictError(f"Объект с таким именем уже существует{where}", details=msg, code=code)
    if code == NO_SUCH_ATTRIBUTE:
        return E.ConflictError(f"Значение атрибута изменилось с момента чтения{where}", details=msg, code=code,
                               hint="Обновите данные объекта и повторите операцию.")
    if code == ATTRIBUTE_OR_VALUE_EXISTS:
        return E.ConflictError(f"Значение уже присутствует{where}", details=msg, code=code)
    if code == CONSTRAINT_VIOLATION:
        if "unicodePwd" in msg or "052D" in msg.upper():
            return E.PasswordPolicyError(details=msg, code=code)
        return E.ConstraintViolationError(f"Нарушено ограничение каталога{where}", details=msg, code=code)
    if code in (INVALID_ATTRIBUTE_SYNTAX, UNDEFINED_ATTRIBUTE_TYPE, OBJECT_CLASS_VIOLATION, NAMING_VIOLATION,
                NOT_ALLOWED_ON_RDN, INVALID_DN_SYNTAX):
        return E.ConstraintViolationError(f"Некорректные данные для операции «{operation}»{where}", details=msg, code=code)
    if code == NOT_ALLOWED_ON_NON_LEAF:
        return E.ConstraintViolationError(f"Объект содержит дочерние объекты{where}", details=msg, code=code)
    if code == UNWILLING_TO_PERFORM:
        if "unicodePwd" in msg or "0000001F" in msg:
            return E.InsecureConnectionError("Контроллер отказался изменять пароль по незашифрованному соединению",
                                             details=msg, code=code)
        return E.ConstraintViolationError(f"Контроллер домена отказался выполнить операцию{where}", details=msg, code=code)
    if code in (STRONGER_AUTH_REQUIRED, CONFIDENTIALITY_REQUIRED):
        return E.InsecureConnectionError("Требуется защищённое соединение", details=msg, code=code)
    if code == TIME_LIMIT_EXCEEDED:
        return E.LdapTimeoutError("Превышен лимит времени выполнения запроса на сервере", details=msg, code=code)
    if code == ADMIN_LIMIT_EXCEEDED:
        return E.ToolkitError("Превышен административный лимит сервера (MaxPageSize/MaxResultSetSize)", details=msg, code=code,
                              hint="Сузьте условия поиска.")
    if code in (BUSY, UNAVAILABLE):
        return E.ConnectionFailedError("Контроллер домена занят или недоступен", details=msg, code=code)
    if code == REFERRAL:
        return E.ObjectNotFoundError(f"Объект находится вне текущего домена (referral){where}", details=msg, code=code)
    desc = (result or {}).get("description") or "unknown"
    return E.ToolkitError(f"Ошибка LDAP при операции «{operation}»{where}: {desc}", details=msg, code=code)


def map_exception(exc: BaseException, operation: str = "connect") -> E.ToolkitError:
    """Map ldap3/socket/ssl exceptions."""
    if isinstance(exc, E.ToolkitError):
        return exc
    text = mask_text(str(exc))
    name = type(exc).__name__
    lowered = text.lower()
    if isinstance(exc, ssl.SSLCertVerificationError) or "certificate verify failed" in lowered or "certificate_verify_failed" in lowered:
        return E.CertificateError(
            "Сертификат контроллера домена не прошёл проверку (недоверенный издатель, истёк срок или не совпадает имя)",
            details=text,
            hint="Укажите FQDN контроллера, совпадающее с сертификатом; установите корневой сертификат ЦС домена в "
                 "хранилище «Доверенные корневые центры сертификации» или укажите PEM-файл ЦС в профиле.")
    if "hostname" in lowered and ("match" in lowered or "doesn't" in lowered) or name == "LDAPCertificateError":
        return E.CertificateError("Имя в сертификате не совпадает с именем сервера", details=text,
                                  hint="Подключайтесь по FQDN, указанному в сертификате контроллера домена.")
    if isinstance(exc, (socket.timeout, TimeoutError)) or "timed out" in lowered or "timeout" in lowered:
        return E.LdapTimeoutError(details=text, hint="Проверьте сетевую доступность контроллера и тайм-ауты профиля.")
    if name == "LDAPPackageUnavailableError":
        return E.UnsupportedFeatureError(
            "Для Kerberos-аутентификации требуется пакет winkerberos (Windows) или gssapi", details=text)
    if name == "LDAPStartTLSError":
        return E.CertificateError("Не удалось установить StartTLS", details=text,
                                  hint="Проверьте сертификат контроллера домена или используйте LDAPS.")
    if name in ("LDAPSocketOpenError", "LDAPSocketReceiveError", "LDAPSocketSendError", "LDAPSessionTerminatedByServerError",
                "LDAPSocketCloseError", "LDAPCommunicationError") or isinstance(exc, (ConnectionError, OSError)):
        if "ssl" in lowered or "tls" in lowered:
            return E.CertificateError("Ошибка TLS при подключении", details=text,
                                      hint="Проверьте, что на контроллере установлен сертификат для LDAPS и порт верный.")
        if operation in ("connect", "bind"):
            return E.ConnectionFailedError("Сервер LDAP недоступен", details=text,
                                           hint="Проверьте имя/адрес контроллера, порт и сетевые правила (TCP 389/636).")
        return E.ConnectionLostError(details=text)
    if name == "LDAPBindError":
        return E.AuthenticationError(details=text)
    if name == "LDAPInvalidFilterError":
        return E.ValidationError("Некорректный LDAP-фильтр", details=text)
    if name in ("LDAPInvalidDnError", "LDAPInvalidDNSyntaxResult"):
        return E.ValidationError("Некорректный DN", details=text)
    return E.ToolkitError(f"Ошибка при операции «{operation}»", details=f"{name}: {text}")
