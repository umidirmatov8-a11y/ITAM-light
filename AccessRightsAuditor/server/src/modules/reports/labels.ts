// Русские подписи перечислений (для отчётов). Интерфейс использует аналогичный словарь web/src/i18n.
export const SEVERITY_RU: Record<string, string> = { CRITICAL: 'Критическое', HIGH: 'Высокое', MEDIUM: 'Среднее', LOW: 'Низкое', REVIEW: 'Требует проверки' };
export const OUTCOME_RU: Record<string, string> = {
  VIOLATION: 'Нарушение', COVERED_BY_EXCEPTION: 'Нарушение покрыто действующим исключением', EXCEPTION_EXPIRED: 'Исключение истекло',
  NEEDS_REVIEW: 'Требует проверки', COMPENSATED: 'Компенсирующий контроль',
};
export const RESULT_RU: Record<string, string> = { COMPLIANT: 'Соответствует', VIOLATION: 'Нарушение', COVERED_BY_EXCEPTION: 'Покрыто исключением', NEEDS_REVIEW: 'Требует проверки' };
export const TYPE_RU: Record<string, string> = {
  IDENTITY_UNRESOLVED: 'Сотрудник не сопоставлен',
  UNKNOWN_REFERENCE: 'Неизвестные справочные значения',
  TERMINATED_USER_ACCESS: 'Доступ у уволенного сотрудника',
  NOT_IN_MATRIX: 'Назначение вне матрицы',
  EXPLICITLY_DENIED: 'Явно запрещено матрицей',
  ROLE_NOT_ALLOWED: 'Роль не разрешена для должности',
  SCOPE_MISMATCH: 'Несоответствие области действия',
  EXCESS_OPERATION: 'Избыточная операция в роли',
  RESIDUAL_AFTER_TRANSFER: 'Остаточный доступ после перевода',
  SOD_CONFLICT: 'Конфликт SoD',
  SOD_CONFLICT_COMPENSATED: 'Конфликт SoD (компенсирующий контроль)',
};
export const FSTATUS_RU: Record<string, string> = { OPEN: 'Открыто', CONFIRMED: 'Подтверждено', DISPUTED: 'Оспорено', ACCEPTED_RISK: 'Риск принят', REMEDIATION: 'Устраняется', CLOSED: 'Закрыто' };
export const CHANGE_RU: Record<string, string> = {
  ADDED: 'Новое назначение', REMOVED: 'Удалённое назначение', UNCHANGED: 'Без изменений', CHANGED: 'Изменены атрибуты',
  NEW_FINDING: 'Новое нарушение', RESOLVED: 'Нарушение устранено', PERSISTING: 'Нарушение сохраняется', AMBIGUOUS: 'Неоднозначное сравнение',
};
export const IMPORT_STATUS_RU: Record<string, string> = { OK: 'OK', WARNING: 'Предупреждение', ERROR: 'Ошибка', DUPLICATE: 'Дубль' };
