import { Router } from 'express';
import multer from 'multer';
import { z } from 'zod';
import { Db, q, tx } from '../../common/db';
import { mountCrud } from '../../common/crud';
import { badRequest, parse, zDate, zId, zOptDate, zOptId, zOptText, zRisk, zText } from '../../common/http';
import { logActivity } from '../../common/activity';
import { parseDateValue, readTable, readWorkbook } from '../../common/spreadsheet';
import { requirePerm } from '../auth/auth';

export const referenceRouter = Router();
const V = 'reference.view';
const E = 'reference.edit';

mountCrud(referenceRouter, {
  path: 'departments', table: 'departments', entity: 'department', viewPerm: V, editPerm: E,
  schema: z.object({ code: zText, name: zText, parent_id: zOptId, is_active: z.boolean().default(true) }),
  selectSql: `SELECT t.*, p.name AS parent_name FROM departments t LEFT JOIN departments p ON p.id = t.parent_id`,
  orderBy: 't.code', searchCols: ['t.code', 't.name'],
});

mountCrud(referenceRouter, {
  path: 'positions', table: 'positions', entity: 'position', viewPerm: V, editPerm: E,
  schema: z.object({ code: zText, name: zText, is_active: z.boolean().default(true) }),
  selectSql: `SELECT t.* FROM positions t`, orderBy: 't.code', searchCols: ['t.code', 't.name'],
});

mountCrud(referenceRouter, {
  path: 'systems', table: 'systems', entity: 'system', viewPerm: V, editPerm: E,
  schema: z.object({ code: zText, name: zText, description: zOptText, owner_user_id: zOptId, is_active: z.boolean().default(true) }),
  selectSql: `SELECT t.*, u.full_name AS owner_name,
                (SELECT count(*) FROM access_roles r WHERE r.system_id = t.id) AS roles_count,
                (SELECT count(*) FROM operations o WHERE o.system_id = t.id) AS operations_count
                FROM systems t LEFT JOIN users u ON u.id = t.owner_user_id`,
  orderBy: 't.code', searchCols: ['t.code', 't.name'],
});

mountCrud(referenceRouter, {
  path: 'roles', table: 'access_roles', entity: 'access_role', viewPerm: V, editPerm: E,
  schema: z.object({ system_id: zId, role_code: zText, role_name: zText, description: zOptText, operation_ids: z.array(zId).optional() }),
  virtualFields: ['operation_ids'],
  afterSave: async (id, data, c) => {
    if (!data.operation_ids) return;
    await c.query('DELETE FROM role_operations WHERE role_id = $1', [id]);
    await c.query(`INSERT INTO role_operations (role_id, operation_id) SELECT $1, o.id FROM operations o JOIN access_roles r ON r.id = $1 AND r.system_id = o.system_id WHERE o.id = ANY($2)`, [id, data.operation_ids]);
  },
  selectSql: `SELECT t.*, s.code AS system_code, s.name AS system_name,
                COALESCE((SELECT array_agg(ro.operation_id) FROM role_operations ro WHERE ro.role_id = t.id), '{}') AS operation_ids
                FROM access_roles t JOIN systems s ON s.id = t.system_id`,
  orderBy: 's.code, t.role_code', searchCols: ['t.role_code', 't.role_name'], filters: { system_id: 't.system_id' },
});

mountCrud(referenceRouter, {
  path: 'modules', table: 'modules', entity: 'module', viewPerm: V, editPerm: E,
  schema: z.object({ system_id: zId, code: zText, name: zText }),
  selectSql: `SELECT t.*, s.code AS system_code FROM modules t JOIN systems s ON s.id = t.system_id`,
  orderBy: 's.code, t.code', searchCols: ['t.code', 't.name'], filters: { system_id: 't.system_id' },
});

mountCrud(referenceRouter, {
  path: 'operations', table: 'operations', entity: 'operation', viewPerm: V, editPerm: E,
  schema: z.object({ module_id: zId, code: zText, name: zText, risk_level: zRisk.default('MEDIUM') }),
  beforeSave: async (data, c) => {
    const m = (await c.query('SELECT system_id FROM modules WHERE id = $1', [data.module_id])).rows[0];
    if (!m) throw badRequest('Модуль не найден');
    return { ...data, system_id: m.system_id };
  },
  selectSql: `SELECT t.*, s.code AS system_code, m.code AS module_code, m.name AS module_name
                FROM operations t JOIN modules m ON m.id = t.module_id JOIN systems s ON s.id = t.system_id`,
  orderBy: 's.code, m.code, t.code', searchCols: ['t.code', 't.name'], filters: { system_id: 't.system_id', module_id: 't.module_id' },
});

const employeeSchema = z.object({
  employee_key: zText,
  hr_source: z.string().trim().min(1).default('HR'),
  full_name: zText,
  department_id: zOptId,
  position_id: zOptId,
  employment_status: z.enum(['ACTIVE', 'TERMINATED', 'LEAVE', 'TRANSFERRED']).default('ACTIVE'),
  valid_from: zOptDate,
  valid_to: zOptDate,
  previous_department_id: zOptId,
  previous_position_id: zOptId,
  transferred_at: zOptDate,
});

mountCrud(referenceRouter, {
  path: 'employees', table: 'employees', entity: 'employee', viewPerm: V, editPerm: E,
  schema: employeeSchema,
  beforeSave: async (data) => ({ ...data, updated_at: new Date() }),
  selectSql: `SELECT t.*, d.name AS department_name, p.name AS position_name, pd.name AS previous_department_name, pp.name AS previous_position_name
                FROM employees t LEFT JOIN departments d ON d.id = t.department_id LEFT JOIN positions p ON p.id = t.position_id
                LEFT JOIN departments pd ON pd.id = t.previous_department_id LEFT JOIN positions pp ON pp.id = t.previous_position_id`,
  orderBy: 't.full_name', searchCols: ['t.employee_key', 't.full_name'],
  filters: { department_id: 't.department_id', position_id: 't.position_id', employment_status: 't.employment_status' },
  limit: 2000,
});

mountCrud(referenceRouter, {
  path: 'aliases', table: 'aliases', entity: 'alias', viewPerm: V, editPerm: E,
  schema: z.object({ entity_type: z.enum(['SYSTEM', 'ROLE', 'MODULE', 'OPERATION', 'EMPLOYEE']), system_id: zOptId, alias: zText, target_id: zId }),
  selectSql: `SELECT t.*, s.code AS system_code,
                COALESCE(ts.code || ' — ' || ts.name, tr.role_code || ' — ' || tr.role_name, tm.code || ' — ' || tm.name, top.code || ' — ' || top.name, te.employee_key || ' — ' || te.full_name) AS target_label
                FROM aliases t LEFT JOIN systems s ON s.id = t.system_id
                LEFT JOIN systems ts ON t.entity_type = 'SYSTEM' AND ts.id = t.target_id
                LEFT JOIN access_roles tr ON t.entity_type = 'ROLE' AND tr.id = t.target_id
                LEFT JOIN modules tm ON t.entity_type = 'MODULE' AND tm.id = t.target_id
                LEFT JOIN operations top ON t.entity_type = 'OPERATION' AND top.id = t.target_id
                LEFT JOIN employees te ON t.entity_type = 'EMPLOYEE' AND te.id = t.target_id`,
  orderBy: 't.entity_type, t.alias', searchCols: ['t.alias'], filters: { entity_type: 't.entity_type' },
});

/** Компактные списки для выпадающих списков интерфейса. */
referenceRouter.get('/lookups', requirePerm(V), async (_req, res) => {
  const [systems, departments, positions, roles, modules, operations] = await Promise.all([
    q('SELECT id, code, name, owner_user_id, is_active FROM systems ORDER BY code'),
    q('SELECT id, code, name FROM departments ORDER BY code'),
    q('SELECT id, code, name FROM positions ORDER BY code'),
    q('SELECT id, system_id, role_code AS code, role_name AS name FROM access_roles ORDER BY role_code'),
    q('SELECT id, system_id, code, name FROM modules ORDER BY code'),
    q('SELECT id, system_id, module_id, code, name, risk_level FROM operations ORDER BY code'),
  ]);
  res.json({ systems, departments, positions, roles, modules, operations });
});

referenceRouter.get('/employee-options', requirePerm(V), async (req, res) => {
  const s = String(req.query.search ?? '');
  res.json(await q(`SELECT id, employee_key, full_name, employment_status FROM employees
                     WHERE $1 = '' OR employee_key ILIKE $2 OR full_name ILIKE $2 ORDER BY full_name LIMIT 50`, [s, `%${s}%`]));
});

// ---------- Импорт справочников из XLSX/CSV ----------
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 50 * 1024 * 1024, files: 1 } });

const EMPLOYEE_COLUMNS = {
  employee_key: ['табельный номер', 'табельный', 'таб номер', 'id сотрудника', 'employee id', 'employeekey'],
  full_name: ['фио', 'ф.и.о.', 'сотрудник', 'fullname', 'name'],
  department_code: ['код подразделения', 'подразделение', 'department'],
  department_name: ['наименование подразделения', 'название подразделения'],
  position_code: ['код должности', 'должность', 'position'],
  position_name: ['наименование должности', 'название должности'],
  employment_status: ['статус', 'status', 'статус занятости'],
  hire_date: ['дата приема', 'дата приёма', 'valid_from'],
  termination_date: ['дата увольнения', 'valid_to'],
  previous_department_code: ['прежнее подразделение', 'предыдущее подразделение'],
  previous_position_code: ['прежняя должность', 'предыдущая должность'],
  transferred_at: ['дата перевода'],
};

const CATALOG_COLUMNS = {
  system_code: ['код системы', 'система', 'system'],
  system_name: ['наименование системы', 'название системы'],
  role_code: ['код роли', 'роль', 'role'],
  role_name: ['наименование роли', 'название роли'],
  module_code: ['код модуля', 'модуль', 'module'],
  module_name: ['наименование модуля', 'название модуля'],
  operation_code: ['код операции', 'операция', 'operation'],
  operation_name: ['наименование операции', 'название операции'],
  risk_level: ['риск', 'критичность', 'risk'],
};

function mapStatus(v: string): 'ACTIVE' | 'TERMINATED' | 'LEAVE' | 'TRANSFERRED' | null {
  const s = v.trim().toLowerCase();
  if (!s) return 'ACTIVE';
  if (['active', 'работает', 'активен', 'действующий', 'принят'].includes(s)) return 'ACTIVE';
  if (['terminated', 'уволен', 'уволена', 'уволен(а)'].includes(s)) return 'TERMINATED';
  if (['leave', 'отпуск', 'декрет', 'длительный отпуск'].includes(s)) return 'LEAVE';
  if (['transferred', 'переведен', 'переведён', 'переведена'].includes(s)) return 'TRANSFERRED';
  return null;
}

async function ensureCoded(c: Db, table: 'departments' | 'positions', code: string, name: string | undefined, created: string[]): Promise<string | null> {
  if (!code) return null;
  const r = await c.query(`SELECT id FROM ${table} WHERE lower(code) = lower($1) OR lower(name) = lower($1) LIMIT 1`, [code]);
  if (r.rows[0]) return r.rows[0].id;
  const ins = await c.query(`INSERT INTO ${table} (code, name) VALUES ($1, $2) RETURNING id`, [code, name || code]);
  created.push(`${table === 'departments' ? 'Подразделение' : 'Должность'} «${code}»`);
  return ins.rows[0].id;
}

referenceRouter.post('/import/:kind', requirePerm(E), upload.single('file'), async (req, res) => {
  const kind = parse(z.enum(['employees', 'catalog']), req.params.kind);
  if (!req.file) throw badRequest('Файл не передан');
  const name = Buffer.from(req.file.originalname, 'latin1').toString('utf8');
  const wb = await readWorkbook(name, req.file.buffer);
  const sheet = wb.sheets.find((s) => s.rows.length > 1);
  if (!sheet) throw badRequest('Файл не содержит данных');
  const errors: Array<{ row: number; error: string }> = [];
  const created: string[] = [];
  let ok = 0;

  await tx(async (c) => {
    if (kind === 'employees') {
      const t = readTable(sheet, EMPLOYEE_COLUMNS);
      if (t.missing.includes('employee_key') || t.missing.includes('full_name')) throw badRequest('Не найдены обязательные колонки «Табельный номер» и «ФИО»');
      const seen = new Set<string>();
      for (const { rowNumber, values: v } of t.records) {
        if (!v.employee_key) { errors.push({ row: rowNumber, error: 'Пустой табельный номер' }); continue; }
        if (!v.full_name) { errors.push({ row: rowNumber, error: 'Пустое ФИО' }); continue; }
        if (seen.has(v.employee_key)) { errors.push({ row: rowNumber, error: `Дубль табельного номера ${v.employee_key}` }); continue; }
        seen.add(v.employee_key);
        const status = mapStatus(v.employment_status);
        if (!status) { errors.push({ row: rowNumber, error: `Неизвестный статус «${v.employment_status}»` }); continue; }
        const dates: Record<string, string | null> = {};
        let bad = false;
        for (const k of ['hire_date', 'termination_date', 'transferred_at']) {
          const p = parseDateValue(v[k]);
          if (!p.ok) { errors.push({ row: rowNumber, error: `Некорректная дата в колонке ${k}: «${v[k]}»` }); bad = true; break; }
          dates[k] = p.value;
        }
        if (bad) continue;
        const dep = await ensureCoded(c, 'departments', v.department_code, v.department_name, created);
        const pos = await ensureCoded(c, 'positions', v.position_code, v.position_name, created);
        const pdep = await ensureCoded(c, 'departments', v.previous_department_code, undefined, created);
        const ppos = await ensureCoded(c, 'positions', v.previous_position_code, undefined, created);
        await c.query(`INSERT INTO employees (employee_key, full_name, department_id, position_id, employment_status, valid_from, valid_to, previous_department_id, previous_position_id, transferred_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                       ON CONFLICT (hr_source, employee_key) DO UPDATE SET full_name=EXCLUDED.full_name, department_id=EXCLUDED.department_id, position_id=EXCLUDED.position_id,
                         employment_status=EXCLUDED.employment_status, valid_from=EXCLUDED.valid_from, valid_to=EXCLUDED.valid_to,
                         previous_department_id=EXCLUDED.previous_department_id, previous_position_id=EXCLUDED.previous_position_id, transferred_at=EXCLUDED.transferred_at, updated_at=now()`,
          [v.employee_key, v.full_name, dep, pos, status, dates.hire_date, dates.termination_date, pdep, ppos, dates.transferred_at]);
        ok++;
      }
    } else {
      const t = readTable(sheet, CATALOG_COLUMNS);
      if (t.missing.includes('system_code') || t.missing.includes('role_code')) throw badRequest('Не найдены обязательные колонки «Код системы» и «Код роли»');
      for (const { rowNumber, values: v } of t.records) {
        if (!v.system_code) { errors.push({ row: rowNumber, error: 'Пустой код системы' }); continue; }
        const risk = (v.risk_level || 'MEDIUM').toUpperCase();
        const riskMap: Record<string, string> = { НИЗКИЙ: 'LOW', СРЕДНИЙ: 'MEDIUM', ВЫСОКИЙ: 'HIGH', КРИТИЧЕСКИЙ: 'CRITICAL', КРИТИЧНЫЙ: 'CRITICAL' };
        const riskLevel = riskMap[risk] ?? risk;
        if (!['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].includes(riskLevel)) { errors.push({ row: rowNumber, error: `Неизвестный уровень риска «${v.risk_level}»` }); continue; }
        const sys = (await c.query(`INSERT INTO systems (code, name) VALUES ($1, $2) ON CONFLICT (code) DO UPDATE SET name = CASE WHEN $3 THEN EXCLUDED.name ELSE systems.name END RETURNING id`,
          [v.system_code, v.system_name || v.system_code, Boolean(v.system_name)])).rows[0].id;
        let roleId: string | null = null;
        if (v.role_code) {
          roleId = (await c.query(`INSERT INTO access_roles (system_id, role_code, role_name) VALUES ($1,$2,$3) ON CONFLICT (system_id, role_code) DO UPDATE SET role_name = CASE WHEN $4 THEN EXCLUDED.role_name ELSE access_roles.role_name END RETURNING id`,
            [sys, v.role_code, v.role_name || v.role_code, Boolean(v.role_name)])).rows[0].id;
        }
        if (v.operation_code && !v.module_code) { errors.push({ row: rowNumber, error: 'Для операции не указан модуль' }); continue; }
        if (v.module_code) {
          const mod = (await c.query(`INSERT INTO modules (system_id, code, name) VALUES ($1,$2,$3) ON CONFLICT (system_id, code) DO UPDATE SET name = CASE WHEN $4 THEN EXCLUDED.name ELSE modules.name END RETURNING id`,
            [sys, v.module_code, v.module_name || v.module_code, Boolean(v.module_name)])).rows[0].id;
          if (v.operation_code) {
            const op = (await c.query(`INSERT INTO operations (system_id, module_id, code, name, risk_level) VALUES ($1,$2,$3,$4,$5)
                                       ON CONFLICT (module_id, code) DO UPDATE SET name = CASE WHEN $6 THEN EXCLUDED.name ELSE operations.name END, risk_level = EXCLUDED.risk_level RETURNING id`,
              [sys, mod, v.operation_code, v.operation_name || v.operation_code, riskLevel, Boolean(v.operation_name)])).rows[0].id;
            if (roleId) await c.query('INSERT INTO role_operations (role_id, operation_id) VALUES ($1,$2) ON CONFLICT DO NOTHING', [roleId, op]);
          }
        }
        ok++;
      }
    }
    await logActivity(req, `REFERENCE_IMPORT_${kind.toUpperCase()}`, { category: 'DATA', entityType: kind, after: { file: name, ok, errors: errors.length, created } }, c);
  });
  res.json({ ok, errors, created, warnings: wb.warnings });
});

export const zEmployeeSchema = employeeSchema;
export { zDate };
