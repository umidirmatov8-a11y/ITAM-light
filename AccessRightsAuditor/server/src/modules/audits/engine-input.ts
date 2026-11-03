import { Db, q } from '../../common/db';

import { getSettings } from '../../common/settings';
import { EngineInput, EngineSodRule } from '../../rules-core/types';

/** Запросы в одной транзакции (один клиент pg) выполняются строго последовательно. */
async function sequential(thunks: Array<() => Promise<any[]>>): Promise<any[][]> {
  const out: any[][] = [];
  for (const t of thunks) out.push(await t());
  return out;
}

/**
 * «Версия правил» аудита: SoD-правила, политика критичности, исключения, кадровые данные и профили ролей,
 * зафиксированные на момент запуска. Хранится в audit_runs.rules_snapshot, чтобы повторная проверка
 * давала тот же результат, даже если справочники позже изменились.
 */
export interface RulesSnapshot {
  policy: Record<string, any>;
  sodRules: EngineSodRule[];
  exceptions: EngineInput['exceptions'];
  employees: EngineInput['employees'];
  operations: EngineInput['operations'];
  roleComposition: Record<string, string[]>;
}

export async function captureRulesSnapshot(auditId: string, db?: Db): Promise<RulesSnapshot> {
  const settings = await getSettings();
  const [sod, items, exc, emps, ops, comp] = await sequential([
    () => q('SELECT * FROM sod_rules ORDER BY code', [], db),
    () => q('SELECT rule_id, side, item_type, operation_id, role_id FROM sod_rule_items ORDER BY rule_id, side, id', [], db),
    () => q('SELECT * FROM exceptions ORDER BY id', [], db),
    () => q(`SELECT * FROM employees WHERE id IN (SELECT DISTINCT employee_id FROM access_snapshots WHERE audit_id = $1 AND employee_id IS NOT NULL) ORDER BY id`, [auditId], db),
    () => q('SELECT id, module_id, risk_level FROM operations ORDER BY id', [], db),
    () => q('SELECT role_id, operation_id FROM role_operations ORDER BY role_id, operation_id', [], db),
  ]);
  const roleComposition: Record<string, string[]> = {};
  for (const c of comp) (roleComposition[c.role_id] ??= []).push(c.operation_id);
  return {
    policy: settings.severity_policy ?? {},
    sodRules: sod.map((r) => ({
      id: r.id, code: r.code, name: r.name, severity: r.severity, scope: r.scope, justification: r.justification,
      validFrom: r.valid_from, validTo: r.valid_to, status: r.status, compensatingControl: r.compensating_control, compensatingApprovedBy: r.compensating_approved_by,
      items: items.filter((i) => i.rule_id === r.id).map((i) => ({ side: i.side, itemType: i.item_type, operationId: i.operation_id, roleId: i.role_id })),
    })),
    exceptions: exc.map((x) => ({
      id: x.id, employeeId: x.employee_id, systemId: x.system_id, roleId: x.role_id, operationId: x.operation_id, ticketRef: x.ticket_ref,
      approvedBy: x.approved_by, validFrom: x.valid_from, validTo: x.valid_to, status: x.status, compensatingControl: x.compensating_control,
    })),
    employees: emps.map((e) => ({
      id: e.id, key: e.employee_key, fullName: e.full_name, departmentId: e.department_id, positionId: e.position_id, status: e.employment_status,
      validFrom: e.valid_from, validTo: e.valid_to, previousDepartmentId: e.previous_department_id, previousPositionId: e.previous_position_id, transferredAt: e.transferred_at,
    })),
    operations: ops.map((o) => ({ id: o.id, moduleId: o.module_id, riskLevel: o.risk_level })),
    roleComposition,
  };
}

export async function buildEngineInput(audit: { id: string; as_of_date: string; matrix_version_id: string }, snap: RulesSnapshot, db?: Db): Promise<EngineInput> {
  const [accesses, rules, systems, roles, modules, operations, departments, positions] = await sequential([
    () => q('SELECT * FROM access_snapshots WHERE audit_id = $1', [audit.id], db),
    () => q('SELECT * FROM matrix_rules WHERE version_id = $1', [audit.matrix_version_id], db),
    () => q('SELECT id, code, name FROM systems', [], db),
    () => q('SELECT id, role_code, role_name FROM access_roles', [], db),
    () => q('SELECT id, code, name FROM modules', [], db),
    () => q('SELECT id, code, name FROM operations', [], db),
    () => q('SELECT id, code, name FROM departments', [], db),
    () => q('SELECT id, code, name FROM positions', [], db),
  ]);
  return {
    asOfDate: audit.as_of_date,
    employees: snap.employees,
    accesses: accesses.map((a) => ({
      id: a.id, accessKey: a.access_key, employeeId: a.employee_id, systemId: a.system_id, roleId: a.role_id, moduleId: a.module_id, operationId: a.operation_id,
      login: a.login, assignedAt: a.assigned_at, normalizedStatus: a.normalized_status, reviewReason: a.review_reason,
      raw: { employeeKey: a.employee_key_raw, fullName: a.full_name_raw, system: a.system_raw, role: a.role_raw, module: a.module_raw, operation: a.operation_raw },
    })),
    matrixRules: rules.map((r) => ({
      id: r.id, systemId: r.system_id, departmentId: r.department_id, positionId: r.position_id, roleId: r.role_id, moduleId: r.module_id, operationId: r.operation_id,
      effect: r.effect, severity: r.severity, sourceRef: r.source_ref, validFrom: r.valid_from, validTo: r.valid_to, status: r.status,
    })),
    operations: snap.operations,
    roleComposition: new Map(Object.entries(snap.roleComposition).map(([k, v]) => [k, new Set(v)])),
    exceptions: snap.exceptions,
    sodRules: snap.sodRules,
    policy: snap.policy,
    names: {
      system: new Map(systems.map((s) => [s.id, `${s.code} — ${s.name}`])),
      role: new Map(roles.map((s) => [s.id, `${s.role_code} — ${s.role_name}`])),
      module: new Map(modules.map((s) => [s.id, `${s.code} — ${s.name}`])),
      operation: new Map(operations.map((s) => [s.id, `${s.code} — ${s.name}`])),
      department: new Map(departments.map((s) => [s.id, s.name])),
      position: new Map(positions.map((s) => [s.id, s.name])),
    },
  };
}
