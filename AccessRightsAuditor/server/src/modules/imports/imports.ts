import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { Request, Router } from 'express';
import multer from 'multer';
import { z } from 'zod';
import { bulkInsert, one, q, tx } from '../../common/db';
import { badRequest, conflict, notFound, parse, zId, zOptId } from '../../common/http';
import { logActivity } from '../../common/activity';
import { sha256 } from '../../common/hash';
import { setting } from '../../common/settings';
import { detectFileType, guessColumn, parseDateValue, readWorkbook } from '../../common/spreadsheet';
import { requirePerm } from '../auth/auth';
import { config } from '../../config';

export const importsRouter = Router();

export const MAPPING_FIELDS = {
  employee_key: { label: 'Табельный номер / ID сотрудника', required: true, synonyms: ['табельный номер', 'табельный', 'таб номер', 'таб', 'id сотрудника', 'employee id', 'employeeid', 'personnel number'] },
  full_name: { label: 'ФИО', required: false, synonyms: ['фио', 'ф.и.о.', 'сотрудник', 'пользователь фио', 'full name', 'fullname'] },
  login: { label: 'Логин', required: false, synonyms: ['логин', 'учетная запись', 'учётная запись', 'login', 'username', 'user', 'account'] },
  system: { label: 'Система', required: true, synonyms: ['система', 'код системы', 'system', 'application', 'приложение'] },
  role: { label: 'Роль', required: true, synonyms: ['роль', 'код роли', 'role', 'профиль', 'группа'] },
  module: { label: 'Модуль', required: false, synonyms: ['модуль', 'код модуля', 'module', 'подсистема'] },
  operation: { label: 'Операция / полномочие', required: false, synonyms: ['операция', 'код операции', 'полномочие', 'право', 'operation', 'permission', 'function'] },
  assigned_at: { label: 'Дата назначения', required: false, synonyms: ['дата назначения', 'дата выдачи', 'назначено', 'assigned', 'assigned at', 'granted'] },
} as const;
type Field = keyof typeof MAPPING_FIELDS;

const mappingSchema = z.object({
  sheet: z.string().min(1),
  headerRow: z.coerce.number().int().min(1).default(1),
  columns: z.object(Object.fromEntries(Object.keys(MAPPING_FIELDS).map((k) => [k, z.union([z.coerce.number().int().min(-1), z.null()]).optional()])) as Record<Field, any>),
  defaultSystemId: zOptId,
  splitMultiValues: z.boolean().default(true),
  expandRoles: z.boolean().default(true),
  saveTemplateName: z.string().trim().max(100).optional(),
});
export type Mapping = z.infer<typeof mappingSchema>;

async function maxUploadBytes() {
  return Number(await setting('max_upload_mb', 50)) * 1024 * 1024;
}

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 200 * 1024 * 1024, files: 20 } });

async function draftAudit(id: string) {
  const a = await one('SELECT * FROM audit_runs WHERE id = $1', [id]);
  if (!a) throw notFound('Аудит не найден');
  if (a.status !== 'DRAFT' && a.status !== 'FAILED') throw conflict('Аудит уже выполнен: снимок неизменяем. Создайте новый аудит для повторной загрузки');
  return a;
}

const safeName = (n: string) => n.replace(/[^\p{L}\p{N}._ -]+/gu, '_').slice(0, 120);

// ---------- Загрузка файлов в пакет аудита ----------
importsRouter.post('/audits/:id/batches', requirePerm('import.run'), upload.array('files', 20), async (req, res) => {
  const auditId = parse(zId, req.params.id);
  await draftAudit(auditId);
  const files = (req.files as Express.Multer.File[]) ?? [];
  if (!files.length) throw badRequest('Файлы не переданы');
  const limit = await maxUploadBytes();
  const prepared = [];
  for (const f of files) {
    const name = Buffer.from(f.originalname, 'latin1').toString('utf8');
    if (f.size > limit) throw badRequest(`Файл «${name}» превышает допустимый размер ${Math.round(limit / 1048576)} МБ`);
    prepared.push({ name, buffer: f.buffer });
  }
  const created = [];
  for (const f of prepared) created.push(await registerBatch(req, auditId, f.name, f.buffer, req.user!.id));
  res.status(201).json(created);
});

/** Сохраняет оригинал файла в хранилище, вычисляет SHA-256 и создаёт пакет импорта. */
export async function registerBatch(req: Request | null, auditId: string, name: string, buffer: Buffer, actorId: string) {
  const type = detectFileType(name, buffer);
  const wb = await readWorkbook(name, buffer); // проверка, что файл читается
  const hash = sha256(buffer);
  const id = crypto.randomUUID();
  const dir = path.join(config.dataDir, 'imports', auditId);
  fs.mkdirSync(dir, { recursive: true });
  const stored = path.join(dir, `${id}_${safeName(name)}`);
  fs.writeFileSync(stored, buffer, { mode: 0o600 });
  const batch = await one(`INSERT INTO import_batches (id, audit_id, file_name, stored_path, file_size, file_type, sha256, uploaded_by, file_warnings)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *`,
    [id, auditId, name, path.relative(config.dataDir, stored), buffer.length, type, hash, actorId, JSON.stringify(wb.warnings)]);
  await logActivity(req, 'IMPORT_FILE_UPLOADED', { category: 'AUDIT', entityType: 'import_batch', entityId: id, actorId, after: { auditId, file: name, sha256: hash, size: buffer.length } });
  return batch;
}

importsRouter.get('/audits/:id/batches', requirePerm('audit.view'), async (req, res) => {
  res.json(await q(`SELECT b.*, u.full_name AS uploaded_by_name FROM import_batches b LEFT JOIN users u ON u.id = b.uploaded_by WHERE b.audit_id = $1 ORDER BY b.uploaded_at`, [parse(zId, req.params.id)]));
});

async function loadBatch(id: string) {
  const b = await one('SELECT * FROM import_batches WHERE id = $1', [id]);
  if (!b) throw notFound('Пакет импорта не найден');
  return b;
}

async function readBatchFile(b: any) {
  const full = path.join(config.dataDir, b.stored_path);
  if (!fs.existsSync(full)) throw notFound('Исходный файл пакета не найден в хранилище');
  const buf = fs.readFileSync(full);
  if (sha256(buf) !== b.sha256) throw conflict('Контрольная сумма исходного файла не совпадает — файл изменён в хранилище');
  return readWorkbook(b.file_name, buf);
}

/** Предпросмотр: листы, заголовки, первые строки и предложенное сопоставление колонок. */
importsRouter.get('/batches/:id/preview', requirePerm('import.run'), async (req, res) => {
  const b = await loadBatch(parse(zId, req.params.id));
  const wb = await readBatchFile(b);
  const headerRow = Math.max(1, Number(req.query.headerRow) || 1);
  res.json({
    batch: b,
    warnings: wb.warnings,
    fields: MAPPING_FIELDS,
    sheets: wb.sheets.map((s) => {
      const headers = s.rows[headerRow - 1] ?? [];
      const suggested = Object.fromEntries(Object.entries(MAPPING_FIELDS).map(([k, f]) => [k, guessColumn(headers, [...f.synonyms])]));
      return { name: s.name, totalRows: Math.max(0, s.rows.length - headerRow), headers, preview: s.rows.slice(headerRow, headerRow + 15), suggested };
    }),
  });
});

importsRouter.delete('/batches/:id', requirePerm('import.run'), async (req, res) => {
  const b = await loadBatch(parse(zId, req.params.id));
  await draftAudit(b.audit_id);
  await tx(async (c) => {
    await c.query('DELETE FROM access_snapshots WHERE batch_id = $1', [b.id]);
    await c.query('DELETE FROM import_rows WHERE batch_id = $1', [b.id]);
    await c.query('DELETE FROM import_batches WHERE id = $1', [b.id]);
    await logActivity(req, 'IMPORT_BATCH_DELETED', { category: 'AUDIT', entityType: 'import_batch', entityId: b.id, before: { file: b.file_name, sha256: b.sha256 } }, c);
  });
  fs.rmSync(path.join(config.dataDir, b.stored_path), { force: true });
  res.json({ ok: true });
});

importsRouter.get('/batches/:id/rows', requirePerm('audit.view'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const status = typeof req.query.status === 'string' && req.query.status ? req.query.status : null;
  res.json(await q(`SELECT id, sheet_name, row_number, raw_json, normalized_status, error_text, error_column FROM import_rows
                     WHERE batch_id = $1 AND ($2::text IS NULL OR normalized_status = $2) ORDER BY row_number LIMIT 5000`, [id, status]));
});

// ---------- Шаблоны сопоставления ----------
importsRouter.get('/import-templates', requirePerm('import.run'), async (_req, res) => {
  res.json(await q('SELECT * FROM import_mapping_templates ORDER BY name'));
});
importsRouter.delete('/import-templates/:id', requirePerm('import.run'), async (req, res) => {
  await q('DELETE FROM import_mapping_templates WHERE id = $1', [parse(zId, req.params.id)]);
  res.json({ ok: true });
});

// ---------- Обработка пакета ----------
const lc = (s: string | null | undefined) => (s ?? '').trim().toLowerCase().replace(/ё/g, 'е');
const SPLIT = /[;\n|]+/;

interface RefMaps {
  systems: Map<string, { id: string; code: string }>;
  roles: Map<string, Array<{ id: string; code: string }>>; // key: systemId|name
  modules: Map<string, Array<{ id: string; code: string }>>;
  operations: Map<string, Array<{ id: string; code: string; module_id: string }>>;
  employees: Map<string, Array<{ id: string; key: string; full_name: string }>>;
  roleComposition: Map<string, Array<{ id: string; code: string; module_id: string; module_code: string }>>;
}

async function loadRefMaps(): Promise<RefMaps> {
  const [systems, roles, modules, operations, employees, aliases, comp] = await Promise.all([
    q('SELECT id, code, name FROM systems'),
    q('SELECT id, system_id, role_code AS code, role_name AS name FROM access_roles'),
    q('SELECT id, system_id, code, name FROM modules'),
    q('SELECT id, system_id, module_id, code, name FROM operations'),
    q('SELECT id, employee_key AS key, full_name FROM employees'),
    q('SELECT entity_type, system_id, alias, target_id FROM aliases'),
    q(`SELECT ro.role_id, o.id, o.code, o.module_id, m.code AS module_code FROM role_operations ro JOIN operations o ON o.id = ro.operation_id JOIN modules m ON m.id = o.module_id ORDER BY o.code`),
  ]);
  const add = <T extends { id: string }>(m: Map<string, T[]>, k: string, v: T) => {
    const list = m.get(k) ?? [];
    if (!list.some((x) => x.id === v.id)) list.push(v);
    m.set(k, list);
  };
  const maps: RefMaps = { systems: new Map(), roles: new Map(), modules: new Map(), operations: new Map(), employees: new Map(), roleComposition: new Map() };
  for (const s of systems) { maps.systems.set(lc(s.code), s); maps.systems.set(lc(s.name), s); }
  for (const r of roles) { add(maps.roles, `${r.system_id}|${lc(r.code)}`, r); add(maps.roles, `${r.system_id}|${lc(r.name)}`, r); }
  for (const r of modules) { add(maps.modules, `${r.system_id}|${lc(r.code)}`, r); add(maps.modules, `${r.system_id}|${lc(r.name)}`, r); }
  for (const r of operations) { add(maps.operations, `${r.system_id}|${lc(r.code)}`, r); add(maps.operations, `${r.system_id}|${lc(r.name)}`, r); }
  for (const e of employees) add(maps.employees, lc(e.key), e);
  const byId = <T extends { id: string }>(list: T[]) => new Map(list.map((x) => [x.id, x]));
  const sysById = byId(systems), roleById = byId(roles), modById = byId(modules), opById = byId(operations), empById = byId(employees);
  for (const a of aliases) {
    if (a.entity_type === 'SYSTEM' && sysById.get(a.target_id)) maps.systems.set(lc(a.alias), sysById.get(a.target_id)!);
    if (a.entity_type === 'ROLE' && roleById.get(a.target_id)) add(maps.roles, `${roleById.get(a.target_id)!.system_id}|${lc(a.alias)}`, roleById.get(a.target_id)!);
    if (a.entity_type === 'MODULE' && modById.get(a.target_id)) add(maps.modules, `${modById.get(a.target_id)!.system_id}|${lc(a.alias)}`, modById.get(a.target_id)!);
    if (a.entity_type === 'OPERATION' && opById.get(a.target_id)) add(maps.operations, `${opById.get(a.target_id)!.system_id}|${lc(a.alias)}`, opById.get(a.target_id)!);
    if (a.entity_type === 'EMPLOYEE' && empById.get(a.target_id)) add(maps.employees, lc(a.alias), empById.get(a.target_id)!);
  }
  for (const c of comp) {
    const list = maps.roleComposition.get(c.role_id) ?? [];
    list.push({ id: c.id, code: c.code, module_id: c.module_id, module_code: c.module_code });
    maps.roleComposition.set(c.role_id, list);
  }
  return maps;
}

export interface ProcessResult { total: number; ok: number; warnings: number; errors: number; duplicates: number; snapshots: number; status: string }

export async function processBatch(batchId: string, mapping: Mapping, actorId: string | null): Promise<ProcessResult> {
  const b = await loadBatch(batchId);
  await draftAudit(b.audit_id);
  const wb = await readBatchFile(b);
  const sheet = wb.sheets.find((s) => s.name === mapping.sheet);
  if (!sheet) throw badRequest(`Лист «${mapping.sheet}» не найден в файле`);
  const cols = mapping.columns as Record<Field, number | null | undefined>;
  const col = (f: Field) => (cols[f] === undefined || cols[f] === null || cols[f]! < 0 ? -1 : cols[f]!);
  if (col('employee_key') < 0) throw badRequest('Не выбрана колонка «Табельный номер / ID сотрудника»');
  if (col('role') < 0) throw badRequest('Не выбрана колонка «Роль»');
  if (col('system') < 0 && !mapping.defaultSystemId) throw badRequest('Не выбрана колонка «Система» и не указана система по умолчанию');

  const maps = await loadRefMaps();
  const defaultSystem = mapping.defaultSystemId ? await one('SELECT id, code FROM systems WHERE id = $1', [mapping.defaultSystemId]) : null;
  const headers = sheet.rows[mapping.headerRow - 1] ?? [];
  const dataRows = sheet.rows.slice(mapping.headerRow);
  const rowNums = sheet.rowNumbers.slice(mapping.headerRow);

  // Ключи назначений из других пакетов этого аудита — для выявления дублей между файлами.
  const existingKeys = new Set((await q<{ access_key: string }>('SELECT access_key FROM access_snapshots WHERE audit_id = $1 AND batch_id <> $2', [b.audit_id, b.id])).map((r) => r.access_key));
  const keysInBatch = new Set<string>();

  const importRows: unknown[][] = [];
  const snapshots: unknown[][] = [];
  const counters = { ok: 0, warnings: 0, errors: 0, duplicates: 0 };

  for (let i = 0; i < dataRows.length; i++) {
    const r = dataRows[i];
    const rowId = crypto.randomUUID();
    const raw: Record<string, string> = {};
    headers.forEach((h, j) => { raw[h || `Колонка ${j + 1}`] = r[j] ?? ''; });
    const get = (f: Field) => (col(f) >= 0 ? (r[col(f)] ?? '').trim() : '');
    const issues: Array<{ level: 'ERROR' | 'WARNING'; text: string; column?: string }> = [];
    const colName = (f: Field) => headers[col(f)] ?? MAPPING_FIELDS[f].label;

    const empKeyRaw = get('employee_key');
    const fullName = get('full_name');
    const login = get('login');
    const systemRaw = get('system') || defaultSystem?.code || '';
    const rolesRaw = mapping.splitMultiValues ? get('role').split(SPLIT).map((s) => s.trim()).filter(Boolean) : [get('role')].filter(Boolean);
    const moduleRaw = get('module');
    const opsRaw = mapping.splitMultiValues ? get('operation').split(SPLIT).map((s) => s.trim()).filter(Boolean) : [get('operation')].filter(Boolean);

    if (!systemRaw) issues.push({ level: 'ERROR', text: 'Не заполнена система', column: colName('system') });
    if (!rolesRaw.length) issues.push({ level: 'ERROR', text: 'Не заполнена роль', column: colName('role') });
    if (rolesRaw.length > 1 && opsRaw.length) issues.push({ level: 'ERROR', text: 'В строке несколько ролей и указаны операции — невозможно однозначно отнести операции к ролям', column: colName('role') });
    const date = parseDateValue(get('assigned_at'));
    let assignedAt: string | null = null;
    if (!date.ok) issues.push({ level: 'WARNING', text: `Некорректная дата назначения «${get('assigned_at')}» — дата не учтена`, column: colName('assigned_at') });
    else assignedAt = date.value;

    if (issues.some((x) => x.level === 'ERROR')) {
      counters.errors++;
      importRows.push([rowId, b.id, sheet.name, rowNums[i], JSON.stringify(raw), 'ERROR', issues.map((x) => x.text).join('; '), issues.find((x) => x.level === 'ERROR')?.column ?? null]);
      continue;
    }

    // Идентичность: только по табельному номеру/ID; ФИО — вспомогательное поле.
    let employee: { id: string; key: string; full_name: string } | null = null;
    let reviewReasons: string[] = [];
    if (!empKeyRaw) {
      issues.push({ level: 'WARNING', text: 'Не заполнен табельный номер — сотрудник не сопоставлен', column: colName('employee_key') });
      reviewReasons.push('Не указан табельный номер; сопоставление только по ФИО не допускается');
    } else {
      const cands = maps.employees.get(lc(empKeyRaw)) ?? [];
      if (cands.length === 1) {
        employee = cands[0];
        if (fullName && lc(fullName).replace(/\s+/g, ' ') !== lc(employee.full_name).replace(/\s+/g, ' ')) {
          issues.push({ level: 'WARNING', text: `ФИО «${fullName}» не совпадает с кадровым справочником («${employee.full_name}»)`, column: colName('full_name') });
        }
      } else if (cands.length > 1) {
        issues.push({ level: 'WARNING', text: `Неоднозначный идентификатор «${empKeyRaw}»: найдено ${cands.length} сотрудников`, column: colName('employee_key') });
        reviewReasons.push(`Неоднозначный идентификатор сотрудника «${empKeyRaw}»`);
      } else {
        issues.push({ level: 'WARNING', text: `Сотрудник с табельным номером «${empKeyRaw}» не найден в кадровом справочнике`, column: colName('employee_key') });
        reviewReasons.push(`Сотрудник «${empKeyRaw}» не найден в кадровом справочнике`);
      }
    }

    const sys = maps.systems.get(lc(systemRaw)) ?? null;
    if (!sys) { issues.push({ level: 'WARNING', text: `Неизвестная система «${systemRaw}»`, column: colName('system') }); reviewReasons.push(`Неизвестная система «${systemRaw}»`); }

    // Атомарные назначения строки.
    const atoms: Array<{ roleRaw: string; role: { id: string; code: string } | null; moduleRaw: string; module: { id: string; code: string } | null; opRaw: string; op: { id: string; code: string; module_id: string } | null; expanded: boolean; reasons: string[] }> = [];
    for (const roleRaw of rolesRaw) {
      const reasons: string[] = [];
      let role: { id: string; code: string } | null = null;
      if (sys) {
        const rc = maps.roles.get(`${sys.id}|${lc(roleRaw)}`) ?? [];
        if (rc.length === 1) role = rc[0];
        else if (rc.length > 1) reasons.push(`Неоднозначная роль «${roleRaw}»`);
        else reasons.push(`Неизвестная роль «${roleRaw}» в системе ${sys.code}`);
      }
      let mod: { id: string; code: string } | null = null;
      if (sys && moduleRaw) {
        const mc = maps.modules.get(`${sys.id}|${lc(moduleRaw)}`) ?? [];
        if (mc.length === 1) mod = mc[0];
        else reasons.push(mc.length > 1 ? `Неоднозначный модуль «${moduleRaw}»` : `Неизвестный модуль «${moduleRaw}»`);
      }
      if (opsRaw.length) {
        for (const opRaw of opsRaw) {
          const r2 = [...reasons];
          let op: { id: string; code: string; module_id: string } | null = null;
          if (sys) {
            let oc = maps.operations.get(`${sys.id}|${lc(opRaw)}`) ?? [];
            if (mod) oc = oc.filter((o) => o.module_id === mod!.id);
            if (oc.length === 1) op = oc[0];
            else r2.push(oc.length > 1 ? `Неоднозначная операция «${opRaw}» (укажите модуль)` : `Неизвестная операция «${opRaw}»`);
          }
          atoms.push({ roleRaw, role, moduleRaw, module: mod, opRaw, op, expanded: false, reasons: r2 });
        }
      } else if (role && mapping.expandRoles && (maps.roleComposition.get(role.id)?.length ?? 0) > 0) {
        // Составной профиль роли разворачивается в фактический набор атомарных операций.
        for (const o of maps.roleComposition.get(role.id)!) {
          if (mod && o.module_id !== mod.id) continue;
          atoms.push({ roleRaw, role, moduleRaw: moduleRaw || o.module_code, module: mod ?? { id: o.module_id, code: o.module_code }, opRaw: o.code, op: o, expanded: true, reasons: [...reasons] });
        }
      } else {
        atoms.push({ roleRaw, role, moduleRaw, module: mod, opRaw: '', op: null, expanded: false, reasons });
      }
    }

    let createdForRow = 0;
    let dupForRow = 0;
    for (const at of atoms) {
      const allReasons = [...reviewReasons, ...at.reasons];
      for (const reason of at.reasons) issues.push({ level: 'WARNING', text: reason });
      const moduleId = at.module?.id ?? (at.op ? at.op.module_id : null);
      const key = [
        employee ? lc(employee.key) : `?${lc(empKeyRaw) || lc(fullName)}`,
        sys ? lc(sys.code) : `?${lc(systemRaw)}`,
        lc(login),
        at.role ? lc(at.role.code) : `?${lc(at.roleRaw)}`,
        at.module ? lc(at.module.code) : lc(at.moduleRaw) ? `?${lc(at.moduleRaw)}` : '',
        at.op ? lc(at.op.code) : lc(at.opRaw) ? `?${lc(at.opRaw)}` : '',
      ].join('|');
      if (existingKeys.has(key) || keysInBatch.has(key)) { dupForRow++; continue; }
      keysInBatch.add(key);
      createdForRow++;
      snapshots.push([
        b.audit_id, b.id, rowId, employee?.id ?? null, sys?.id ?? null, at.role?.id ?? null, moduleId, at.op?.id ?? null,
        empKeyRaw || null, fullName || null, login, systemRaw || null, at.roleRaw || null, at.moduleRaw || null, at.opRaw || null,
        assignedAt, at.expanded, allReasons.length ? 'NEEDS_REVIEW' : 'OK', allReasons.length ? [...new Set(allReasons)].join('; ') : null, key,
      ]);
    }

    let status: string;
    if (createdForRow === 0 && dupForRow > 0) {
      status = 'DUPLICATE';
      counters.duplicates++;
      issues.push({ level: 'WARNING', text: 'Дубль: такое назначение уже загружено' });
    } else if (issues.length) {
      status = 'WARNING';
      counters.warnings++;
      if (dupForRow) issues.push({ level: 'WARNING', text: `Дублирующихся атомарных назначений пропущено: ${dupForRow}` });
    } else {
      status = 'OK';
      counters.ok++;
    }
    const uniq = [...new Set(issues.map((x) => x.text))];
    importRows.push([rowId, b.id, sheet.name, rowNums[i], JSON.stringify(raw), status, uniq.length ? uniq.join('; ') : null, issues[0]?.column ?? null]);
  }

  const total = dataRows.length;
  const status = counters.errors || counters.warnings || counters.duplicates ? 'PROCESSED_WITH_ERRORS' : 'PROCESSED';
  await tx(async (c) => {
    await c.query('DELETE FROM access_snapshots WHERE batch_id = $1', [b.id]);
    await c.query('DELETE FROM import_rows WHERE batch_id = $1', [b.id]);
    await bulkInsert(c, 'import_rows', ['id', 'batch_id', 'sheet_name', 'row_number', 'raw_json', 'normalized_status', 'error_text', 'error_column'], importRows);
    await bulkInsert(c, 'access_snapshots', ['audit_id', 'batch_id', 'source_row_id', 'employee_id', 'system_id', 'role_id', 'module_id', 'operation_id',
      'employee_key_raw', 'full_name_raw', 'login', 'system_raw', 'role_raw', 'module_raw', 'operation_raw', 'assigned_at', 'expanded_from_role',
      'normalized_status', 'review_reason', 'access_key'], snapshots);
    const { saveTemplateName, ...mappingToStore } = mapping;
    await c.query(`UPDATE import_batches SET mapping_json=$2, sheet_name=$3, status=$4, total_rows=$5, ok_rows=$6, error_rows=$7, warning_rows=$8, processed_at=now() WHERE id=$1`,
      [b.id, JSON.stringify(mappingToStore), sheet.name, status, total, counters.ok, counters.errors, counters.warnings + counters.duplicates]);
    if (saveTemplateName) {
      await c.query(`INSERT INTO import_mapping_templates (name, mapping, created_by) VALUES ($1,$2,$3) ON CONFLICT (name) DO UPDATE SET mapping = EXCLUDED.mapping`,
        [saveTemplateName, JSON.stringify({ ...mappingToStore, headers }), actorId]);
    }
  });
  return { total, ...counters, snapshots: snapshots.length, status };
}

importsRouter.post('/batches/:id/process', requirePerm('import.run'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const mapping = parse(mappingSchema, req.body);
  const started = Date.now();
  const result = await processBatch(id, mapping, req.user!.id);
  await logActivity(req, 'IMPORT_BATCH_PROCESSED', { category: 'AUDIT', entityType: 'import_batch', entityId: id, after: { ...result, mapping, ms: Date.now() - started } });
  res.json(result);
});
