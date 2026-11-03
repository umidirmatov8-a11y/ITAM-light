/**
 * Демонстрационные данные: справочники двух систем (Smart Bank, NCI), кадры, утверждённая матрица,
 * SoD-правила, исключения, тестовые выгрузки и два выполненных аудита (для сравнения).
 * Использование: npm run seed:demo   (повторный запуск ничего не дублирует)
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import ExcelJS from 'exceljs';
import { migrate } from '../common/migrate';
import { one, pool, q } from '../common/db';
import { createUser, ensureInitialAdmin } from './bootstrap';
import { registerBatch, processBatch, Mapping } from '../modules/imports/imports';
import { executeAudit } from '../modules/audits/audits';
import { matrixChecksum } from '../modules/access-matrix/matrix';
import { compareAudits } from '../modules/comparisons/comparisons';
import { ROOT_DIR, config } from '../config';
import { bulkInsert } from '../common/db';

const TEMPLATES = path.join(ROOT_DIR, 'docs', 'import-templates');

const DEPARTMENTS = [['OPS', 'Операционное управление'], ['TREAS', 'Казначейство'], ['CARD', 'Управление карточных операций'], ['IT', 'Департамент ИТ']];
const POSITIONS = [['OPER', 'Операционист'], ['CTRL', 'Контролёр'], ['CHIEF', 'Начальник отдела'], ['CARDSPEC', 'Специалист по картам'], ['ADMIN', 'Администратор систем']];

// система, название, модуль, название модуля, операция, название, риск, роли (через запятую)
const CATALOG: Array<[string, string, string, string, string, string, string, string]> = [
  ['SMARTBANK', 'Smart Bank (АБС)', 'PAY', 'Платежи', 'PAY.CREATE', 'Создание платежа', 'MEDIUM', 'OPERATOR'],
  ['SMARTBANK', 'Smart Bank (АБС)', 'PAY', 'Платежи', 'PAY.APPROVE', 'Утверждение платежа', 'HIGH', 'CONTROLLER'],
  ['SMARTBANK', 'Smart Bank (АБС)', 'PAY', 'Платежи', 'PAY.VIEW', 'Просмотр платежей', 'LOW', 'OPERATOR,CONTROLLER,CHIEF'],
  ['SMARTBANK', 'Smart Bank (АБС)', 'PAY', 'Платежи', 'PAY.DELETE', 'Удаление платежа', 'CRITICAL', ''],
  ['SMARTBANK', 'Smart Bank (АБС)', 'ACC', 'Счета', 'ACC.OPEN', 'Открытие счёта', 'MEDIUM', 'OPERATOR'],
  ['SMARTBANK', 'Smart Bank (АБС)', 'ACC', 'Счета', 'ACC.VIEW', 'Просмотр счетов', 'LOW', 'OPERATOR,CONTROLLER,CHIEF'],
  ['SMARTBANK', 'Smart Bank (АБС)', 'ACC', 'Счета', 'ACC.CLOSE', 'Закрытие счёта', 'HIGH', 'CHIEF'],
  ['SMARTBANK', 'Smart Bank (АБС)', 'CFG', 'Администрирование', 'CFG.USERS', 'Управление пользователями', 'CRITICAL', 'SB_ADMIN'],
  ['NCI', 'NCI (карточный процессинг)', 'CARD', 'Карты', 'CARD.ISSUE', 'Выпуск карты', 'MEDIUM', 'CARD_OPER'],
  ['NCI', 'NCI (карточный процессинг)', 'CARD', 'Карты', 'CARD.BLOCK', 'Блокировка карты', 'MEDIUM', 'CARD_OPER'],
  ['NCI', 'NCI (карточный процессинг)', 'CARD', 'Карты', 'CARD.VIEW', 'Просмотр карт', 'LOW', 'CARD_OPER,LIMIT_MGR,LIMIT_APPR'],
  ['NCI', 'NCI (карточный процессинг)', 'LIM', 'Лимиты', 'LIM.CHANGE', 'Изменение лимитов', 'HIGH', 'LIMIT_MGR'],
  ['NCI', 'NCI (карточный процессинг)', 'LIM', 'Лимиты', 'LIM.APPROVE', 'Утверждение лимитов', 'HIGH', 'LIMIT_APPR'],
];
const ROLE_NAMES: Record<string, string> = {
  OPERATOR: 'Операционист', CONTROLLER: 'Контролёр платежей', CHIEF: 'Начальник отдела', SB_ADMIN: 'Администратор АБС',
  CARD_OPER: 'Оператор карт', LIMIT_MGR: 'Менеджер лимитов', LIMIT_APPR: 'Утверждающий лимиты',
};

// таб. №, ФИО, подразделение, должность, статус, приём, увольнение, прежнее подр., прежняя должность, дата перевода
const EMPLOYEES: string[][] = [
  ['1001', 'Иванов Иван Иванович', 'OPS', 'OPER', 'ACTIVE', '2019-03-01', '', '', '', ''],
  ['1002', 'Петрова Анна Сергеевна', 'OPS', 'CTRL', 'ACTIVE', '2018-07-15', '', '', '', ''],
  ['1003', 'Сидоров Пётр Алексеевич', 'OPS', 'CHIEF', 'ACTIVE', '2015-01-10', '', '', '', ''],
  ['1004', 'Кузнецова Мария Викторовна', 'OPS', 'OPER', 'TERMINATED', '2020-02-01', '2025-04-30', '', '', ''],
  ['1005', 'Алимов Рустам Шухратович', 'CARD', 'CARDSPEC', 'ACTIVE', '2021-05-20', '', '', '', ''],
  ['1006', 'Каримова Нилуфар Бахтиёровна', 'CARD', 'CHIEF', 'ACTIVE', '2017-09-01', '', '', '', ''],
  ['1007', 'Юсупов Тимур Рашидович', 'OPS', 'CTRL', 'ACTIVE', '2020-11-02', '', 'OPS', 'OPER', '2025-03-01'],
  ['1008', 'Морозов Алексей Николаевич', 'IT', 'ADMIN', 'ACTIVE', '2016-04-04', '', '', '', ''],
  ['1009', 'Ахмедова Дилноза Алишеровна', 'TREAS', 'OPER', 'ACTIVE', '2022-01-17', '', '', '', ''],
  ['1010', 'Ким Сергей Валерьевич', 'OPS', 'OPER', 'ACTIVE', '2023-06-01', '', '', '', ''],
  ['1011', 'Хасанов Бахтиёр Ильхомович', 'CARD', 'CARDSPEC', 'ACTIVE', '2019-12-09', '', '', '', ''],
];

// система, подразделение, должность, роль, модуль, операция, эффект, критичность, основание, владелец
const MATRIX: string[][] = [
  ['SMARTBANK', 'OPS', 'OPER', 'OPERATOR', '', '', 'ALLOW', '', 'Приказ №45 от 10.01.2025', 'Владелец АБС'],
  ['SMARTBANK', 'OPS', 'CTRL', 'CONTROLLER', '', '', 'ALLOW', '', 'Приказ №45 от 10.01.2025', 'Владелец АБС'],
  ['SMARTBANK', 'OPS', 'CHIEF', 'CHIEF', '', '', 'ALLOW', '', 'Приказ №45 от 10.01.2025', 'Владелец АБС'],
  ['SMARTBANK', 'OPS', 'CHIEF', 'CONTROLLER', '', '', 'ALLOW', '', 'Приказ №45 от 10.01.2025', 'Владелец АБС'],
  ['SMARTBANK', 'IT', 'ADMIN', 'SB_ADMIN', '', '', 'ALLOW', '', 'Регламент ИТ-12', 'Департамент ИТ'],
  ['SMARTBANK', '*', 'OPER', '*', 'PAY', 'PAY.DELETE', 'DENY', 'CRITICAL', 'Политика ИБ п.4.2', 'Служба ИБ'],
  ['NCI', 'CARD', 'CARDSPEC', 'CARD_OPER', '', '', 'ALLOW', '', 'Распоряжение №7-К', 'Владелец NCI'],
  ['NCI', 'CARD', 'CARDSPEC', 'LIMIT_MGR', '', '', 'ALLOW', '', 'Распоряжение №7-К', 'Владелец NCI'],
  ['NCI', 'CARD', 'CHIEF', 'LIMIT_APPR', '', '', 'ALLOW', '', 'Распоряжение №7-К', 'Владелец NCI'],
];

const SB_HEADERS = ['Таб. номер', 'ФИО', 'Логин', 'Система', 'Роль', 'Модуль', 'Операция', 'Дата назначения'];
const SB_JUNE: string[][] = [
  ['1001', 'Иванов Иван Иванович', 'ivanov', 'SMARTBANK', 'OPERATOR', '', '', '2023-02-01'],
  ['1001', 'Иванов Иван Иванович', 'ivanov', 'SMARTBANK', 'OPERATOR', 'PAY', 'PAY.APPROVE', '2025-05-12'],
  ['1002', 'Петрова Анна Сергеевна', 'petrova', 'SMARTBANK', 'CONTROLLER', '', '', '2021-03-10'],
  ['1002', 'Петрова Анна Сергеевна', 'petrova', 'SMARTBANK', 'SUPERUSER', '', '', '2025-06-01'],
  ['1003', 'Сидоров Пётр Алексеевич', 'sidorov', 'SMARTBANK', 'CHIEF;CONTROLLER', '', '', '31.02.2025'],
  ['1003', 'Сидоров Пётр Алексеевич', 'sidorov', 'SMARTBANK', 'OPERATOR', 'ACC', 'ACC.OPEN', '2025-04-01'],
  ['1004', 'Кузнецова Мария Викторовна', 'kuznetsova', 'SMARTBANK', 'OPERATOR', '', '', '2020-02-03'],
  ['1007', 'Юсупов Тимур Рашидович', 'yusupov', 'SMARTBANK', 'OPERATOR', 'PAY', 'PAY.CREATE', '2024-05-10'],
  ['1007', 'Юсупов Тимур Рашидович', 'yusupov', 'SMARTBANK', 'CONTROLLER', '', '', '2025-03-02'],
  ['1008', 'Морозов Алексей Николаевич', 'morozov', 'SMARTBANK', 'SB_ADMIN', '', '', '2019-01-01'],
  ['1008', 'Морозов Алексей Николаевич', 'morozov', 'SMARTBANK', 'OPERATOR', 'PAY', 'PAY.DELETE', '2025-06-20'],
  ['1009', 'Ахмедова Дилноза Алишеровна', 'akhmedova', 'SMARTBANK', 'OPERATOR', 'ACC', 'ACC.VIEW', '2022-02-01'],
  ['1010', 'Ким Сергей Валерьевич', 'kim', 'SMARTBANK', 'OPERATOR', 'PAY', 'PAY.CREATE;PAY.APPROVE', '2025-01-15'],
  ['9999', 'Неизвестный Пользователь', 'temp01', 'SMARTBANK', 'OPERATOR', '', '', '2025-06-25'],
  ['1002', 'Петрова Анна Сергеевна', 'petrova', 'SMARTBANK', '', 'PAY', 'PAY.VIEW', ''],
  ['1002', 'Петрова Анна С.', 'petrova', 'SMARTBANK', 'CONTROLLER', '', '', '2021-03-10'],
];
const SB_MARCH: string[][] = [
  ['1001', 'Иванов Иван Иванович', 'ivanov', 'SMARTBANK', 'OPERATOR', '', '', '2023-02-01'],
  ['1002', 'Петрова Анна Сергеевна', 'petrova', 'SMARTBANK', 'CONTROLLER', '', '', '2021-03-10'],
  ['1003', 'Сидоров Пётр Алексеевич', 'sidorov', 'SMARTBANK', 'CHIEF;CONTROLLER', '', '', '2016-01-01'],
  ['1004', 'Кузнецова Мария Викторовна', 'kuznetsova', 'SMARTBANK', 'OPERATOR', '', '', '2020-02-03'],
  ['1007', 'Юсупов Тимур Рашидович', 'yusupov', 'SMARTBANK', 'OPERATOR', 'PAY', 'PAY.CREATE', '2024-05-10'],
  ['1007', 'Юсупов Тимур Рашидович', 'yusupov', 'SMARTBANK', 'CONTROLLER', '', '', '2025-03-02'],
  ['1008', 'Морозов Алексей Николаевич', 'morozov', 'SMARTBANK', 'SB_ADMIN', '', '', '2019-01-01'],
  ['1009', 'Ахмедова Дилноза Алишеровна', 'akhmedova', 'SMARTBANK', 'OPERATOR', 'ACC', 'ACC.VIEW', '2022-02-01'],
  ['1009', 'Ахмедова Дилноза Алишеровна', 'akhmedova', 'SMARTBANK', 'OPERATOR', 'ACC', 'ACC.CLOSE', '2022-02-01'],
  ['1010', 'Ким Сергей Валерьевич', 'kim', 'SMARTBANK', 'OPERATOR', 'PAY', 'PAY.CREATE;PAY.APPROVE', '2025-01-15'],
];
const NCI_HEADERS = ['Табельный номер', 'ФИО', 'Учетная запись', 'Роль', 'Операция'];
const NCI_JUNE: string[][] = [
  ['1005', 'Алимов Рустам Шухратович', 'r.alimov', 'CARD_OPER', ''],
  ['1005', 'Алимов Рустам Шухратович', 'r.alimov', 'LIMIT_MGR', 'LIM.CHANGE'],
  ['1006', 'Каримова Нилуфар Бахтиёровна', 'n.karimova', 'LIMIT_APPR', ''],
  ['1006', 'Каримова Нилуфар Бахтиёровна', 'n.karimova', 'LIMIT_MGR', 'LIM.CHANGE'],
  ['1011', 'Хасанов Бахтиёр Ильхомович', 'b.khasanov', 'CARD_OPER', ''],
  ['1011', 'Хасанов Бахтиёр Ильхомович', 'b.khasanov', 'LIMIT_APPR', 'LIM.APPROVE'],
  ['1001', 'Иванов Иван Иванович', 'i.ivanov', 'CARD_OPER', 'CARD.VIEW'],
];
const NCI_MARCH: string[][] = [
  ['1005', 'Алимов Рустам Шухратович', 'r.alimov', 'CARD_OPER', ''],
  ['1006', 'Каримова Нилуфар Бахтиёровна', 'n.karimova', 'LIMIT_APPR', ''],
  ['1011', 'Хасанов Бахтиёр Ильхомович', 'b.khasanov', 'CARD_OPER', ''],
  ['1011', 'Хасанов Бахтиёр Ильхомович', 'b.khasanov', 'LIMIT_APPR', 'LIM.APPROVE'],
];

const csvLine = (r: string[]) => r.map((v) => (/[;"\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)).join(';');
const writeCsv = (file: string, headers: string[], rows: string[][]) => fs.writeFileSync(file, '﻿' + [headers, ...rows].map(csvLine).join('\r\n') + '\r\n', 'utf8');

async function writeXlsx(file: string, sheet: string, headers: string[], rows: string[][]) {
  const wb = new ExcelJS.Workbook();
  wb.created = new Date('2025-07-01T00:00:00Z');
  wb.modified = wb.created;
  const ws = wb.addWorksheet(sheet);
  ws.addRow(headers).font = { bold: true };
  for (const r of rows) ws.addRow(r);
  ws.columns.forEach((c) => { c.width = 22; });
  await wb.xlsx.writeFile(file);
}

async function writeTemplates() {
  fs.mkdirSync(TEMPLATES, { recursive: true });
  const f = (n: string) => path.join(TEMPLATES, n);
  if (!fs.existsSync(f('hr_employees.csv'))) {
    writeCsv(f('hr_employees.csv'), ['Табельный номер', 'ФИО', 'Код подразделения', 'Код должности', 'Статус', 'Дата приёма', 'Дата увольнения', 'Прежнее подразделение', 'Прежняя должность', 'Дата перевода'], EMPLOYEES);
  }
  if (!fs.existsSync(f('catalog_roles_operations.csv'))) {
    const rows: string[][] = [];
    for (const [sys, sysName, mod, modName, op, opName, risk, roles] of CATALOG) {
      for (const role of roles ? roles.split(',') : ['']) rows.push([sys, sysName, role, role ? ROLE_NAMES[role] : '', mod, modName, op, opName, risk]);
    }
    writeCsv(f('catalog_roles_operations.csv'), ['Код системы', 'Наименование системы', 'Код роли', 'Наименование роли', 'Код модуля', 'Наименование модуля', 'Код операции', 'Наименование операции', 'Риск'], rows);
  }
  if (!fs.existsSync(f('matrix_rules.csv'))) {
    writeCsv(f('matrix_rules.csv'), ['Код системы', 'Код подразделения', 'Код должности', 'Код роли', 'Код модуля', 'Код операции', 'Эффект', 'Критичность', 'Основание', 'Владелец', 'Дата начала', 'Дата окончания'],
      MATRIX.map((r) => [...r, '2025-01-01', '']));
  }
  if (!fs.existsSync(f('smartbank_access_2025-06-30.xlsx'))) await writeXlsx(f('smartbank_access_2025-06-30.xlsx'), 'Доступы', SB_HEADERS, SB_JUNE);
  if (!fs.existsSync(f('smartbank_access_2025-03-31.xlsx'))) await writeXlsx(f('smartbank_access_2025-03-31.xlsx'), 'Доступы', SB_HEADERS, SB_MARCH);
  if (!fs.existsSync(f('nci_access_2025-06-30.csv'))) writeCsv(f('nci_access_2025-06-30.csv'), NCI_HEADERS, NCI_JUNE);
  if (!fs.existsSync(f('nci_access_2025-03-31.csv'))) writeCsv(f('nci_access_2025-03-31.csv'), NCI_HEADERS, NCI_MARCH);
}

async function id(sql: string, params: unknown[]) {
  return (await one(sql, params))!.id as string;
}

async function seedReference(ownerSbId: string, ownerNciId: string) {
  for (const [code, name] of DEPARTMENTS) await q('INSERT INTO departments (code, name) VALUES ($1,$2) ON CONFLICT (code) DO NOTHING', [code, name]);
  for (const [code, name] of POSITIONS) await q('INSERT INTO positions (code, name) VALUES ($1,$2) ON CONFLICT (code) DO NOTHING', [code, name]);
  const sys: Record<string, string> = {};
  for (const [code, name, owner] of [['SMARTBANK', 'Smart Bank (АБС)', ownerSbId], ['NCI', 'NCI (карточный процессинг)', ownerNciId]]) {
    sys[code] = await id(`INSERT INTO systems (code, name, owner_user_id) VALUES ($1,$2,$3) ON CONFLICT (code) DO UPDATE SET owner_user_id = EXCLUDED.owner_user_id RETURNING id`, [code, name, owner]);
  }
  for (const [s, , mod, modName, op, opName, risk, roles] of CATALOG) {
    const m = await id(`INSERT INTO modules (system_id, code, name) VALUES ($1,$2,$3) ON CONFLICT (system_id, code) DO UPDATE SET name = EXCLUDED.name RETURNING id`, [sys[s], mod, modName]);
    const o = await id(`INSERT INTO operations (system_id, module_id, code, name, risk_level) VALUES ($1,$2,$3,$4,$5) ON CONFLICT (module_id, code) DO UPDATE SET name = EXCLUDED.name RETURNING id`, [sys[s], m, op, opName, risk]);
    for (const role of roles ? roles.split(',') : []) {
      const r = await id(`INSERT INTO access_roles (system_id, role_code, role_name) VALUES ($1,$2,$3) ON CONFLICT (system_id, role_code) DO UPDATE SET role_name = EXCLUDED.role_name RETURNING id`, [sys[s], role, ROLE_NAMES[role]]);
      await q('INSERT INTO role_operations (role_id, operation_id) VALUES ($1,$2) ON CONFLICT DO NOTHING', [r, o]);
    }
  }
  await q(`INSERT INTO access_roles (system_id, role_code, role_name) VALUES ($1,'SB_ADMIN',$2) ON CONFLICT DO NOTHING`, [sys.SMARTBANK, ROLE_NAMES.SB_ADMIN]);
  for (const e of EMPLOYEES) {
    await q(`INSERT INTO employees (employee_key, full_name, department_id, position_id, employment_status, valid_from, valid_to, previous_department_id, previous_position_id, transferred_at)
             VALUES ($1,$2,(SELECT id FROM departments WHERE code=$3),(SELECT id FROM positions WHERE code=$4),$5,$6,NULLIF($7,'')::date,
                     (SELECT id FROM departments WHERE code=NULLIF($8,'')),(SELECT id FROM positions WHERE code=NULLIF($9,'')),NULLIF($10,'')::date)
             ON CONFLICT (hr_source, employee_key) DO NOTHING`, e);
  }
  // Алиас: в выгрузках NCI встречается старое написание роли.
  const lm = await one(`SELECT id FROM access_roles WHERE role_code = 'LIMIT_MGR'`);
  await q(`INSERT INTO aliases (entity_type, system_id, alias, target_id) VALUES ('ROLE', $1, 'Менеджер лимитов (старое)', $2) ON CONFLICT DO NOTHING`, [sys.NCI, lm.id]);
  return sys;
}

async function seedMatrix(adminId: string, sys: Record<string, string>) {
  const existing = await one(`SELECT id FROM matrix_versions WHERE version = '2025.1'`);
  if (existing) return existing.id as string;
  const v = await id(`INSERT INTO matrix_versions (version, name, description, valid_from, created_by) VALUES ('2025.1', 'Матрица доступа 2025', 'Демонстрационная матрица: Smart Bank и NCI', '2025-01-01', $1) RETURNING id`, [adminId]);
  const any = (s: string) => !s || s === '*';
  for (const [s, dep, pos, role, mod, op, effect, sev, src, owner] of MATRIX) {
    await q(`INSERT INTO matrix_rules (version_id, system_id, department_id, position_id, role_id, module_id, operation_id, effect, severity, source_ref, owner, valid_from)
             VALUES ($1,$2,(SELECT id FROM departments WHERE code=$3),(SELECT id FROM positions WHERE code=$4),
                     (SELECT id FROM access_roles WHERE system_id=$2 AND role_code=$5),(SELECT id FROM modules WHERE system_id=$2 AND code=$6),
                     (SELECT id FROM operations WHERE system_id=$2 AND code=$7),$8,NULLIF($9,''),$10,$11,'2025-01-01')`,
      [v, sys[s], any(dep) ? null : dep, any(pos) ? null : pos, any(role) ? null : role, any(mod) ? null : mod, any(op) ? null : op, effect, sev, src, owner]);
  }
  await q(`UPDATE matrix_versions SET status='APPROVED', approved_by=$2, approved_at=now(), checksum=$3 WHERE id=$1`, [v, adminId, await matrixChecksum(v)]);
  return v;
}

async function seedSodAndExceptions(sys: Record<string, string>) {
  const op = async (code: string) => (await one('SELECT id FROM operations WHERE code = $1', [code]))!.id;
  const rules: Array<[string, string, string, string, string[], string[], string | null, string | null]> = [
    ['PAY-01', 'Создание и утверждение платежа', 'CRITICAL', 'Принцип «четырёх глаз»: один сотрудник не может создать и утвердить платёж', ['PAY.CREATE'], ['PAY.APPROVE'], null, null],
    ['LIM-01', 'Изменение и утверждение лимитов', 'HIGH', 'Изменение лимита и его утверждение выполняют разные сотрудники', ['LIM.CHANGE'], ['LIM.APPROVE'], null, null],
    ['ACC-01', 'Открытие и закрытие счёта', 'MEDIUM', 'Открытие и закрытие счетов разделены', ['ACC.OPEN'], ['ACC.CLOSE'], 'Ежедневная выверка открытых/закрытых счетов контролёром', 'Директор операционного департамента'],
  ];
  for (const [code, name, sev, just, s1, s2, comp, compBy] of rules) {
    if (await one('SELECT 1 FROM sod_rules WHERE code = $1', [code])) continue;
    const r = await id(`INSERT INTO sod_rules (code, name, severity, justification, valid_from, compensating_control, compensating_approved_by, compensating_approved_at)
                        VALUES ($1,$2,$3,$4,'2025-01-01',$5,$6,CASE WHEN $5::text IS NULL THEN NULL ELSE DATE '2025-01-20' END) RETURNING id`, [code, name, sev, just, comp, compBy]);
    for (const o of s1) await q(`INSERT INTO sod_rule_items (rule_id, side, item_type, operation_id) VALUES ($1, 1, 'OPERATION', $2)`, [r, await op(o)]);
    for (const o of s2) await q(`INSERT INTO sod_rule_items (rule_id, side, item_type, operation_id) VALUES ($1, 2, 'OPERATION', $2)`, [r, await op(o)]);
  }
  if (!(await one(`SELECT 1 FROM exceptions WHERE ticket_ref = 'REQ-2025-0117'`))) {
    await q(`INSERT INTO exceptions (employee_id, system_id, operation_id, ticket_ref, author, approved_by, reason, valid_from, valid_to, compensating_control)
             VALUES ((SELECT id FROM employees WHERE employee_key='1010'), $1, $2, 'REQ-2025-0117', 'Сидоров П.А.', 'Владелец АБС', 'Временное замещение контролёра на период отпуска', '2025-01-01', '2025-12-31', 'Последующий контроль платежей начальником отдела')`,
      [sys.SMARTBANK, await op('PAY.APPROVE')]);
    await q(`INSERT INTO exceptions (employee_id, system_id, operation_id, ticket_ref, author, approved_by, reason, valid_from, valid_to, compensating_control)
             VALUES ((SELECT id FROM employees WHERE employee_key='1011'), $1, $2, 'REQ-2024-0388', 'Каримова Н.Б.', 'Владелец NCI', 'Проект миграции лимитов', '2024-06-01', '2025-03-31', 'Еженедельный отчёт по изменённым лимитам')`,
      [sys.NCI, await op('LIM.APPROVE')]);
  }
}

const SB_MAPPING = (sheet: string): Mapping => ({
  sheet, headerRow: 1, splitMultiValues: true, expandRoles: true, defaultSystemId: null,
  columns: { employee_key: 0, full_name: 1, login: 2, system: 3, role: 4, module: 5, operation: 6, assigned_at: 7 },
} as Mapping);
const NCI_MAPPING = (nciId: string): Mapping => ({
  sheet: 'CSV', headerRow: 1, splitMultiValues: true, expandRoles: true, defaultSystemId: nciId,
  columns: { employee_key: 0, full_name: 1, login: 2, system: -1, role: 3, module: -1, operation: 4, assigned_at: -1 },
} as Mapping);

async function seedAudit(name: string, date: string, versionId: string, actorId: string, sys: Record<string, string>, files: Array<[string, Mapping]>) {
  const existing = await one('SELECT id FROM audit_runs WHERE name = $1', [name]);
  if (existing) return existing.id as string;
  const auditId = await id(`INSERT INTO audit_runs (name, as_of_date, matrix_version_id, created_by, description) VALUES ($1,$2,$3,$4,'Демонстрационный аудит') RETURNING id`, [name, date, versionId, actorId]);
  for (const [file, mapping] of files) {
    const buf = fs.readFileSync(path.join(TEMPLATES, file));
    const batch = await registerBatch(null, auditId, file, buf, actorId);
    await processBatch(batch.id, mapping, actorId);
  }
  await executeAudit(null, auditId, actorId);
  void sys;
  return auditId;
}

async function main() {
  fs.mkdirSync(config.dataDir, { recursive: true });
  await migrate(() => undefined);
  await ensureInitialAdmin();
  await writeTemplates();
  const password = process.env.ARA_DEMO_PASSWORD || `Demo${crypto.randomBytes(4).toString('hex')}1`;
  const exists = await one(`SELECT 1 FROM users WHERE username = 'auditor'`);
  const users: Record<string, string> = {};
  for (const [u, n, roles] of [
    ['auditor', 'Аудитор ИБ (демо)', ['AUDITOR']], ['matrix', 'Администратор матрицы (демо)', ['MATRIX_ADMIN']],
    ['owner_sb', 'Владелец Smart Bank (демо)', ['SYSTEM_OWNER']], ['owner_nci', 'Владелец NCI (демо)', ['SYSTEM_OWNER']], ['viewer', 'Руководитель (демо)', ['VIEWER']],
  ] as Array<[string, string, string[]]>) {
    const row = await one('SELECT id FROM users WHERE username = $1', [u]);
    users[u] = row ? row.id : await createUser(u, n, password, roles, false);
  }
  const sys = await seedReference(users.owner_sb, users.owner_nci);
  const versionId = await seedMatrix(users.matrix, sys);
  await seedSodAndExceptions(sys);
  const march = await seedAudit('Плановый аудит I квартал 2025', '2025-03-31', versionId, users.auditor, sys,
    [['smartbank_access_2025-03-31.xlsx', SB_MAPPING('Доступы')], ['nci_access_2025-03-31.csv', NCI_MAPPING(sys.NCI)]]);
  const june = await seedAudit('Плановый аудит II квартал 2025', '2025-06-30', versionId, users.auditor, sys,
    [['smartbank_access_2025-06-30.xlsx', SB_MAPPING('Доступы')], ['nci_access_2025-06-30.csv', NCI_MAPPING(sys.NCI)]]);
  if (!(await one('SELECT 1 FROM audit_comparisons WHERE from_audit_id = $1 AND to_audit_id = $2', [march, june]))) {
    const { items, summary } = await compareAudits(march, june);
    const c = await id('INSERT INTO audit_comparisons (from_audit_id, to_audit_id, created_by, summary) VALUES ($1,$2,$3,$4) RETURNING id', [march, june, users.auditor, JSON.stringify(summary)]);
    await bulkInsert(pool, 'comparison_items', ['comparison_id', 'access_key', 'change_type', 'before_json', 'after_json'],
      items.filter((i) => i.type !== 'UNCHANGED').map((i) => [c, i.key, i.type, i.before ? JSON.stringify(i.before) : null, i.after ? JSON.stringify(i.after) : null]));
  }
  console.log('Демонстрационные данные загружены.');
  if (!exists) {
    console.log(`Демо-пользователи: auditor, matrix, owner_sb, owner_nci, viewer — пароль: ${password}`);
  } else {
    console.log('Демо-пользователи уже существовали — пароли не изменены.');
  }
  console.log(`Шаблоны и примеры выгрузок: ${TEMPLATES}`);
}

main().catch((e) => { console.error(e); process.exitCode = 1; }).finally(() => pool.end());
