"""Unified error model.

Every failure that reaches the UI is a :class:`ToolkitError` with a Russian user-facing message, an optional
technical detail (already masked) and a category used for colouring and for the operation journal.
"""
from __future__ import annotations

from ..security.masking import mask_text


class ToolkitError(Exception):
    category = "error"
    default_message = "Ошибка выполнения операции"

    def __init__(self, message: str | None = None, *, details: str | None = None, hint: str | None = None,
                 code: int | None = None):
        self.message = mask_text(message or self.default_message)
        self.details = mask_text(details) if details else None
        self.hint = hint
        self.code = code
        super().__init__(self.message)

    def full_text(self) -> str:
        parts = [self.message]
        if self.hint:
            parts.append(f"Рекомендация: {self.hint}")
        if self.details:
            parts.append(f"Технические сведения: {self.details}")
        return "\n\n".join(parts)


class ConfigurationError(ToolkitError):
    category = "config"
    default_message = "Некорректные параметры"


class ValidationError(ToolkitError):
    category = "validation"
    default_message = "Ошибка проверки входных данных"


class NotConnectedError(ToolkitError):
    category = "connection"
    default_message = "Нет подключения к Active Directory"


class ConnectionFailedError(ToolkitError):
    category = "connection"
    default_message = "Не удалось подключиться к контроллеру домена"


class ConnectionLostError(ConnectionFailedError):
    default_message = "Соединение с контроллером домена потеряно"


class LdapTimeoutError(ConnectionFailedError):
    default_message = "Превышено время ожидания ответа LDAP"


class CertificateError(ConnectionFailedError):
    category = "security"
    default_message = "Сертификат контроллера домена не прошёл проверку"


class InsecureConnectionError(ToolkitError):
    category = "security"
    default_message = "Операция запрещена: соединение не зашифровано"


class AuthenticationError(ToolkitError):
    category = "auth"
    default_message = "Ошибка аутентификации"


class PermissionDeniedError(ToolkitError):
    category = "permission"
    default_message = "Недостаточно прав для выполнения операции"


class ReadOnlyModeError(PermissionDeniedError):
    default_message = "Приложение работает в режиме только для чтения — изменения запрещены"


class ProtectedObjectError(PermissionDeniedError):
    default_message = "Объект защищён от изменения политикой приложения"


class ObjectNotFoundError(ToolkitError):
    category = "notfound"
    default_message = "Объект не найден"


class ConflictError(ToolkitError):
    category = "conflict"
    default_message = "Конфликт изменения: объект был изменён или уже существует"


class ConstraintViolationError(ToolkitError):
    category = "constraint"
    default_message = "Значение не удовлетворяет ограничениям каталога"


class PasswordPolicyError(ConstraintViolationError):
    default_message = "Пароль не соответствует парольной политике домена"


class OperationCancelledError(ToolkitError):
    category = "cancelled"
    default_message = "Операция отменена пользователем"


class UnsupportedFeatureError(ToolkitError):
    category = "unsupported"
    default_message = "Функция недоступна в текущей среде"


class ExternalToolError(ToolkitError):
    category = "external"
    default_message = "Ошибка внешнего компонента Windows"


def describe_exception(exc: BaseException) -> str:
    """Human readable, masked description for any exception."""
    if isinstance(exc, ToolkitError):
        return exc.full_text()
    return mask_text(f"{type(exc).__name__}: {exc}")
