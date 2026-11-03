import {
  EngineAccess, EngineEmployee, EngineException, EngineFinding, EngineInput, EngineMatrixRule, EngineResult,
  EngineSummary, FindingType, IsoDate, Outcome, ResultStatus, RiskLevel, Severity,
} from './types';

export const RULE_CODES: Record<FindingType, string> = {
  IDENTITY_UNRESOLVED: 'ARA-R01',
  UNKNOWN_REFERENCE: 'ARA-R02',
  TERMINATED_USER_ACCESS: 'ARA-R03',
  NOT_IN_MATRIX: 'ARA-R04',
  EXPLICITLY_DENIED: 'ARA-R05',
  ROLE_NOT_ALLOWED: 'ARA-R06',
  SCOPE_MISMATCH: 'ARA-R07',
  EXCESS_OPERATION: 'ARA-R08',
  RESIDUAL_AFTER_TRANSFER: 'ARA-R09',
  SOD_CONFLICT: 'ARA-SOD',
  SOD_CONFLICT_COMPENSATED: 'ARA-SOD',
};

export const DEFAULT_POLICY: Record<string, Severity> = {
  TERMINATED_USER_ACCESS: 'CRITICAL',
  ROLE_NOT_ALLOWED: 'HIGH',
  EXCESS_OPERATION: 'MEDIUM',
  SCOPE_MISMATCH: 'MEDIUM',
  EXPLICITLY_DENIED: 'HIGH',
  RESIDUAL_AFTER_TRANSFER: 'MEDIUM',
  NOT_IN_MATRIX: 'REVIEW',
  IDENTITY_UNRESOLVED: 'REVIEW',
  UNKNOWN_REFERENCE: 'REVIEW',
  MATRIX_DEVIATION_WITH_EXCEPTION: 'REVIEW',
  SOD_CONFLICT_COMPENSATED: 'REVIEW',
};

const SEVERITY_RANK: Record<Severity, number> = { REVIEW: 0, LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 };

export function maxSeverity(a: Severity, b: Severity): Severity {
  return SEVERITY_RANK[a] >= SEVERITY_RANK[b] ? a : b;
}

export function inPeriod(date: IsoDate, from: IsoDate | null, to: IsoDate | null): boolean {
  if (from && date < from) return false;
  if (to && date > to) return false;
  return true;
}

/** Статус занятости на дату аудита. Дата увольнения (validTo) — последний рабочий день. */
export function employmentStatusAt(e: EngineEmployee, date: IsoDate): 'ACTIVE' | 'TERMINATED' | 'NOT_HIRED' {
  if (e.validTo && date > e.validTo) return 'TERMINATED';
  if (e.status === 'TERMINATED' && !e.validTo) return 'TERMINATED';
  if (e.validFrom && date < e.validFrom) return 'NOT_HIRED';
  return 'ACTIVE';
}

function cmp(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

export function runEngine(input: EngineInput): EngineResult {
  const { asOfDate, names } = input;
  const policy = { ...DEFAULT_POLICY, ...input.policy } as Record<string, Severity> & { escalate_by_operation_risk?: boolean };
  const escalate = input.policy.escalate_by_operation_risk !== false;
  const sev = (key: string): Severity => (policy[key] as Severity) ?? 'MEDIUM';

  const employees = new Map(input.employees.map((e) => [e.id, e]));
  const operations = new Map(input.operations.map((o) => [o.id, o]));

  // Детерминированный порядок обработки.
  const accesses = [...input.accesses].sort((a, b) => cmp(a.accessKey, b.accessKey));
  const activeRules = input.matrixRules
    .filter((r) => r.status === 'ACTIVE' && inPeriod(asOfDate, r.validFrom, r.validTo))
    .sort((a, b) => cmp(a.id, b.id));
  const rulesBySystem = new Map<string, EngineMatrixRule[]>();
  for (const r of activeRules) {
    const list = rulesBySystem.get(r.systemId) ?? [];
    list.push(r);
    rulesBySystem.set(r.systemId, list);
  }
  const exceptions = [...input.exceptions].filter((x) => x.status === 'APPROVED').sort((a, b) => cmp(a.id, b.id));

  const findings: EngineFinding[] = [];
  const rowResults = new Map<string, ResultStatus>();
  const matchedExpired = new Set<string>();

  const label = (map: Map<string, string>, id: string | null, fallback = '—') => (id ? map.get(id) ?? id : fallback);
  const accessLabel = (a: EngineAccess) =>
    [
      `Система: ${label(names.system, a.systemId, a.raw.system ?? '—')}`,
      `Роль: ${label(names.role, a.roleId, a.raw.role ?? '—')}`,
      a.moduleId || a.raw.module ? `Модуль: ${label(names.module, a.moduleId, a.raw.module ?? '—')}` : null,
      a.operationId || a.raw.operation ? `Операция: ${label(names.operation, a.operationId, a.raw.operation ?? '—')}` : null,
      a.login ? `Логин: ${a.login}` : null,
    ].filter(Boolean).join('; ');

  const ruleLabel = (r: EngineMatrixRule) =>
    [
      `роль ${r.roleId ? label(names.role, r.roleId) : 'любая'}`,
      r.moduleId ? `модуль ${label(names.module, r.moduleId)}` : null,
      r.operationId ? `операция ${label(names.operation, r.operationId)}` : r.roleId && input.roleComposition.get(r.roleId)?.size
        ? `операции профиля: ${[...input.roleComposition.get(r.roleId)!].map((o) => label(names.operation, o)).sort().join(', ')}`
        : 'все операции',
      `подразделение ${r.departmentId ? label(names.department, r.departmentId) : 'любое'}`,
      `должность ${r.positionId ? label(names.position, r.positionId) : 'любая'}`,
      `основание ${r.sourceRef}`,
    ].filter(Boolean).join(', ');

  const scopeMatches = (r: EngineMatrixRule, dept: string | null, pos: string | null) =>
    (r.departmentId === null || r.departmentId === dept) && (r.positionId === null || r.positionId === pos);
  const roleMatches = (r: EngineMatrixRule, a: EngineAccess) => r.roleId === null || r.roleId === a.roleId;
  const operationMatches = (r: EngineMatrixRule, a: EngineAccess) => {
    if (a.operationId === null) {
      // Назначение на уровне роли/модуля без атомарной операции.
      return r.operationId === null && (r.moduleId === null || r.moduleId === a.moduleId);
    }
    if (r.operationId !== null) return r.operationId === a.operationId;
    if (r.moduleId !== null) return r.moduleId === (operations.get(a.operationId)?.moduleId ?? a.moduleId);
    if (r.roleId !== null) {
      const comp = input.roleComposition.get(r.roleId);
      if (comp && comp.size > 0) return comp.has(a.operationId);
    }
    return true;
  };

  const opRisk = (a: EngineAccess): RiskLevel | null => (a.operationId ? operations.get(a.operationId)?.riskLevel ?? null : null);

  const findException = (a: EngineAccess): { valid: EngineException | null; expired: EngineException | null } => {
    let valid: EngineException | null = null;
    let expired: EngineException | null = null;
    for (const x of exceptions) {
      if (x.employeeId !== a.employeeId || x.systemId !== a.systemId) continue;
      if (x.roleId !== null && x.roleId !== a.roleId) continue;
      if (x.operationId !== null && x.operationId !== a.operationId) continue;
      if (inPeriod(asOfDate, x.validFrom, x.validTo)) { valid = valid ?? x; }
      else if (x.validTo < asOfDate) {
        const prev = expired as EngineException | null;
        expired = !prev || x.validTo > prev.validTo ? x : prev;
      }
    }
    return { valid, expired };
  };

  const push = (f: Omit<EngineFinding, 'ruleCode'> & { ruleCode?: string }) => {
    findings.push({ ruleCode: RULE_CODES[f.findingType], ...f });
  };

  for (const a of accesses) {
    const rowOutcomes: Outcome[] = [];
    const emp = a.employeeId ? employees.get(a.employeeId) ?? null : null;
    const base = {
      snapshotId: a.id,
      employeeId: a.employeeId,
      systemId: a.systemId,
      actual: accessLabel(a),
      exceptionId: null as string | null,
    };

    // 1. Идентичность.
    if (!emp) {
      push({
        ...base, findingKey: `IDENTITY_UNRESOLVED|${a.accessKey}`, findingType: 'IDENTITY_UNRESOLVED',
        severity: sev('IDENTITY_UNRESOLVED'), outcome: 'NEEDS_REVIEW', expected: 'Сотрудник однозначно сопоставлен по табельному номеру/ID',
        explanation: a.reviewReason ?? `Сотрудник «${a.raw.employeeKey ?? a.raw.fullName ?? '—'}» не найден в кадровом справочнике или найдено несколько совпадений. Вывод о нарушении не делается.`,
        details: { reviewReason: a.reviewReason, raw: a.raw },
      });
      rowResults.set(a.id, 'NEEDS_REVIEW');
      continue;
    }

    // 2. Статус сотрудника на дату аудита.
    const empStatus = employmentStatusAt(emp, asOfDate);
    if (empStatus === 'TERMINATED') {
      push({
        ...base, findingKey: `TERMINATED_USER_ACCESS|${a.accessKey}`, findingType: 'TERMINATED_USER_ACCESS',
        severity: sev('TERMINATED_USER_ACCESS'), outcome: 'VIOLATION', expected: 'Доступ отозван в дату увольнения',
        explanation: `Сотрудник ${emp.fullName} (${emp.key}) уволен${emp.validTo ? ` ${emp.validTo}` : ''}, но на ${asOfDate} сохраняет доступ.`,
        details: { terminationDate: emp.validTo, employeeKey: emp.key },
      });
      rowResults.set(a.id, 'VIOLATION');
      continue;
    }

    // 3. Неизвестные справочные значения — только «Требует проверки».
    if (a.normalizedStatus === 'NEEDS_REVIEW' || !a.systemId || !a.roleId) {
      push({
        ...base, findingKey: `UNKNOWN_REFERENCE|${a.accessKey}`, findingType: 'UNKNOWN_REFERENCE',
        severity: sev('UNKNOWN_REFERENCE'), outcome: 'NEEDS_REVIEW', expected: 'Система, роль, модуль и операция есть в справочниках',
        explanation: a.reviewReason ?? 'Назначение содержит значения, отсутствующие в справочниках. Автоматический вывод о нарушении не делается.',
        details: { reviewReason: a.reviewReason, raw: a.raw },
      });
      rowResults.set(a.id, 'NEEDS_REVIEW');
      continue;
    }
    if (empStatus === 'NOT_HIRED') {
      push({
        ...base, findingKey: `IDENTITY_UNRESOLVED|${a.accessKey}`, findingType: 'IDENTITY_UNRESOLVED',
        severity: sev('IDENTITY_UNRESOLVED'), outcome: 'NEEDS_REVIEW', expected: 'Сотрудник принят на дату аудита',
        explanation: `Дата приёма сотрудника ${emp.fullName} (${emp.validFrom}) позже даты аудита ${asOfDate}.`, details: {},
      });
      rowResults.set(a.id, 'NEEDS_REVIEW');
      continue;
    }

    // 4. Сверка с матрицей.
    const sysRules = rulesBySystem.get(a.systemId) ?? [];
    let type: FindingType | null = null;
    let expected = '';
    let explanation = '';
    let matrixRuleIds: string[] = [];
    let baseSeverity: Severity = 'MEDIUM';

    if (sysRules.length === 0) {
      type = 'NOT_IN_MATRIX';
      expected = 'Система описана в действующей версии матрицы';
      explanation = `Система «${label(names.system, a.systemId)}» не описана в версии матрицы, действующей на ${asOfDate}. Требуется проверка полноты матрицы.`;
    } else {
      const scoped = (r: EngineMatrixRule) => scopeMatches(r, emp.departmentId, emp.positionId);
      const deny = sysRules.filter((r) => r.effect === 'DENY' && scoped(r) && roleMatches(r, a) && operationMatches(r, a));
      const allows = sysRules.filter((r) => r.effect === 'ALLOW');
      const allowFull = allows.filter((r) => scoped(r) && roleMatches(r, a) && operationMatches(r, a));
      if (deny.length) {
        type = 'EXPLICITLY_DENIED';
        matrixRuleIds = deny.map((r) => r.id);
        baseSeverity = deny.reduce<Severity>((s, r) => maxSeverity(s, r.severity ?? sev('EXPLICITLY_DENIED')), 'LOW');
        expected = `Запрещено правилом: ${ruleLabel(deny[0])}`;
        explanation = 'Назначение явно запрещено матрицей для подразделения/должности сотрудника.';
      } else if (allowFull.length === 0) {
        const roleOk = allows.filter((r) => scoped(r) && roleMatches(r, a));
        if (roleOk.length) {
          type = 'EXCESS_OPERATION';
          matrixRuleIds = roleOk.map((r) => r.id);
          expected = `Разрешено: ${roleOk.map(ruleLabel).join(' | ')}`;
          explanation = `Роль «${label(names.role, a.roleId)}» разрешена сотруднику, но операция «${label(names.operation, a.operationId, a.raw.operation ?? '—')}» выходит за разрешённый набор операций роли.`;
        } else {
          const prevScoped = emp.transferredAt && (emp.previousDepartmentId || emp.previousPositionId)
            ? allows.filter((r) => scopeMatches(r, emp.previousDepartmentId ?? emp.departmentId, emp.previousPositionId ?? emp.positionId) && roleMatches(r, a) && operationMatches(r, a))
            : [];
          const assignedBeforeTransfer = !a.assignedAt || !emp.transferredAt || a.assignedAt <= emp.transferredAt;
          const roleAnywhere = allows.filter((r) => r.roleId === a.roleId);
          if (prevScoped.length && assignedBeforeTransfer) {
            type = 'RESIDUAL_AFTER_TRANSFER';
            matrixRuleIds = prevScoped.map((r) => r.id);
            expected = 'Права прежней должности/подразделения отозваны после перевода';
            explanation = `Сотрудник переведён ${emp.transferredAt} из «${label(names.department, emp.previousDepartmentId, label(names.department, emp.departmentId))} / ${label(names.position, emp.previousPositionId, label(names.position, emp.positionId))}». Доступ соответствует прежней должности и не разрешён для текущей — возможный остаточный доступ, требует подтверждения.`;
          } else if (roleAnywhere.length === 0) {
            type = 'NOT_IN_MATRIX';
            expected = 'Роль описана в матрице';
            explanation = `Роль «${label(names.role, a.roleId)}» не упоминается ни в одном разрешающем правиле действующей матрицы. Это не считается доказанным нарушением без проверки полноты матрицы.`;
          } else {
            const samePosition = roleAnywhere.filter((r) => (r.positionId === null || r.positionId === emp.positionId) && r.departmentId !== null && r.departmentId !== emp.departmentId);
            matrixRuleIds = roleAnywhere.map((r) => r.id);
            if (samePosition.length) {
              type = 'SCOPE_MISMATCH';
              expected = `Роль разрешена для: ${samePosition.map(ruleLabel).join(' | ')}`;
              explanation = `Роль «${label(names.role, a.roleId)}» разрешена для должности сотрудника только в другом подразделении (текущее: ${label(names.department, emp.departmentId)}).`;
            } else {
              type = 'ROLE_NOT_ALLOWED';
              expected = `Роль разрешена только для: ${roleAnywhere.map(ruleLabel).join(' | ')}`;
              explanation = `Роль «${label(names.role, a.roleId)}» не разрешена для должности «${label(names.position, emp.positionId)}» в подразделении «${label(names.department, emp.departmentId)}».`;
            }
          }
        }
      }
    }

    if (type) {
      if (type !== 'EXPLICITLY_DENIED') baseSeverity = sev(type);
      const risk = opRisk(a);
      if (escalate && risk && type !== 'NOT_IN_MATRIX' && baseSeverity !== 'REVIEW') baseSeverity = maxSeverity(baseSeverity, risk);

      const { valid, expired } = findException(a);
      let outcome: Outcome = type === 'NOT_IN_MATRIX' ? 'NEEDS_REVIEW' : 'VIOLATION';
      let severity = baseSeverity;
      let exceptionId: string | null = null;
      let excNote = '';
      if (valid) {
        outcome = 'COVERED_BY_EXCEPTION';
        severity = sev('MATRIX_DEVIATION_WITH_EXCEPTION');
        exceptionId = valid.id;
        excNote = ` Нарушение покрыто действующим исключением ${valid.ticketRef} (согласовал: ${valid.approvedBy}, до ${valid.validTo}).`;
      } else if (expired) {
        matchedExpired.add(expired.id);
        if (outcome === 'VIOLATION') outcome = 'EXCEPTION_EXPIRED';
        exceptionId = expired.id;
        excNote = ` Исключение ${expired.ticketRef} истекло ${expired.validTo}.`;
      }
      push({
        ...base, findingKey: `${type}|${a.accessKey}`, findingType: type, severity, outcome, exceptionId,
        expected, explanation: explanation + excNote,
        details: { matrixRuleIds, originalSeverity: baseSeverity, operationRisk: opRisk(a) },
      });
      rowOutcomes.push(outcome);
    }
    rowResults.set(a.id, resultFromOutcomes(rowOutcomes));
  }

  // 5. SoD — групповые проверки по сотруднику (или сотруднику + системе).
  let sodConflicts = 0;
  const sodRules = input.sodRules
    .filter((r) => r.status === 'ACTIVE' && inPeriod(asOfDate, r.validFrom, r.validTo))
    .sort((a, b) => cmp(a.code, b.code));
  if (sodRules.length) {
    const groups = new Map<string, EngineAccess[]>();
    for (const a of accesses) {
      if (!a.employeeId || a.normalizedStatus !== 'OK') continue;
      const list = groups.get(a.employeeId) ?? [];
      list.push(a);
      groups.set(a.employeeId, list);
    }
    const groupKeys = [...groups.keys()].sort((a, b) => cmp(employees.get(a)?.key ?? a, employees.get(b)?.key ?? b));
    for (const empId of groupKeys) {
      const emp = employees.get(empId)!;
      const all = groups.get(empId)!;
      for (const rule of sodRules) {
        const scopes: Array<[string | null, EngineAccess[]]> = rule.scope === 'EMPLOYEE_SYSTEM'
          ? [...new Set(all.map((a) => a.systemId!))].sort().map((s) => [s, all.filter((a) => a.systemId === s)])
          : [[null, all]];
        for (const [scopeSystem, list] of scopes) {
          const sides = [...new Set(rule.items.map((i) => i.side))].sort((x, y) => x - y);
          if (sides.length < 2) continue;
          const sideMatches = sides.map((side) => {
            const items = rule.items.filter((i) => i.side === side);
            const matched = list.filter((a) => items.some((i) =>
              (i.itemType === 'OPERATION' && i.operationId === a.operationId) || (i.itemType === 'ROLE' && i.roleId === a.roleId)));
            return { side, items, matched };
          });
          if (sideMatches.some((s) => s.matched.length === 0)) continue;
          sodConflicts++;
          const compensated = Boolean(rule.compensatingControl && rule.compensatingApprovedBy);
          const sidesDesc = sideMatches.map((s) => ({
            side: s.side,
            capabilities: s.items.map((i) => i.itemType === 'OPERATION' ? `Операция: ${label(names.operation, i.operationId)}` : `Роль: ${label(names.role, i.roleId)}`),
            assignments: s.matched.map((a) => ({ snapshotId: a.id, accessKey: a.accessKey, label: accessLabel(a) })),
          }));
          push({
            snapshotId: null, employeeId: empId, systemId: scopeSystem, exceptionId: null,
            findingKey: `SOD|${rule.code}|${emp.key}${scopeSystem ? `|${scopeSystem}` : ''}`,
            findingType: compensated ? 'SOD_CONFLICT_COMPENSATED' : 'SOD_CONFLICT',
            ruleCode: `SOD-${rule.code}`,
            severity: compensated ? sev('SOD_CONFLICT_COMPENSATED') : rule.severity,
            outcome: compensated ? 'COMPENSATED' : 'VIOLATION',
            expected: `Конфликтующие полномочия не совмещаются: ${sidesDesc.map((s) => s.capabilities.join(' / ')).join('  ×  ')}`,
            actual: sidesDesc.map((s) => `Сторона ${s.side}: ${s.assignments.map((x) => x.label).join('; ')}`).join(' | '),
            explanation: `SoD «${rule.name}» (${rule.code}): у сотрудника ${emp.fullName} (${emp.key}) присутствуют все конфликтующие полномочия. ${rule.justification}` +
              (compensated ? ` Утверждён компенсирующий контроль: ${rule.compensatingControl} (${rule.compensatingApprovedBy}).` : ' Жёсткий конфликт.'),
            details: { sodRuleId: rule.id, sides: sidesDesc, compensatingControl: rule.compensatingControl },
          });
          if (!compensated) {
            for (const s of sideMatches) for (const a of s.matched) rowResults.set(a.id, 'VIOLATION');
          }
        }
      }
    }
  }

  findings.sort((a, b) => cmp(a.findingKey, b.findingKey));

  const expiredTotal = exceptions.filter((x) => x.validTo < asOfDate).length;
  return { findings, rowResults, summary: buildSummary(input, findings, rowResults, sodConflicts, matchedExpired.size, expiredTotal) };
}

function resultFromOutcomes(outcomes: Outcome[]): ResultStatus {
  if (outcomes.some((o) => o === 'VIOLATION' || o === 'EXCEPTION_EXPIRED')) return 'VIOLATION';
  if (outcomes.some((o) => o === 'NEEDS_REVIEW')) return 'NEEDS_REVIEW';
  if (outcomes.some((o) => o === 'COVERED_BY_EXCEPTION')) return 'COVERED_BY_EXCEPTION';
  return 'COMPLIANT';
}

function buildSummary(input: EngineInput, findings: EngineFinding[], rows: Map<string, ResultStatus>, sod: number, expiredMatched: number, expiredTotal: number): EngineSummary {
  const byResult: Record<ResultStatus, number> = { COMPLIANT: 0, VIOLATION: 0, COVERED_BY_EXCEPTION: 0, NEEDS_REVIEW: 0 };
  for (const r of rows.values()) byResult[r]++;
  const bySeverity: Record<Severity, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, REVIEW: 0 };
  const byType: Record<string, number> = {};
  for (const f of findings) {
    bySeverity[f.severity]++;
    byType[f.findingType] = (byType[f.findingType] ?? 0) + 1;
  }
  return {
    asOfDate: input.asOfDate,
    totalAccesses: input.accesses.length,
    byResult, bySeverity, byType,
    findings: findings.length,
    employees: new Set(input.accesses.map((a) => a.employeeId).filter(Boolean)).size,
    terminatedWithAccess: new Set(findings.filter((f) => f.findingType === 'TERMINATED_USER_ACCESS').map((f) => f.employeeId)).size,
    sodConflicts: sod,
    coveredByException: findings.filter((f) => f.outcome === 'COVERED_BY_EXCEPTION').length,
    expiredExceptionsMatched: expiredMatched,
    expiredExceptionsTotal: expiredTotal,
  };
}

/** Канонический вид результатов для контрольной суммы (не зависит от UUID строк). */
export function canonicalResult(input: EngineInput, result: EngineResult): string {
  const keyById = new Map(input.accesses.map((a) => [a.id, a.accessKey]));
  const rows = [...result.rowResults.entries()].map(([id, s]) => `${keyById.get(id)}=${s}`).sort();
  const f = result.findings.map((x) => [x.findingKey, x.ruleCode, x.findingType, x.severity, x.outcome].join('|'));
  return JSON.stringify({ rows, findings: f });
}
