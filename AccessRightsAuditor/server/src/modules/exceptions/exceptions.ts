import { Router } from 'express';
import { z } from 'zod';
import { one, q } from '../../common/db';
import { badRequest, notFound, parse, zDate, zId, zOptId, zText } from '../../common/http';
import { logActivity } from '../../common/activity';
import { requirePerm, scopedSystemIds } from '../auth/auth';

export const exceptionsRouter = Router();

const SELECT = `
  SELECT x.*, e.employee_key, e.full_name AS employee_name, s.code AS system_code, s.name AS system_name,
         ar.role_code, ar.role_name, o.code AS operation_code, o.name AS operation_name,
         CASE WHEN x.status <> 'APPROVED' THEN x.status
              WHEN x.valid_to < CURRENT_DATE THEN 'EXPIRED'
              WHEN x.valid_from > CURRENT_DATE THEN 'PENDING'
              ELSE 'ACTIVE' END AS effective_status
    FROM exceptions x JOIN employees e ON e.id = x.employee_id JOIN systems s ON s.id = x.system_id
    LEFT JOIN access_roles ar ON ar.id = x.role_id LEFT JOIN operations o ON o.id = x.operation_id`;

exceptionsRouter.get('/', requirePerm('exceptions.view'), async (req, res) => {
  const params: unknown[] = [];
  const where: string[] = [];
  const scope = await scopedSystemIds(req);
  if (scope) { params.push(scope); where.push(`x.system_id = ANY($${params.length})`); }
  if (req.query.system_id) { params.push(req.query.system_id); where.push(`x.system_id = $${params.length}`); }
  if (req.query.search) { params.push(`%${req.query.search}%`); where.push(`(x.ticket_ref ILIKE $${params.length} OR e.full_name ILIKE $${params.length} OR e.employee_key ILIKE $${params.length})`); }
  let sql = `${SELECT} ${where.length ? 'WHERE ' + where.join(' AND ') : ''}`;
  if (req.query.effective_status) { params.push(req.query.effective_status); sql = `SELECT * FROM (${sql}) z WHERE effective_status = $${params.length}`; }
  res.json(await q(`${sql} ORDER BY valid_to DESC LIMIT 5000`, params));
});

const schema = z.object({
  employee_id: zId, system_id: zId, role_id: zOptId, operation_id: zOptId, ticket_ref: zText, author: zText, approved_by: zText,
  reason: zText, valid_from: zDate, valid_to: zDate, compensating_control: zText, status: z.enum(['DRAFT', 'APPROVED', 'REVOKED']).default('APPROVED'),
});
const COLS = ['employee_id', 'system_id', 'role_id', 'operation_id', 'ticket_ref', 'author', 'approved_by', 'reason', 'valid_from', 'valid_to', 'compensating_control', 'status'] as const;

async function validate(b: z.infer<typeof schema>) {
  if (b.valid_to < b.valid_from) throw badRequest('Дата окончания раньше даты начала');
  if (b.role_id && !(await one('SELECT 1 FROM access_roles WHERE id=$1 AND system_id=$2', [b.role_id, b.system_id]))) throw badRequest('Роль не принадлежит выбранной системе');
  if (b.operation_id && !(await one('SELECT 1 FROM operations WHERE id=$1 AND system_id=$2', [b.operation_id, b.system_id]))) throw badRequest('Операция не принадлежит выбранной системе');
}

exceptionsRouter.post('/', requirePerm('exceptions.edit'), async (req, res) => {
  const b = parse(schema, req.body);
  await validate(b);
  const r = await one(`INSERT INTO exceptions (${COLS.join(',')}, created_by) VALUES (${COLS.map((_, i) => `$${i + 1}`).join(',')}, $${COLS.length + 1}) RETURNING id`, [...COLS.map((k) => b[k]), req.user!.id]);
  await logActivity(req, 'EXCEPTION_CREATED', { category: 'DATA', entityType: 'exception', entityId: r.id, after: b });
  res.status(201).json(await one(`${SELECT} WHERE x.id = $1`, [r.id]));
});

exceptionsRouter.put('/:id', requirePerm('exceptions.edit'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const b = parse(schema, req.body);
  await validate(b);
  const before = await one('SELECT * FROM exceptions WHERE id = $1', [id]);
  if (!before) throw notFound();
  await q(`UPDATE exceptions SET ${COLS.map((k, i) => `${k} = $${i + 2}`).join(', ')}, updated_at = now() WHERE id = $1`, [id, ...COLS.map((k) => b[k])]);
  await logActivity(req, 'EXCEPTION_UPDATED', { category: 'DATA', entityType: 'exception', entityId: id, before, after: b });
  res.json(await one(`${SELECT} WHERE x.id = $1`, [id]));
});

// Исключения не удаляются — только отзываются (история сохраняется для доказуемости).
exceptionsRouter.post('/:id/revoke', requirePerm('exceptions.edit'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const before = await one('SELECT * FROM exceptions WHERE id = $1', [id]);
  if (!before) throw notFound();
  await q(`UPDATE exceptions SET status = 'REVOKED', updated_at = now() WHERE id = $1`, [id]);
  await logActivity(req, 'EXCEPTION_REVOKED', { category: 'DATA', entityType: 'exception', entityId: id, before });
  res.json(await one(`${SELECT} WHERE x.id = $1`, [id]));
});
