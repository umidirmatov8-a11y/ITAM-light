// Словарь интерфейса. MVP — русский; структура позволяет добавить узбекский (uz) без изменения компонентов.
export type Lang = 'ru';

export const SEVERITY: Record<string, string> = { CRITICAL: 'Критическое', HIGH: 'Высокое', MEDIUM: 'Среднее', LOW: 'Низкое', REVIEW: 'Требует проверки' };
export const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'REVIEW'];
export const RISK: Record<string, string> = { CRITICAL: 'Критический', HIGH: 'Высокий', MEDIUM: 'Средний', LOW: 'Низкий' };
export const OUTCOME: Record<string, string> = {
  VIOLATION: 'Нарушение', COVERED_BY_EXCEPTION: 'Покрыто исключением', EXCEPTION_EXPIRED: 'Исключение истекло',
  NEEDS_REVIEW: 'Требует проверки', COMPENSATED: 'Компенсирующий контроль',
};
export const RESULT: Record<string, string> = { COMPLIANT: 'Соответствует', VIOLATION: 'Нарушение', COVERED_BY_EXCEPTION: 'Покрыто исключением', NEEDS_REVIEW: 'Требует проверки' };
export const FINDING_TYPE: Record<string, string> = {
  IDENTITY_UNRESOLVED: 'Сотрудник не сопоставлен',
  UNKNOWN_REFERENCE: 'Неизвестные справочные значения',
  TERMINATED_USER_ACCESS: 'Доступ у уволенного',
  NOT_IN_MATRIX: 'Вне матрицы',
  EXPLICITLY_DENIED: 'Явно запрещено',
  ROLE_NOT_ALLOWED: 'Роль не разрешена',
  SCOPE_MISMATCH: 'Несоответствие области действия',
  EXCESS_OPERATION: 'Избыточная операция в роли',
  RESIDUAL_AFTER_TRANSFER: 'Остаточный доступ после перевода',
  SOD_CONFLICT: 'Конфликт SoD',
  SOD_CONFLICT_COMPENSATED: 'SoD с компенсирующим контролем',
};
export const FINDING_STATUS: Record<string, string> = { OPEN: 'Открыто', CONFIRMED: 'Подтверждено', DISPUTED: 'Оспорено', ACCEPTED_RISK: 'Риск принят', REMEDIATION: 'Устраняется', CLOSED: 'Закрыто' };
export const AUDIT_STATUS: Record<string, string> = { DRAFT: 'Черновик', RUNNING: 'Выполняется', COMPLETED: 'Выполнен', FAILED: 'Ошибка' };
export const BATCH_STATUS: Record<string, string> = { UPLOADED: 'Загружен, не обработан', PROCESSED: 'Обработан', PROCESSED_WITH_ERRORS: 'Обработан с замечаниями', FAILED: 'Ошибка' };
export const ROW_STATUS: Record<string, string> = { OK: 'OK', WARNING: 'Предупреждение', ERROR: 'Ошибка (карантин)', DUPLICATE: 'Дубль' };
export const MATRIX_STATUS: Record<string, string> = { DRAFT: 'Черновик', APPROVED: 'Утверждена', ARCHIVED: 'Архив' };
export const EMPLOYMENT: Record<string, string> = { ACTIVE: 'Работает', TERMINATED: 'Уволен', LEAVE: 'Отпуск', TRANSFERRED: 'Переведён' };
export const EXC_STATUS: Record<string, string> = { ACTIVE: 'Действует', EXPIRED: 'Истекло', PENDING: 'Ещё не началось', DRAFT: 'Черновик', REVOKED: 'Отозвано', APPROVED: 'Согласовано' };
export const CHANGE: Record<string, string> = {
  ADDED: 'Новые назначения', REMOVED: 'Удалённые назначения', UNCHANGED: 'Без изменений', CHANGED: 'Изменены атрибуты',
  NEW_FINDING: 'Новые нарушения', RESOLVED: 'Устранённые нарушения', PERSISTING: 'Сохраняющиеся нарушения', AMBIGUOUS: 'Неоднозначные сравнения',
};
export const APP_ROLES: Record<string, string> = {
  SYS_ADMIN: 'Системный администратор', MATRIX_ADMIN: 'Администратор матрицы', AUDITOR: 'Аудитор ИБ', SYSTEM_OWNER: 'Владелец системы', VIEWER: 'Наблюдатель / Руководитель',
};
export const ENTITY_TYPE: Record<string, string> = { SYSTEM: 'Система', ROLE: 'Роль', MODULE: 'Модуль', OPERATION: 'Операция', EMPLOYEE: 'Сотрудник' };
export const ATTR: Record<string, string> = { department: 'подразделение', position: 'должность', employment_status: 'статус', assigned_at: 'дата назначения', result_status: 'результат' };

export const fmtDate = (s?: string | null) => (s ? (s.length === 10 ? s.split('-').reverse().join('.') : new Date(s).toLocaleDateString('ru-RU')) : '—');
export const fmtDateTime = (s?: string | null) => (s ? new Date(s).toLocaleString('ru-RU') : '—');
export const fmtNum = (n?: number | null) => (n ?? 0).toLocaleString('ru-RU');
