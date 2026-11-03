import { describe, expect, it } from 'vitest';
import { canonicalResult, runEngine } from '../src/rules-core/engine';
import { EngineAccess, EngineEmployee, EngineInput, EngineMatrixRule } from '../src/rules-core/types';

const names = () => ({
  system: new Map([['SYS', 'Smart Bank'], ['SYS2', 'NCI']]),
  role: new Map([['R_OPER', 'Операционист'], ['R_CTRL', 'Контролёр'], ['R_ADM', 'Администратор']]),
  module: new Map([['M_PAY', 'Платежи']]),
  operation: new Map([['OP_CREATE', 'Создать платёж'], ['OP_APPROVE', 'Утвердить платёж'], ['OP_VIEW', 'Просмотр'], ['OP_DELETE', 'Удалить платёж']]),
  department: new Map([['D1', 'Операционный отдел'], ['D2', 'Казначейство']]),
  position: new Map([['P1', 'Операционист'], ['P2', 'Контролёр']]),
});

const emp = (id: string, over: Partial<EngineEmployee> = {}): EngineEmployee => ({
  id, key: `T-${id}`, fullName: `Сотрудник ${id}`, departmentId: 'D1', positionId: 'P1', status: 'ACTIVE',
  validFrom: '2020-01-01', validTo: null, previousDepartmentId: null, previousPositionId: null, transferredAt: null, ...over,
});

let seq = 0;
const acc = (employeeId: string | null, roleId: string, operationId: string | null, over: Partial<EngineAccess> = {}): EngineAccess => ({
  id: `a${++seq}`, accessKey: `${employeeId}|SYS|${roleId}|${operationId}|${seq}`, employeeId, systemId: 'SYS', roleId,
  moduleId: operationId ? 'M_PAY' : null, operationId, login: 'u', assignedAt: '2024-01-01', normalizedStatus: 'OK', reviewReason: null,
  raw: { employeeKey: employeeId, fullName: null, system: 'SYS', role: roleId, module: null, operation: operationId }, ...over,
});

const rule = (over: Partial<EngineMatrixRule>): EngineMatrixRule => ({
  id: `r-${Math.random().toString(36).slice(2)}`, systemId: 'SYS', departmentId: 'D1', positionId: 'P1', roleId: 'R_OPER', moduleId: null,
  operationId: null, effect: 'ALLOW', severity: null, sourceRef: 'Приказ 1', validFrom: '2020-01-01', validTo: null, status: 'ACTIVE', ...over,
});

const baseInput = (over: Partial<EngineInput>): EngineInput => ({
  asOfDate: '2025-06-30',
  employees: [emp('E1')],
  accesses: [],
  matrixRules: [
    rule({ id: 'r1' }),
    rule({ id: 'r2', roleId: 'R_CTRL', positionId: 'P2' }),
  ],
  operations: [
    { id: 'OP_CREATE', moduleId: 'M_PAY', riskLevel: 'MEDIUM' },
    { id: 'OP_VIEW', moduleId: 'M_PAY', riskLevel: 'LOW' },
    { id: 'OP_APPROVE', moduleId: 'M_PAY', riskLevel: 'HIGH' },
    { id: 'OP_DELETE', moduleId: 'M_PAY', riskLevel: 'CRITICAL' },
  ],
  roleComposition: new Map([['R_OPER', new Set(['OP_CREATE', 'OP_VIEW'])], ['R_CTRL', new Set(['OP_APPROVE', 'OP_VIEW'])]]),
  exceptions: [],
  sodRules: [],
  policy: {},
  names: names(),
  ...over,
});

describe('rules-core engine', () => {
  it('разрешённое назначение — соответствует', () => {
    const a = acc('E1', 'R_OPER', 'OP_CREATE');
    const r = runEngine(baseInput({ accesses: [a] }));
    expect(r.findings).toHaveLength(0);
    expect(r.rowResults.get(a.id)).toBe('COMPLIANT');
  });

  it('лишняя операция внутри разрешённой роли выявляется отдельно от лишней роли', () => {
    const extraOp = acc('E1', 'R_OPER', 'OP_APPROVE');
    const extraRole = acc('E1', 'R_CTRL', 'OP_APPROVE');
    const r = runEngine(baseInput({ accesses: [extraOp, extraRole] }));
    const types = Object.fromEntries(r.findings.map((f) => [f.snapshotId, f.findingType]));
    expect(types[extraOp.id]).toBe('EXCESS_OPERATION');
    expect(types[extraRole.id]).toBe('ROLE_NOT_ALLOWED');
    // эскалация по риску операции (HIGH)
    expect(r.findings.find((f) => f.snapshotId === extraOp.id)!.severity).toBe('HIGH');
  });

  it('уволенный сотрудник с доступом — отдельная категория, критично', () => {
    const a = acc('E2', 'R_OPER', 'OP_CREATE');
    const r = runEngine(baseInput({ employees: [emp('E2', { status: 'TERMINATED', validTo: '2025-03-01' })], accesses: [a] }));
    expect(r.findings).toHaveLength(1);
    expect(r.findings[0].findingType).toBe('TERMINATED_USER_ACCESS');
    expect(r.findings[0].severity).toBe('CRITICAL');
    expect(r.summary.terminatedWithAccess).toBe(1);
  });

  it('несопоставленный сотрудник — требует проверки, без вывода о нарушении', () => {
    const a = acc(null, 'R_OPER', 'OP_CREATE', { normalizedStatus: 'NEEDS_REVIEW' });
    const r = runEngine(baseInput({ accesses: [a] }));
    expect(r.findings[0].findingType).toBe('IDENTITY_UNRESOLVED');
    expect(r.findings[0].outcome).toBe('NEEDS_REVIEW');
    expect(r.rowResults.get(a.id)).toBe('NEEDS_REVIEW');
  });

  it('действующее исключение покрывает нарушение, истёкшее — нет', () => {
    const a = acc('E1', 'R_OPER', 'OP_APPROVE');
    const exc = { id: 'x1', employeeId: 'E1', systemId: 'SYS', roleId: null, operationId: 'OP_APPROVE', ticketRef: 'REQ-1', approvedBy: 'Владелец', validFrom: '2025-01-01', validTo: '2025-12-31', status: 'APPROVED' as const, compensatingControl: 'Двойной контроль' };
    const covered = runEngine(baseInput({ accesses: [a], exceptions: [exc] }));
    expect(covered.findings[0].outcome).toBe('COVERED_BY_EXCEPTION');
    expect(covered.findings[0].findingType).toBe('EXCESS_OPERATION'); // факт превышения сохраняется
    expect(covered.rowResults.get(a.id)).toBe('COVERED_BY_EXCEPTION');

    const expired = runEngine(baseInput({ accesses: [a], exceptions: [{ ...exc, validTo: '2025-05-31' }] }));
    expect(expired.findings[0].outcome).toBe('EXCEPTION_EXPIRED');
    expect(expired.rowResults.get(a.id)).toBe('VIOLATION');
    expect(expired.summary.expiredExceptionsMatched).toBe(1);
  });

  it('SoD-правило с двумя конфликтующими операциями срабатывает и показывает обе стороны', () => {
    const a1 = acc('E1', 'R_OPER', 'OP_CREATE');
    const a2 = acc('E1', 'R_OPER', 'OP_APPROVE');
    const r = runEngine(baseInput({
      accesses: [a1, a2],
      sodRules: [{
        id: 's1', code: 'SOD-PAY', name: 'Создание и утверждение платежа', severity: 'CRITICAL', scope: 'EMPLOYEE', justification: '4 глаза',
        validFrom: '2020-01-01', validTo: null, status: 'ACTIVE', compensatingControl: null, compensatingApprovedBy: null,
        items: [{ side: 1, itemType: 'OPERATION', operationId: 'OP_CREATE', roleId: null }, { side: 2, itemType: 'OPERATION', operationId: 'OP_APPROVE', roleId: null }],
      }],
    }));
    const sod = r.findings.find((f) => f.findingType === 'SOD_CONFLICT')!;
    expect(sod).toBeTruthy();
    expect(sod.severity).toBe('CRITICAL');
    const sides = (sod.details as { sides: Array<{ assignments: Array<{ snapshotId: string }> }> }).sides;
    expect(sides[0].assignments[0].snapshotId).toBe(a1.id);
    expect(sides[1].assignments[0].snapshotId).toBe(a2.id);
  });

  it('компенсирующий контроль отличается от жёсткого конфликта', () => {
    const r = runEngine(baseInput({
      accesses: [acc('E1', 'R_OPER', 'OP_CREATE'), acc('E1', 'R_OPER', 'OP_APPROVE')],
      sodRules: [{
        id: 's1', code: 'SOD-PAY', name: 'x', severity: 'CRITICAL', scope: 'EMPLOYEE', justification: 'j', validFrom: '2020-01-01', validTo: null,
        status: 'ACTIVE', compensatingControl: 'Ежедневная сверка', compensatingApprovedBy: 'Владелец процесса',
        items: [{ side: 1, itemType: 'OPERATION', operationId: 'OP_CREATE', roleId: null }, { side: 2, itemType: 'OPERATION', operationId: 'OP_APPROVE', roleId: null }],
      }],
    }));
    const sod = r.findings.find((f) => f.findingType.startsWith('SOD'))!;
    expect(sod.findingType).toBe('SOD_CONFLICT_COMPENSATED');
    expect(sod.outcome).toBe('COMPENSATED');
  });

  it('система вне матрицы — требует проверки, а не нарушение', () => {
    const a = acc('E1', 'R_OPER', 'OP_CREATE', { systemId: 'SYS2' });
    const r = runEngine(baseInput({ accesses: [a] }));
    expect(r.findings[0].findingType).toBe('NOT_IN_MATRIX');
    expect(r.findings[0].outcome).toBe('NEEDS_REVIEW');
  });

  it('остаточный доступ после перевода', () => {
    const a = acc('E3', 'R_OPER', 'OP_CREATE', { assignedAt: '2023-01-01' });
    const r = runEngine(baseInput({
      employees: [emp('E3', { positionId: 'P2', previousPositionId: 'P1', transferredAt: '2024-05-01' })],
      accesses: [a],
    }));
    expect(r.findings[0].findingType).toBe('RESIDUAL_AFTER_TRANSFER');
  });

  it('несоответствие области действия (другое подразделение)', () => {
    const a = acc('E4', 'R_OPER', 'OP_CREATE');
    const r = runEngine(baseInput({ employees: [emp('E4', { departmentId: 'D2' })], accesses: [a] }));
    expect(r.findings[0].findingType).toBe('SCOPE_MISMATCH');
  });

  it('правило вне периода действия не применяется', () => {
    const a = acc('E1', 'R_OPER', 'OP_CREATE');
    const r = runEngine(baseInput({ accesses: [a], matrixRules: [rule({ id: 'r1', validTo: '2024-12-31' }), rule({ id: 'r2', roleId: 'R_CTRL' })] }));
    expect(r.findings[0].findingType).toBe('NOT_IN_MATRIX');
  });

  it('явный запрет перекрывает разрешение', () => {
    const a = acc('E1', 'R_OPER', 'OP_CREATE');
    const r = runEngine(baseInput({ accesses: [a], matrixRules: [rule({ id: 'r1' }), rule({ id: 'r9', effect: 'DENY', operationId: 'OP_CREATE', severity: 'CRITICAL' })] }));
    expect(r.findings[0].findingType).toBe('EXPLICITLY_DENIED');
    expect(r.findings[0].severity).toBe('CRITICAL');
  });

  it('повторный запуск на одинаковых данных даёт одинаковый результат', () => {
    const accesses = [acc('E1', 'R_OPER', 'OP_CREATE'), acc('E1', 'R_OPER', 'OP_APPROVE'), acc('E1', 'R_CTRL', 'OP_VIEW')];
    const i1 = baseInput({ accesses });
    const i2 = baseInput({ accesses: [...accesses].reverse() });
    expect(canonicalResult(i1, runEngine(i1))).toBe(canonicalResult(i2, runEngine(i2)));
  });
});
