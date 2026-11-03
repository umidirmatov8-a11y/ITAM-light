import { Router } from 'express';
import multer from 'multer';
import { z } from 'zod';
import { Db, one, q, tx } from '../../common/db';
import { badRequest, conflict, notFound, parse, zDate, zId, zOptDate, zOptId, zOptText, zRisk, zText } from '../../common/http';
import { logActivity } from '../../common/activity';
import { sha256 } from '../../common/hash';
import { parseDateValue, readTable, readWorkbook } from '../../common/spreadsheet';
import { requirePerm } from '../auth/auth';

export const matrixRouter = Router();

export async function matrixChecksum(versionId: string, db?: Db): Promise<string> {
  const rows = await q(`SELECT system_id, department_id, position_id, role_id, module_id, operation_id, effect, severity, source_ref, valid_from, valid_to, status
                          FROM matrix_rules WHERE version_id = $1
                         ORDER BY system_id, department_id NULLS FIRST, position_id NULLS FIRST, role_id NULLS FIRST, module_id NULLS FIRST, operation_id NULLS FIRST, effect, id`, [versionId], db);
  return sha256(JSON.stringify(rows));
}

matrixRouter.get('/versions', requirePerm('reference.view'), async (_req, res) => {
  res.json(await q(`SELECT v.*, cu.full_name AS created_by_name, au.full_name AS approved_by_name,
                       (SELECT count(*) FROM matrix_rules r WHERE r.version_id = v.id) AS rules_count,
                       (SELECT count(*) FROM audit_runs a WHERE a.matrix_version_id = v.id) AS audits_count
                     FROM matrix_versions v LEFT JOIN users cu ON cu.id = v.created_by LEFT JOIN users au ON au.id = v.approved_by
                     ORDER BY v.valid_from DESC, v.created_at DESC`));
});

const versionSchema = z.object({ version: zText, name: zText, description: zOptText, valid_from: zDate, valid_to: zOptDate });

matrixRouter.post('/versions', requirePerm('matrix.edit'), async (req, res) => {
  const b = parse(versionSchema.extend({ clone_from_id: zOptId }), req.body);
  const v = await tx(async (c) => {
    const v = (await c.query(`INSERT INTO matrix_versions (version, name, description, valid_from, valid_to, created_by) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *`,
      [b.version, b.name, b.description, b.valid_from, b.valid_to, req.user!.id])).rows[0];
    if (b.clone_from_id) {
      await c.query(`INSERT INTO matrix_rules (version_id, system_id, department_id, position_id, role_id, module_id, operation_id, effect, severity, source_ref, owner, valid_from, valid_to, status, notes)
                     SELECT $1, system_id, department_id, position_id, role_id, module_id, operation_id, effect, severity, source_ref, owner, valid_from, valid_to, status, notes
                       FROM matrix_rules WHERE version_id = $2`, [v.id, b.clone_from_id]);
    }
    await logActivity(req, 'MATRIX_VERSION_CREATED', { category: 'ADMIN', entityType: 'matrix_version', entityId: v.id, after: b }, c);
    return v;
  });
  res.status(201).json(v);
});

async function getVersion(id: string, db?: Db) {
  const v = await one('SELECT * FROM matrix_versions WHERE id = $1', [id], db);
  if (!v) throw notFound('Версия матрицы не найдена');
  return v;
}

matrixRouter.put('/versions/:id', requirePerm('matrix.edit'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const b = parse(versionSchema, req.body);
  const v = await getVersion(id);
  if (v.status !== 'DRAFT') throw conflict('Утверждённую версию изменять нельзя — создайте новую версию на её основе');
  await q('UPDATE matrix_versions SET version=$2, name=$3, description=$4, valid_from=$5, valid_to=$6 WHERE id=$1', [id, b.version, b.name, b.description, b.valid_from, b.valid_to]);
  await logActivity(req, 'MATRIX_VERSION_UPDATED', { category: 'ADMIN', entityType: 'matrix_version', entityId: id, before: v, after: b });
  res.json(await getVersion(id));
});

matrixRouter.post('/versions/:id/approve', requirePerm('matrix.approve'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const v = await getVersion(id);
  if (v.status !== 'DRAFT') throw conflict('Версия уже утверждена или архивирована');
  const count = await one('SELECT count(*)::int AS n FROM matrix_rules WHERE version_id = $1', [id]);
  if (!count.n) throw badRequest('Нельзя утвердить пустую версию матрицы');
  const checksum = await matrixChecksum(id);
  await q(`UPDATE matrix_versions SET status='APPROVED', approved_by=$2, approved_at=now(), checksum=$3 WHERE id=$1`, [id, req.user!.id, checksum]);
  await logActivity(req, 'MATRIX_VERSION_APPROVED', { category: 'ADMIN', entityType: 'matrix_version', entityId: id, after: { checksum, rules: count.n } });
  res.json(await getVersion(id));
});

matrixRouter.post('/versions/:id/archive', requirePerm('matrix.approve'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const v = await getVersion(id);
  if (v.status !== 'APPROVED') throw conflict('Архивировать можно только утверждённую версию');
  await q(`UPDATE matrix_versions SET status='ARCHIVED' WHERE id=$1`, [id]);
  await logActivity(req, 'MATRIX_VERSION_ARCHIVED', { category: 'ADMIN', entityType: 'matrix_version', entityId: id });
  res.json(await getVersion(id));
});

matrixRouter.delete('/versions/:id', requirePerm('matrix.edit'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const v = await getVersion(id);
  if (v.status !== 'DRAFT') throw conflict('Удалить можно только черновик');
  await tx(async (c) => {
    await c.query('DELETE FROM matrix_rules WHERE version_id = $1', [id]);
    await c.query('DELETE FROM matrix_versions WHERE id = $1', [id]);
    await logActivity(req, 'MATRIX_VERSION_DELETED', { category: 'ADMIN', entityType: 'matrix_version', entityId: id, before: v }, c);
  });
  res.json({ ok: true });
});

// ---------- Правила ----------
const RULES_SELECT = `
  SELECT r.*, s.code AS system_code, s.name AS system_name, d.code AS department_code, d.name AS department_name,
         p.code AS position_code, p.name AS position_name, ar.role_code, ar.role_name, m.code AS module_code, m.name AS module_name,
         o.code AS operation_code, o.name AS operation_name
    FROM matrix_rules r JOIN systems s ON s.id = r.system_id
    LEFT JOIN departments d ON d.id = r.department_id LEFT JOIN positions p ON p.id = r.position_id
    LEFT JOIN access_roles ar ON ar.id = r.role_id LEFT JOIN modules m ON m.id = r.module_id LEFT JOIN operations o ON o.id = r.operation_id`;

matrixRouter.get('/versions/:id/rules', requirePerm('reference.view'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const params: unknown[] = [id];
  const where = ['r.version_id = $1'];
  for (const [k, col] of Object.entries({ system_id: 'r.system_id', department_id: 'r.department_id', position_id: 'r.position_id', role_id: 'r.role_id', effect: 'r.effect' })) {
    const v = req.query[k];
    if (typeof v === 'string' && v) { params.push(v); where.push(`${col} = $${params.length}`); }
  }
  if (req.query.search) { params.push(`%${req.query.search}%`); where.push(`(r.source_ref ILIKE $${params.length} OR r.owner ILIKE $${params.length} OR ar.role_name ILIKE $${params.length} OR o.name ILIKE $${params.length})`); }
  res.json(await q(`${RULES_SELECT} WHERE ${where.join(' AND ')} ORDER BY s.code, d.code NULLS FIRST, p.code NULLS FIRST, ar.role_code NULLS FIRST, m.code NULLS FIRST, o.code NULLS FIRST LIMIT 20000`, params));
});

const ruleSchema = z.object({
  system_id: zId, department_id: zOptId, position_id: zOptId, role_id: zOptId, module_id: zOptId, operation_id: zOptId,
  effect: z.enum(['ALLOW', 'DENY']).default('ALLOW'), severity: z.union([zRisk, z.literal(''), z.null()]).optional().transform((v) => v || null),
  source_ref: zText, owner: zText, valid_from: zDate, valid_to: zOptDate, status: z.enum(['ACTIVE', 'INACTIVE']).default('ACTIVE'), notes: zOptText,
});

async function validateRuleRefs(b: z.infer<typeof ruleSchema>, db?: Db) {
  const check = async (sql: string, id: string | null, msg: string) => {
    if (!id) return;
    const r = await one(sql, [id, b.system_id], db);
    if (!r) throw badRequest(msg);
  };
  await check('SELECT 1 FROM access_roles WHERE id=$1 AND system_id=$2', b.role_id, 'Роль не принадлежит выбранной системе');
  await check('SELECT 1 FROM modules WHERE id=$1 AND system_id=$2', b.module_id, 'Модуль не принадлежит выбранной системе');
  await check('SELECT 1 FROM operations WHERE id=$1 AND system_id=$2', b.operation_id, 'Операция не принадлежит выбранной системе');
  if (b.valid_to && b.valid_to < b.valid_from) throw badRequest('Дата окончания раньше даты начала');
}

const RULE_COLS = ['system_id', 'department_id', 'position_id', 'role_id', 'module_id', 'operation_id', 'effect', 'severity', 'source_ref', 'owner', 'valid_from', 'valid_to', 'status', 'notes'] as const;

matrixRouter.post('/versions/:id/rules', requirePerm('matrix.edit'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const b = parse(ruleSchema, req.body);
  await validateRuleRefs(b);
  const r = await one(`INSERT INTO matrix_rules (version_id, ${RULE_COLS.join(',')}) VALUES ($1, ${RULE_COLS.map((_, i) => `$${i + 2}`).join(',')}) RETURNING id`, [id, ...RULE_COLS.map((k) => b[k])]);
  await logActivity(req, 'MATRIX_RULE_CREATED', { category: 'ADMIN', entityType: 'matrix_rule', entityId: r.id, after: { version_id: id, ...b } });
  res.status(201).json(await one(`${RULES_SELECT} WHERE r.id = $1`, [r.id]));
});

matrixRouter.put('/rules/:ruleId', requirePerm('matrix.edit'), async (req, res) => {
  const ruleId = parse(zId, req.params.ruleId);
  const b = parse(ruleSchema, req.body);
  await validateRuleRefs(b);
  const before = await one('SELECT * FROM matrix_rules WHERE id = $1', [ruleId]);
  if (!before) throw notFound();
  await q(`UPDATE matrix_rules SET ${RULE_COLS.map((k, i) => `${k} = $${i + 2}`).join(', ')} WHERE id = $1`, [ruleId, ...RULE_COLS.map((k) => b[k])]);
  await logActivity(req, 'MATRIX_RULE_UPDATED', { category: 'ADMIN', entityType: 'matrix_rule', entityId: ruleId, before, after: b });
  res.json(await one(`${RULES_SELECT} WHERE r.id = $1`, [ruleId]));
});

matrixRouter.delete('/rules/:ruleId', requirePerm('matrix.edit'), async (req, res) => {
  const ruleId = parse(zId, req.params.ruleId);
  const before = await one('SELECT * FROM matrix_rules WHERE id = $1', [ruleId]);
  if (!before) throw notFound();
  await q('DELETE FROM matrix_rules WHERE id = $1', [ruleId]);
  await logActivity(req, 'MATRIX_RULE_DELETED', { category: 'ADMIN', entityType: 'matrix_rule', entityId: ruleId, before });
  res.json({ ok: true });
});

// ---------- Импорт правил матрицы ----------
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 50 * 1024 * 1024, files: 1 } });
const MATRIX_COLUMNS = {
  system_code: ['код системы', 'система', 'system'],
  department_code: ['код подразделения', 'подразделение', 'department'],
  position_code: ['код должности', 'должность', 'position'],
  role_code: ['код роли', 'роль', 'role'],
  module_code: ['код модуля', 'модуль', 'module'],
  operation_code: ['код операции', 'операция', 'operation'],
  effect: ['эффект', 'разрешение', 'effect', 'разрешено'],
  severity: ['критичность', 'severity'],
  source_ref: ['основание', 'источник', 'source', 'source_ref'],
  owner: ['владелец', 'owner', 'владелец правила'],
  valid_from: ['дата начала', 'действует с', 'valid_from'],
  valid_to: ['дата окончания', 'действует по', 'valid_to'],
  notes: ['примечание', 'комментарий', 'notes'],
};

matrixRouter.post('/versions/:id/import', requirePerm('matrix.edit'), upload.single('file'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const v = await getVersion(id);
  if (v.status !== 'DRAFT') throw conflict('Импорт возможен только в черновик версии');
  if (!req.file) throw badRequest('Файл не передан');
  const name = Buffer.from(req.file.originalname, 'latin1').toString('utf8');
  const wb = await readWorkbook(name, req.file.buffer);
  const sheet = wb.sheets.find((s) => s.rows.length > 1);
  if (!sheet) throw badRequest('Файл не содержит данных');
  const t = readTable(sheet, MATRIX_COLUMNS);
  if (t.missing.includes('system_code')) throw badRequest('Не найдена колонка «Код системы»');
  const replace = req.body?.replace === 'true';

  const [systems, deps, poss, roles, mods, ops] = await Promise.all([
    q('SELECT id, code FROM systems'), q('SELECT id, code, name FROM departments'), q('SELECT id, code, name FROM positions'),
    q('SELECT id, system_id, role_code AS code FROM access_roles'), q('SELECT id, system_id, code FROM modules'), q('SELECT id, system_id, module_id, code FROM operations'),
  ]);
  const lc = (s: string) => s.trim().toLowerCase();
  const any = (s: string) => !s || s === '*' || lc(s) === 'любое' || lc(s) === 'любая' || lc(s) === 'все';
  const errors: Array<{ row: number; error: string }> = [];
  const rows: unknown[][] = [];
  for (const { rowNumber, values: r } of t.records) {
    const err = (e: string) => errors.push({ row: rowNumber, error: e });
    const sys = systems.find((s) => lc(s.code) === lc(r.system_code));
    if (!sys) { err(`Неизвестная система «${r.system_code}»`); continue; }
    const dep = any(r.department_code) ? null : deps.find((d) => lc(d.code) === lc(r.department_code) || lc(d.name) === lc(r.department_code));
    if (dep === undefined) { err(`Неизвестное подразделение «${r.department_code}»`); continue; }
    const pos = any(r.position_code) ? null : poss.find((d) => lc(d.code) === lc(r.position_code) || lc(d.name) === lc(r.position_code));
    if (pos === undefined) { err(`Неизвестная должность «${r.position_code}»`); continue; }
    const role = any(r.role_code) ? null : roles.find((x) => x.system_id === sys.id && lc(x.code) === lc(r.role_code));
    if (role === undefined) { err(`Неизвестная роль «${r.role_code}» в системе ${sys.code}`); continue; }
    const mod = any(r.module_code) ? null : mods.find((x) => x.system_id === sys.id && lc(x.code) === lc(r.module_code));
    if (mod === undefined) { err(`Неизвестный модуль «${r.module_code}»`); continue; }
    const op = any(r.operation_code) ? null : ops.find((x) => x.system_id === sys.id && lc(x.code) === lc(r.operation_code) && (!mod || x.module_id === mod.id));
    if (op === undefined) { err(`Неизвестная операция «${r.operation_code}»`); continue; }
    const eff = lc(r.effect);
    const effect = !eff || ['allow', 'разрешено', 'да', 'разрешить', '1', '+'].includes(eff) ? 'ALLOW' : ['deny', 'запрещено', 'нет', 'запретить', '0', '-'].includes(eff) ? 'DENY' : null;
    if (!effect) { err(`Неизвестный эффект «${r.effect}» (ожидается ALLOW/DENY)`); continue; }
    const severity = r.severity ? r.severity.toUpperCase() : null;
    if (severity && !['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].includes(severity)) { err(`Неизвестная критичность «${r.severity}»`); continue; }
    if (!r.source_ref) { err('Не указано основание (source_ref)'); continue; }
    if (!r.owner) { err('Не указан владелец правила'); continue; }
    const from = parseDateValue(r.valid_from);
    const to = parseDateValue(r.valid_to);
    if (!from.ok || !to.ok) { err('Некорректная дата начала/окончания'); continue; }
    rows.push([id, sys.id, dep?.id ?? null, pos?.id ?? null, role?.id ?? null, mod?.id ?? op?.module_id ?? null, op?.id ?? null, effect, severity, r.source_ref, r.owner, from.value ?? v.valid_from, to.value, 'ACTIVE', r.notes || null]);
  }
  await tx(async (c) => {
    if (replace) await c.query('DELETE FROM matrix_rules WHERE version_id = $1', [id]);
    for (const row of rows) {
      await c.query(`INSERT INTO matrix_rules (version_id, system_id, department_id, position_id, role_id, module_id, operation_id, effect, severity, source_ref, owner, valid_from, valid_to, status, notes)
                     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)`, row);
    }
    await logActivity(req, 'MATRIX_RULES_IMPORTED', { category: 'ADMIN', entityType: 'matrix_version', entityId: id, after: { file: name, imported: rows.length, errors: errors.length, replace } }, c);
  });
  res.json({ ok: rows.length, errors, warnings: wb.warnings });
});
