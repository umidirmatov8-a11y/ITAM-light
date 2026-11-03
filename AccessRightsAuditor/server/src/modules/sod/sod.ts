import { Router } from 'express';
import { z } from 'zod';
import { one, q, tx } from '../../common/db';
import { badRequest, notFound, parse, zDate, zId, zOptDate, zOptId, zOptText, zRisk, zText } from '../../common/http';
import { logActivity } from '../../common/activity';
import { requirePerm } from '../auth/auth';

export const sodRouter = Router();

const SOD_SELECT = `
  SELECT r.*, COALESCE((
    SELECT json_agg(json_build_object('id', i.id, 'side', i.side, 'item_type', i.item_type, 'operation_id', i.operation_id, 'role_id', i.role_id,
             'label', CASE WHEN i.item_type = 'OPERATION' THEN s1.code || ' / ' || o.code || ' — ' || o.name ELSE s2.code || ' / роль ' || ar.role_code || ' — ' || ar.role_name END)
             ORDER BY i.side, i.id)
      FROM sod_rule_items i
      LEFT JOIN operations o ON o.id = i.operation_id LEFT JOIN systems s1 ON s1.id = o.system_id
      LEFT JOIN access_roles ar ON ar.id = i.role_id LEFT JOIN systems s2 ON s2.id = ar.system_id
     WHERE i.rule_id = r.id), '[]') AS items
  FROM sod_rules r`;

sodRouter.get('/rules', requirePerm('reference.view'), async (_req, res) => {
  res.json(await q(`${SOD_SELECT} ORDER BY r.code`));
});

const itemSchema = z.object({ side: z.coerce.number().int().min(1).max(10), item_type: z.enum(['OPERATION', 'ROLE']), operation_id: zOptId, role_id: zOptId });
const ruleSchema = z.object({
  code: zText, name: zText, severity: zRisk.default('HIGH'), scope: z.enum(['EMPLOYEE', 'EMPLOYEE_SYSTEM']).default('EMPLOYEE'),
  justification: zText, process: zOptText, valid_from: zDate, valid_to: zOptDate, status: z.enum(['ACTIVE', 'INACTIVE']).default('ACTIVE'),
  compensating_control: zOptText, compensating_approved_by: zOptText, compensating_approved_at: zOptDate,
  items: z.array(itemSchema).min(2, 'нужно минимум две конфликтующие способности'),
});

function validate(b: z.infer<typeof ruleSchema>) {
  const sides = new Set(b.items.map((i) => i.side));
  if (sides.size < 2) throw badRequest('Правило SoD должно содержать минимум две стороны конфликта (сторона 1 и сторона 2)');
  for (const i of b.items) {
    if (i.item_type === 'OPERATION' && !i.operation_id) throw badRequest('Для элемента-операции не выбрана операция');
    if (i.item_type === 'ROLE' && !i.role_id) throw badRequest('Для элемента-роли не выбрана роль');
  }
  if (b.compensating_control && !b.compensating_approved_by) throw badRequest('Компенсирующий контроль должен быть утверждён владельцем процесса (укажите, кем утверждён)');
  if (b.valid_to && b.valid_to < b.valid_from) throw badRequest('Дата окончания раньше даты начала');
}

const COLS = ['code', 'name', 'severity', 'scope', 'justification', 'process', 'valid_from', 'valid_to', 'status', 'compensating_control', 'compensating_approved_by', 'compensating_approved_at'] as const;

async function saveItems(c: any, ruleId: string, items: z.infer<typeof itemSchema>[]) {
  await c.query('DELETE FROM sod_rule_items WHERE rule_id = $1', [ruleId]);
  for (const i of items) {
    await c.query('INSERT INTO sod_rule_items (rule_id, side, item_type, operation_id, role_id) VALUES ($1,$2,$3,$4,$5)',
      [ruleId, i.side, i.item_type, i.item_type === 'OPERATION' ? i.operation_id : null, i.item_type === 'ROLE' ? i.role_id : null]);
  }
}

sodRouter.post('/rules', requirePerm('sod.edit'), async (req, res) => {
  const b = parse(ruleSchema, req.body);
  validate(b);
  const id = await tx(async (c) => {
    const r = (await c.query(`INSERT INTO sod_rules (${COLS.join(',')}) VALUES (${COLS.map((_, i) => `$${i + 1}`).join(',')}) RETURNING id`, COLS.map((k) => b[k]))).rows[0];
    await saveItems(c, r.id, b.items);
    await logActivity(req, 'SOD_RULE_CREATED', { category: 'ADMIN', entityType: 'sod_rule', entityId: r.id, after: b }, c);
    return r.id;
  });
  res.status(201).json(await one(`${SOD_SELECT} WHERE r.id = $1`, [id]));
});

sodRouter.put('/rules/:id', requirePerm('sod.edit'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const b = parse(ruleSchema, req.body);
  validate(b);
  await tx(async (c) => {
    const before = (await c.query(`${SOD_SELECT} WHERE r.id = $1`, [id])).rows[0];
    if (!before) throw notFound();
    await c.query(`UPDATE sod_rules SET ${COLS.map((k, i) => `${k} = $${i + 2}`).join(', ')}, updated_at = now() WHERE id = $1`, [id, ...COLS.map((k) => b[k])]);
    await saveItems(c, id, b.items);
    await logActivity(req, 'SOD_RULE_UPDATED', { category: 'ADMIN', entityType: 'sod_rule', entityId: id, before, after: b }, c);
  });
  res.json(await one(`${SOD_SELECT} WHERE r.id = $1`, [id]));
});

sodRouter.delete('/rules/:id', requirePerm('sod.edit'), async (req, res) => {
  const id = parse(zId, req.params.id);
  // Правила, участвовавшие в аудитах, сохраняются в снимке аудита; удаление из каталога допустимо, но предпочтительна деактивация.
  await tx(async (c) => {
    const before = (await c.query(`${SOD_SELECT} WHERE r.id = $1`, [id])).rows[0];
    if (!before) throw notFound();
    await c.query('DELETE FROM sod_rule_items WHERE rule_id = $1', [id]);
    await c.query('DELETE FROM sod_rules WHERE id = $1', [id]);
    await logActivity(req, 'SOD_RULE_DELETED', { category: 'ADMIN', entityType: 'sod_rule', entityId: id, before }, c);
  });
  res.json({ ok: true });
});
