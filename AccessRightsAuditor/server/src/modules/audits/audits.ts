import fs from 'node:fs';
import path from 'node:path';
import { Request, Router } from 'express';
import { z } from 'zod';
import { bulkInsert, one, q, tx } from '../../common/db';
import { badRequest, conflict, forbidden, notFound, parse, zDate, zId, zOptId, zOptText, zText } from '../../common/http';
import { logActivity } from '../../common/activity';
import { canonicalJson, sha256 } from '../../common/hash';
import { can, requirePerm, scopedSystemIds } from '../auth/auth';
import { canonicalResult, runEngine } from '../../rules-core/engine';
import { buildEngineInput, captureRulesSnapshot, RulesSnapshot } from './engine-input';
import { matrixChecksum } from '../access-matrix/matrix';
import { config } from '../../config';

export const auditsRouter = Router();

const AUDIT_SELECT = `
  SELECT a.*, mv.version AS matrix_version, mv.name AS matrix_name, mv.checksum AS matrix_version_checksum,
         cu.full_name AS created_by_name, su.full_name AS started_by_name,
         (SELECT count(*) FROM import_batches b WHERE b.audit_id = a.id) AS batches_count,
         (SELECT count(*) FROM access_snapshots s WHERE s.audit_id = a.id) AS snapshots_count
    FROM audit_runs a LEFT JOIN matrix_versions mv ON mv.id = a.matrix_version_id
    LEFT JOIN users cu ON cu.id = a.created_by LEFT JOIN users su ON su.id = a.started_by`;

export async function getAudit(id: string) {
  const a = await one(`${AUDIT_SELECT} WHERE a.id = $1`, [id]);
  if (!a) throw notFound('Аудит не найден');
  return a;
}

/** Утверждённая версия матрицы, действующая на дату. */
export async function matrixVersionForDate(date: string) {
  return one(`SELECT * FROM matrix_versions WHERE status IN ('APPROVED','ARCHIVED') AND valid_from <= $1 AND (valid_to IS NULL OR valid_to >= $1)
              ORDER BY (status = 'APPROVED') DESC, valid_from DESC, approved_at DESC LIMIT 1`, [date]);
}

auditsRouter.get('/', requirePerm('audit.view'), async (_req, res) => {
  res.json(await q(`${AUDIT_SELECT} ORDER BY a.created_at DESC LIMIT 500`));
});

auditsRouter.get('/matrix-for-date', requirePerm('audit.view'), async (req, res) => {
  res.json(await matrixVersionForDate(parse(zDate, req.query.date)));
});

const auditSchema = z.object({ name: zText, description: zOptText, as_of_date: zDate, matrix_version_id: zOptId });

auditsRouter.post('/', requirePerm('audit.create'), async (req, res) => {
  const b = parse(auditSchema, req.body);
  const mv = b.matrix_version_id ? await one('SELECT * FROM matrix_versions WHERE id = $1', [b.matrix_version_id]) : await matrixVersionForDate(b.as_of_date);
  const a = await one(`INSERT INTO audit_runs (name, description, as_of_date, matrix_version_id, created_by) VALUES ($1,$2,$3,$4,$5) RETURNING id`,
    [b.name, b.description, b.as_of_date, mv?.id ?? null, req.user!.id]);
  await logActivity(req, 'AUDIT_CREATED', { category: 'AUDIT', entityType: 'audit', entityId: a.id, after: { ...b, matrix_version_id: mv?.id ?? null } });
  res.status(201).json(await getAudit(a.id));
});

auditsRouter.get('/:id', requirePerm('audit.view'), async (req, res) => {
  res.json(await getAudit(parse(zId, req.params.id)));
});

auditsRouter.put('/:id', requirePerm('audit.create'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const b = parse(auditSchema, req.body);
  const a = await getAudit(id);
  if (a.status === 'COMPLETED' || a.status === 'RUNNING') throw conflict('Параметры выполненного аудита изменять нельзя');
  await q('UPDATE audit_runs SET name=$2, description=$3, as_of_date=$4, matrix_version_id=$5 WHERE id=$1', [id, b.name, b.description, b.as_of_date, b.matrix_version_id]);
  await logActivity(req, 'AUDIT_UPDATED', { category: 'AUDIT', entityType: 'audit', entityId: id, before: a, after: b });
  res.json(await getAudit(id));
});

auditsRouter.delete('/:id', requirePerm('audit.create'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const a = await getAudit(id);
  if (a.status === 'COMPLETED' || a.status === 'RUNNING') throw conflict('Выполненный аудит является неизменяемым снимком и не удаляется');
  await tx(async (c) => {
    await c.query('DELETE FROM audit_findings WHERE audit_id = $1', [id]);
    await c.query('DELETE FROM access_snapshots WHERE audit_id = $1', [id]);
    await c.query('DELETE FROM import_rows WHERE batch_id IN (SELECT id FROM import_batches WHERE audit_id = $1)', [id]);
    await c.query('DELETE FROM import_batches WHERE audit_id = $1', [id]);
    await c.query('DELETE FROM audit_runs WHERE id = $1', [id]);
    await logActivity(req, 'AUDIT_DELETED', { category: 'AUDIT', entityType: 'audit', entityId: id, before: { name: a.name, as_of_date: a.as_of_date } }, c);
  });
  fs.rmSync(path.join(config.dataDir, 'imports', id), { recursive: true, force: true });
  res.json({ ok: true });
});

// ---------- Запуск аудита ----------
auditsRouter.post('/:id/run', requirePerm('audit.run'), async (req, res) => {
  const id = parse(zId, req.params.id);
  await executeAudit(req, id, req.user!.id);
  res.json(await getAudit(id));
});

/** Выполнение аудита: снимок версии правил → Rule Engine → неизменяемый снимок результатов. */
export async function executeAudit(req: Request | null, id: string, actorId: string) {
  const audit = await getAudit(id);
  if (audit.status === 'COMPLETED') throw conflict('Аудит уже выполнен. Результаты неизменяемы — используйте проверку воспроизводимости или создайте новый аудит');
  if (audit.status === 'RUNNING') throw conflict('Аудит уже выполняется');
  if (!audit.matrix_version_id) throw badRequest('Не выбрана версия матрицы полномочий');
  const mv = await one('SELECT * FROM matrix_versions WHERE id = $1', [audit.matrix_version_id]);
  if (!mv || mv.status === 'DRAFT') throw badRequest('Для аудита можно использовать только утверждённую версию матрицы');
  const batches = await q('SELECT * FROM import_batches WHERE audit_id = $1 ORDER BY sha256', [id]);
  if (!batches.length) throw badRequest('В аудит не загружено ни одного файла');
  const unprocessed = batches.filter((b) => b.status === 'UPLOADED');
  if (unprocessed.length) throw badRequest(`Не обработаны файлы: ${unprocessed.map((b) => b.file_name).join(', ')}. Выполните сопоставление колонок`);

  const started = Date.now();
  await q(`UPDATE audit_runs SET status='RUNNING', started_by=$2, started_at=now(), error_text=NULL WHERE id=$1`, [id, actorId]);
  try {
    const result = await tx(async (c) => {
      const snap = await captureRulesSnapshot(id, c);
      const input = await buildEngineInput({ id, as_of_date: audit.as_of_date, matrix_version_id: audit.matrix_version_id }, snap, c);
      const out = runEngine(input);
      await c.query('DELETE FROM audit_findings WHERE audit_id = $1', [id]);
      await bulkInsert(c, 'audit_findings',
        ['audit_id', 'snapshot_id', 'employee_id', 'system_id', 'rule_code', 'finding_type', 'severity', 'outcome', 'expected', 'actual', 'explanation', 'details', 'exception_id', 'finding_key'],
        out.findings.map((f) => [id, f.snapshotId, f.employeeId, f.systemId, f.ruleCode, f.findingType, f.severity, f.outcome, f.expected, f.actual, f.explanation, JSON.stringify(f.details), f.exceptionId, f.findingKey]));
      const ids = [...out.rowResults.keys()];
      for (let i = 0; i < ids.length; i += 20000) {
        const part = ids.slice(i, i + 20000);
        await c.query(`UPDATE access_snapshots s SET result_status = v.st FROM unnest($1::uuid[], $2::text[]) AS v(id, st) WHERE s.id = v.id`, [part, part.map((x) => out.rowResults.get(x))]);
      }
      const rulesChecksum = sha256(canonicalJson(snap));
      const packageChecksum = sha256(batches.map((b) => b.sha256).join(','));
      const resultChecksum = sha256(canonicalResult(input, out));
      const mChecksum = mv.checksum ?? (await matrixChecksum(mv.id, c));
      const summary = { ...out.summary, durationMs: Date.now() - started, files: batches.map((b) => ({ name: b.file_name, sha256: b.sha256, rows: b.total_rows })) };
      await c.query(`UPDATE audit_runs SET status='COMPLETED', completed_at=now(), rules_snapshot=$2, rules_checksum=$3, package_checksum=$4, result_checksum=$5, matrix_checksum=$6, summary=$7 WHERE id=$1`,
        [id, JSON.stringify(snap), rulesChecksum, packageChecksum, resultChecksum, mChecksum, JSON.stringify(summary)]);
      return { summary, resultChecksum };
    });
    await logActivity(req, 'AUDIT_COMPLETED', { category: 'AUDIT', entityType: 'audit', entityId: id, actorId, after: { findings: result.summary.findings, resultChecksum: result.resultChecksum, ms: Date.now() - started } });
    return result;
  } catch (e: any) {
    await q(`UPDATE audit_runs SET status='FAILED', error_text=$2 WHERE id=$1`, [id, String(e?.message ?? e).slice(0, 2000)]);
    await logActivity(req, 'AUDIT_FAILED', { category: 'AUDIT', entityType: 'audit', entityId: id, actorId, after: { error: String(e?.message ?? e).slice(0, 500) } });
    throw e;
  }
}

/** Повторный расчёт по сохранённому снимку и версии правил — без записи; сравнение контрольных сумм. */
auditsRouter.post('/:id/verify', requirePerm('audit.view'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const audit = await getAudit(id);
  if (audit.status !== 'COMPLETED') throw badRequest('Проверка воспроизводимости доступна только для выполненного аудита');
  const snap = audit.rules_snapshot as RulesSnapshot;
  const input = await buildEngineInput({ id, as_of_date: audit.as_of_date, matrix_version_id: audit.matrix_version_id }, snap);
  const checksum = sha256(canonicalResult(input, runEngine(input)));
  const rulesOk = sha256(canonicalJson(snap)) === audit.rules_checksum;
  const matrixOk = (await matrixChecksum(audit.matrix_version_id)) === audit.matrix_checksum;
  const batches = await q('SELECT sha256 FROM import_batches WHERE audit_id = $1 ORDER BY sha256', [id]);
  const packageOk = sha256(batches.map((b) => b.sha256).join(',')) === audit.package_checksum;
  const reproducible = checksum === audit.result_checksum;
  await logActivity(req, 'AUDIT_VERIFIED', { category: 'AUDIT', entityType: 'audit', entityId: id, after: { reproducible, rulesOk, matrixOk, packageOk } });
  res.json({ reproducible, resultChecksum: checksum, storedChecksum: audit.result_checksum, rulesOk, matrixOk, packageOk });
});

// ---------- Результаты ----------
export interface FindingFilters {
  system_id?: string; department_id?: string; position_id?: string; severity?: string; finding_type?: string; outcome?: string;
  status?: string; owner_user_id?: string; search?: string;
}

export async function findingsWhere(req: Request, auditId: string, f: FindingFilters) {
  const params: unknown[] = [auditId];
  const where = ['f.audit_id = $1'];
  const add = (cond: (n: number) => string, v: unknown) => { params.push(v); where.push(cond(params.length)); };
  const scope = await scopedSystemIds(req);
  if (scope) add((n) => `f.system_id = ANY($${n})`, scope);
  if (f.system_id) add((n) => `f.system_id = $${n}`, f.system_id);
  if (f.department_id) add((n) => `e.department_id = $${n}`, f.department_id);
  if (f.position_id) add((n) => `e.position_id = $${n}`, f.position_id);
  if (f.severity) add((n) => `f.severity = ANY(string_to_array($${n}, ','))`, f.severity);
  if (f.finding_type) add((n) => `f.finding_type = ANY(string_to_array($${n}, ','))`, f.finding_type);
  if (f.outcome) add((n) => `f.outcome = ANY(string_to_array($${n}, ','))`, f.outcome);
  if (f.status) add((n) => `f.status = ANY(string_to_array($${n}, ','))`, f.status);
  if (f.owner_user_id) add((n) => `sy.owner_user_id = $${n}`, f.owner_user_id);
  if (f.search) add((n) => `(e.full_name ILIKE $${n} OR e.employee_key ILIKE $${n} OR f.explanation ILIKE $${n} OR s.login ILIKE $${n})`, `%${f.search}%`);
  return { where: where.join(' AND '), params };
}

export const FINDINGS_FROM = `
  FROM audit_findings f
  LEFT JOIN access_snapshots s ON s.id = f.snapshot_id
  LEFT JOIN employees e ON e.id = f.employee_id
  LEFT JOIN departments d ON d.id = e.department_id
  LEFT JOIN positions p ON p.id = e.position_id
  LEFT JOIN systems sy ON sy.id = f.system_id
  LEFT JOIN users ow ON ow.id = sy.owner_user_id
  LEFT JOIN access_roles ar ON ar.id = s.role_id
  LEFT JOIN operations o ON o.id = s.operation_id`;

export const FINDINGS_COLUMNS = `
  f.id, f.rule_code, f.finding_type, f.severity, f.outcome, f.status, f.expected, f.actual, f.explanation, f.exception_id, f.finding_key, f.snapshot_id,
  e.employee_key, COALESCE(e.full_name, s.full_name_raw) AS employee_name, d.name AS department_name, p.name AS position_name,
  sy.code AS system_code, sy.name AS system_name, ow.full_name AS owner_name, s.login, COALESCE(ar.role_code, s.role_raw) AS role_code,
  COALESCE(o.code, s.operation_raw) AS operation_code, o.name AS operation_name, s.employee_key_raw`;

const SEVERITY_ORDER = `CASE f.severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END`;

auditsRouter.get('/:id/findings', requirePerm('findings.view'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const { where, params } = await findingsWhere(req, id, req.query as FindingFilters);
  const limit = Math.min(Number(req.query.limit) || 100, 1000);
  const offset = Number(req.query.offset) || 0;
  const [rows, total, facets] = await Promise.all([
    q(`SELECT ${FINDINGS_COLUMNS} ${FINDINGS_FROM} WHERE ${where} ORDER BY ${SEVERITY_ORDER}, f.finding_type, e.full_name NULLS LAST, f.finding_key LIMIT ${limit} OFFSET ${offset}`, params),
    one(`SELECT count(*)::int AS n ${FINDINGS_FROM} WHERE ${where}`, params),
    q(`SELECT f.severity, f.finding_type, count(*)::int AS n ${FINDINGS_FROM} WHERE ${where} GROUP BY 1, 2`, params),
  ]);
  res.json({ rows, total: total.n, facets });
});

auditsRouter.get('/:id/snapshots', requirePerm('findings.view'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const params: unknown[] = [id];
  const where = ['s.audit_id = $1'];
  const scope = await scopedSystemIds(req);
  if (scope) { params.push(scope); where.push(`s.system_id = ANY($${params.length})`); }
  if (req.query.result_status) { params.push(req.query.result_status); where.push(`s.result_status = $${params.length}`); }
  if (req.query.system_id) { params.push(req.query.system_id); where.push(`s.system_id = $${params.length}`); }
  if (req.query.search) { params.push(`%${req.query.search}%`); where.push(`(e.full_name ILIKE $${params.length} OR s.employee_key_raw ILIKE $${params.length} OR s.login ILIKE $${params.length} OR s.role_raw ILIKE $${params.length} OR s.operation_raw ILIKE $${params.length})`); }
  const limit = Math.min(Number(req.query.limit) || 100, 1000);
  const offset = Number(req.query.offset) || 0;
  const from = `FROM access_snapshots s LEFT JOIN employees e ON e.id = s.employee_id LEFT JOIN systems sy ON sy.id = s.system_id
                LEFT JOIN access_roles ar ON ar.id = s.role_id LEFT JOIN modules m ON m.id = s.module_id LEFT JOIN operations o ON o.id = s.operation_id
                LEFT JOIN import_rows ir ON ir.id = s.source_row_id LEFT JOIN import_batches b ON b.id = s.batch_id`;
  const [rows, total, by] = await Promise.all([
    q(`SELECT s.id, s.login, s.assigned_at, s.normalized_status, s.review_reason, s.result_status, s.expanded_from_role, s.access_key,
              COALESCE(e.employee_key, s.employee_key_raw) AS employee_key, COALESCE(e.full_name, s.full_name_raw) AS employee_name,
              COALESCE(sy.code, s.system_raw) AS system_code, COALESCE(ar.role_code, s.role_raw) AS role_code, ar.role_name,
              COALESCE(m.code, s.module_raw) AS module_code, COALESCE(o.code, s.operation_raw) AS operation_code, o.name AS operation_name,
              ir.row_number, b.file_name
         ${from} WHERE ${where.join(' AND ')} ORDER BY s.access_key LIMIT ${limit} OFFSET ${offset}`, params),
    one(`SELECT count(*)::int AS n ${from} WHERE ${where.join(' AND ')}`, params),
    q(`SELECT s.result_status, count(*)::int AS n ${from} WHERE ${where.join(' AND ')} GROUP BY 1`, params),
  ]);
  res.json({ rows, total: total.n, byResult: by });
});

auditsRouter.get('/:id/import-errors', requirePerm('audit.view'), async (req, res) => {
  const id = parse(zId, req.params.id);
  res.json(await q(`SELECT r.id, b.file_name, r.sheet_name, r.row_number, r.normalized_status, r.error_text, r.error_column, r.raw_json
                      FROM import_rows r JOIN import_batches b ON b.id = r.batch_id
                     WHERE b.audit_id = $1 AND r.normalized_status <> 'OK' ORDER BY b.file_name, r.row_number LIMIT 10000`, [id]));
});

// ---------- Карточка находки, статус и комментарии ----------
export const findingsRouter = Router();

async function loadFindingChecked(req: Request, id: string) {
  const f = await one(`SELECT f.*, ${FINDINGS_COLUMNS.replace(/f\.id, /, '')} ${FINDINGS_FROM} WHERE f.id = $1`, [id]);
  if (!f) throw notFound('Находка не найдена');
  const scope = await scopedSystemIds(req);
  if (scope && !scope.includes(f.system_id)) throw forbidden('Находка относится к системе, владельцем которой вы не являетесь');
  return f;
}

findingsRouter.get('/:id', requirePerm('findings.view'), async (req, res) => {
  const f = await loadFindingChecked(req, parse(zId, req.params.id));
  const [snapshot, comments, exception, rules] = await Promise.all([
    f.snapshot_id ? one(`SELECT s.*, ir.raw_json, ir.row_number, ir.sheet_name, b.file_name, b.sha256 FROM access_snapshots s
                          JOIN import_rows ir ON ir.id = s.source_row_id JOIN import_batches b ON b.id = s.batch_id WHERE s.id = $1`, [f.snapshot_id]) : null,
    q(`SELECT c.*, u.full_name AS author_name FROM finding_comments c JOIN users u ON u.id = c.author_id WHERE c.finding_id = $1 ORDER BY c.created_at`, [f.id]),
    f.exception_id ? one('SELECT * FROM exceptions WHERE id = $1', [f.exception_id]) : null,
    f.details?.matrixRuleIds?.length
      ? q(`SELECT r.id, r.effect, r.source_ref, r.owner, r.valid_from, r.valid_to, ar.role_code, o.code AS operation_code, d.name AS department_name, p.name AS position_name
             FROM matrix_rules r LEFT JOIN access_roles ar ON ar.id = r.role_id LEFT JOIN operations o ON o.id = r.operation_id
             LEFT JOIN departments d ON d.id = r.department_id LEFT JOIN positions p ON p.id = r.position_id WHERE r.id = ANY($1)`, [f.details.matrixRuleIds])
      : [],
  ]);
  res.json({ finding: f, snapshot, comments, exception, matrixRules: rules });
});

const STATUSES = ['OPEN', 'CONFIRMED', 'DISPUTED', 'ACCEPTED_RISK', 'REMEDIATION', 'CLOSED'] as const;
findingsRouter.post('/:id/comments', requirePerm('findings.comment', 'findings.edit'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const b = parse(z.object({ text: z.string().trim().min(1, 'введите комментарий').max(4000), status: z.enum(STATUSES).optional() }), req.body);
  const f = await loadFindingChecked(req, id);
  if (b.status && b.status !== f.status) {
    const ownerAllowed = ['CONFIRMED', 'DISPUTED'];
    if (!can(req, 'findings.edit') && !ownerAllowed.includes(b.status)) throw forbidden('Владелец системы может только подтвердить или оспорить замечание');
  }
  await tx(async (c) => {
    await c.query('INSERT INTO finding_comments (finding_id, author_id, text, new_status) VALUES ($1,$2,$3,$4)', [id, req.user!.id, b.text, b.status && b.status !== f.status ? b.status : null]);
    if (b.status && b.status !== f.status) {
      await c.query('UPDATE audit_findings SET status=$2, status_changed_by=$3, status_changed_at=now() WHERE id=$1', [id, b.status, req.user!.id]);
    }
    await logActivity(req, 'FINDING_COMMENTED', { category: 'AUDIT', entityType: 'finding', entityId: id, before: { status: f.status }, after: b }, c);
  });
  res.json({ ok: true });
});
