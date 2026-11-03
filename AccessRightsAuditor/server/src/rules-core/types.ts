// Независимый модуль правил (rules-core): чистые функции без доступа к БД.
// Один и тот же вход (снимок + версия матрицы + версия правил) всегда даёт один и тот же результат.

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'REVIEW';
export type RiskLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type Outcome = 'VIOLATION' | 'COVERED_BY_EXCEPTION' | 'EXCEPTION_EXPIRED' | 'NEEDS_REVIEW' | 'COMPENSATED';
export type ResultStatus = 'COMPLIANT' | 'VIOLATION' | 'COVERED_BY_EXCEPTION' | 'NEEDS_REVIEW';

export type FindingType =
  | 'IDENTITY_UNRESOLVED'
  | 'UNKNOWN_REFERENCE'
  | 'TERMINATED_USER_ACCESS'
  | 'NOT_IN_MATRIX'
  | 'EXPLICITLY_DENIED'
  | 'ROLE_NOT_ALLOWED'
  | 'SCOPE_MISMATCH'
  | 'EXCESS_OPERATION'
  | 'RESIDUAL_AFTER_TRANSFER'
  | 'SOD_CONFLICT'
  | 'SOD_CONFLICT_COMPENSATED';

/** Дата в формате YYYY-MM-DD (бизнес-дата, без времени). Строки сравниваются лексикографически. */
export type IsoDate = string;

export interface EngineEmployee {
  id: string;
  key: string;
  fullName: string;
  departmentId: string | null;
  positionId: string | null;
  status: 'ACTIVE' | 'TERMINATED' | 'LEAVE' | 'TRANSFERRED';
  validFrom: IsoDate | null;
  validTo: IsoDate | null;
  previousDepartmentId: string | null;
  previousPositionId: string | null;
  transferredAt: IsoDate | null;
}

export interface EngineAccess {
  id: string;
  accessKey: string;
  employeeId: string | null;
  systemId: string | null;
  roleId: string | null;
  moduleId: string | null;
  operationId: string | null;
  login: string;
  assignedAt: IsoDate | null;
  normalizedStatus: 'OK' | 'NEEDS_REVIEW';
  reviewReason: string | null;
  raw: { employeeKey: string | null; fullName: string | null; system: string | null; role: string | null; module: string | null; operation: string | null };
}

export interface EngineMatrixRule {
  id: string;
  systemId: string;
  departmentId: string | null;
  positionId: string | null;
  roleId: string | null;
  moduleId: string | null;
  operationId: string | null;
  effect: 'ALLOW' | 'DENY';
  severity: RiskLevel | null;
  sourceRef: string;
  validFrom: IsoDate;
  validTo: IsoDate | null;
  status: 'ACTIVE' | 'INACTIVE';
}

export interface EngineOperation {
  id: string;
  moduleId: string;
  riskLevel: RiskLevel;
}

export interface EngineException {
  id: string;
  employeeId: string;
  systemId: string;
  roleId: string | null;
  operationId: string | null;
  ticketRef: string;
  approvedBy: string;
  validFrom: IsoDate;
  validTo: IsoDate;
  status: 'DRAFT' | 'APPROVED' | 'REVOKED';
  compensatingControl: string;
}

export interface EngineSodItem {
  side: number;
  itemType: 'OPERATION' | 'ROLE';
  operationId: string | null;
  roleId: string | null;
}

export interface EngineSodRule {
  id: string;
  code: string;
  name: string;
  severity: RiskLevel;
  scope: 'EMPLOYEE' | 'EMPLOYEE_SYSTEM';
  justification: string;
  validFrom: IsoDate;
  validTo: IsoDate | null;
  status: 'ACTIVE' | 'INACTIVE';
  compensatingControl: string | null;
  compensatingApprovedBy: string | null;
  items: EngineSodItem[];
}

export type SeverityPolicy = Partial<Record<string, Severity>> & { escalate_by_operation_risk?: boolean };

export interface EngineNames {
  system: Map<string, string>;
  role: Map<string, string>;
  module: Map<string, string>;
  operation: Map<string, string>;
  department: Map<string, string>;
  position: Map<string, string>;
}

export interface EngineInput {
  asOfDate: IsoDate;
  employees: EngineEmployee[];
  accesses: EngineAccess[];
  matrixRules: EngineMatrixRule[];
  operations: EngineOperation[];
  /** roleId -> операции, входящие в стандартный профиль роли */
  roleComposition: Map<string, Set<string>>;
  exceptions: EngineException[];
  sodRules: EngineSodRule[];
  policy: SeverityPolicy;
  names: EngineNames;
}

export interface EngineFinding {
  findingKey: string;
  snapshotId: string | null;
  employeeId: string | null;
  systemId: string | null;
  ruleCode: string;
  findingType: FindingType;
  severity: Severity;
  outcome: Outcome;
  expected: string | null;
  actual: string | null;
  explanation: string;
  exceptionId: string | null;
  details: Record<string, unknown>;
}

export interface EngineResult {
  findings: EngineFinding[];
  rowResults: Map<string, ResultStatus>;
  summary: EngineSummary;
}

export interface EngineSummary {
  asOfDate: IsoDate;
  totalAccesses: number;
  byResult: Record<ResultStatus, number>;
  bySeverity: Record<Severity, number>;
  byType: Record<string, number>;
  findings: number;
  employees: number;
  terminatedWithAccess: number;
  sodConflicts: number;
  coveredByException: number;
  expiredExceptionsMatched: number;
  expiredExceptionsTotal: number;
}
