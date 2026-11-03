import { Router } from 'express';
import { z } from 'zod';
import { bulkInsert, one, q, tx } from '../../common/db';
import { badRequest, notFound, parse, zId } from '../../common/http';
import { logActivity } from '../../common/activity';
import { requirePerm } from '../auth/auth';

export const comparisonsRouter = Router();

interface SnapRow {
  access_key: string; employee_id: string | null; employee_key: string | null; employee_name: string | null; normalized_status: string;
  department: string | null; position: string | null; employment_status: string | null; assigned_at: string | null; result_status: string | null;
  system: string | null; role: string | null; module: string | null; operation: string | null; login: string;
}

async function loadSnapshot(auditId: string): Promise<SnapRow[]> {
  // Подразделение/должность/статус берутся из снимка кадровых данных аудита (rules_snapshot), а не из текущего справочника.
  const audit = await one('SELECT rules_snapshot FROM audit_runs WHERE id = $1', [auditId]);
  const emps = new Map<string, any>((audit?.rules_snapshot?.employees ?? []).map((e: any) => [e.id, e]));
  const [rows, deps, poss] = await Promise.all([
    q(`SELECT s.access_key, s.employee_id, e.employee_key, COALESCE(e.full_name, s.full_name_raw) AS employee_name, s.normalized_status, s.assigned_at, s.result_status, s.login,
              COALESCE(sy.code, s.system_raw) AS system, COALESCE(ar.role_code, s.role_raw) AS role, COALESCE(m.code, s.module_raw) AS module, COALESCE(o.code, s.operation_raw) AS operation
         FROM access_snapshots s LEFT JOIN employees e ON e.id = s.employee_id LEFT JOIN systems sy ON sy.id = s.system_id
         LEFT JOIN access_roles ar ON ar.id = s.role_id LEFT JOIN modules m ON m.id = s.module_id LEFT JOIN operations o ON o.id = s.operation_id
        WHERE s.audit_id = $1`, [auditId]),
    q('SELECT id, name FROM departments'), q('SELECT id, name FROM positions'),
  ]);
  const dn = new Map(deps.map((d) => [d.id, d.name]));
  const pn = new Map(poss.map((d) => [d.id, d.name]));
  return rows.map((r) => {
    const e = r.employee_id ? emps.get(r.employee_id) : null;
    return { ...r, department: e ? dn.get(e.departmentId) ?? null : null, position: e ? pn.get(e.positionId) ?? null : null, employment_status: e?.status ?? null, };
  });
}

/** Стабильный ключ: ID сотрудника (канонический табельный номер с учётом алиасов) + система + логин + роль + модуль + операция. */
const stableKey = (r: SnapRow) => r.access_key;
const isAmbiguous = (r: SnapRow) => !r.employee_id || r.access_key.includes('|?');

export async function compareAudits(fromId: string, toId: string) {
  const [before, after] = await Promise.all([loadSnapshot(fromId), loadSnapshot(toId)]);
  const items: Array<{ key: string; type: string; before: unknown; after: unknown }> = [];
  const bMap = new Map<string, SnapRow>();
  const aMap = new Map<string, SnapRow>();
  for (const r of before) (isAmbiguous(r) ? items.push({ key: r.access_key, type: 'AMBIGUOUS', before: r, after: null }) : bMap.set(stableKey(r), r));
  for (const r of after) (isAmbiguous(r) ? items.push({ key: r.access_key, type: 'AMBIGUOUS', before: null, after: r }) : aMap.set(stableKey(r), r));
  const ATTRS: Array<keyof SnapRow> = ['department', 'position', 'employment_status', 'assigned_at', 'result_status'];
  for (const [k, b] of bMap) {
    const a = aMap.get(k);
    if (!a) { items.push({ key: k, type: 'REMOVED', before: b, after: null }); continue; }
    const changed = ATTRS.filter((f) => (b[f] ?? null) !== (a[f] ?? null));
    items.push({ key: k, type: changed.length ? 'CHANGED' : 'UNCHANGED', before: changed.length ? { ...b, changed } : null, after: changed.length ? a : null });
  }
  for (const [k, a] of aMap) if (!bMap.has(k)) items.push({ key: k, type: 'ADDED', before: null, after: a });

  // Изменения находок.
  const fq = `SELECT f.finding_key, f.finding_type, f.severity, f.outcome, f.explanation, e.employee_key, e.full_name FROM audit_findings f LEFT JOIN employees e ON e.id = f.employee_id
               WHERE f.audit_id = $1 AND f.outcome IN ('VIOLATION','EXCEPTION_EXPIRED','NEEDS_REVIEW')`;
  const [fb, fa] = await Promise.all([q(fq, [fromId]), q(fq, [toId])]);
  const fbm = new Map(fb.map((f) => [f.finding_key, f]));
  const fam = new Map(fa.map((f) => [f.finding_key, f]));
  for (const [k, f] of fam) items.push({ key: k, type: fbm.has(k) ? 'PERSISTING' : 'NEW_FINDING', before: fbm.get(k) ?? null, after: f });
  for (const [k, f] of fbm) if (!fam.has(k)) items.push({ key: k, type: 'RESOLVED', before: f, after: null });

  const summary: Record<string, number> = {};
  for (const i of items) summary[i.type] = (summary[i.type] ?? 0) + 1;
  return { items, summary };
}

comparisonsRouter.get('/', requirePerm('audit.view'), async (_req, res) => {
  res.json(await q(`SELECT c.*, fa.name AS from_name, fa.as_of_date AS from_date, ta.name AS to_name, ta.as_of_date AS to_date, u.full_name AS created_by_name
                      FROM audit_comparisons c JOIN audit_runs fa ON fa.id = c.from_audit_id JOIN audit_runs ta ON ta.id = c.to_audit_id
                      LEFT JOIN users u ON u.id = c.created_by ORDER BY c.created_at DESC`));
});

comparisonsRouter.post('/', requirePerm('comparisons.run'), async (req, res) => {
  const b = parse(z.object({ from_audit_id: zId, to_audit_id: zId }), req.body);
  if (b.from_audit_id === b.to_audit_id) throw badRequest('Выберите два разных аудита');
  const audits = await q(`SELECT id, status FROM audit_runs WHERE id = ANY($1)`, [[b.from_audit_id, b.to_audit_id]]);
  if (audits.length !== 2 || audits.some((a) => a.status !== 'COMPLETED')) throw badRequest('Сравнивать можно только выполненные аудиты');
  const { items, summary } = await compareAudits(b.from_audit_id, b.to_audit_id);
  const id = await tx(async (c) => {
    const r = (await c.query('INSERT INTO audit_comparisons (from_audit_id, to_audit_id, created_by, summary) VALUES ($1,$2,$3,$4) RETURNING id',
      [b.from_audit_id, b.to_audit_id, req.user!.id, JSON.stringify(summary)])).rows[0];
    await bulkInsert(c, 'comparison_items', ['comparison_id', 'access_key', 'change_type', 'before_json', 'after_json'],
      items.filter((i) => i.type !== 'UNCHANGED').map((i) => [r.id, i.key, i.type, i.before ? JSON.stringify(i.before) : null, i.after ? JSON.stringify(i.after) : null]));
    await logActivity(req, 'COMPARISON_CREATED', { category: 'AUDIT', entityType: 'comparison', entityId: r.id, after: { ...b, summary } }, c);
    return r.id;
  });
  res.status(201).json({ id, summary });
});

comparisonsRouter.get('/:id', requirePerm('audit.view'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const c = await one(`SELECT c.*, fa.name AS from_name, fa.as_of_date AS from_date, ta.name AS to_name, ta.as_of_date AS to_date
                         FROM audit_comparisons c JOIN audit_runs fa ON fa.id = c.from_audit_id JOIN audit_runs ta ON ta.id = c.to_audit_id WHERE c.id = $1`, [id]);
  if (!c) throw notFound();
  const type = typeof req.query.change_type === 'string' && req.query.change_type ? req.query.change_type : null;
  const items = await q(`SELECT * FROM comparison_items WHERE comparison_id = $1 AND ($2::text IS NULL OR change_type = $2) ORDER BY change_type, access_key LIMIT 5000`, [id, type]);
  res.json({ comparison: c, items });
});
