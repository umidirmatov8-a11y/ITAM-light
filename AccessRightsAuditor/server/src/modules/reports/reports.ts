import fs from 'node:fs';
import path from 'node:path';
import { Request, Router } from 'express';
import ExcelJS from 'exceljs';
import PDFDocument from 'pdfkit';
import { one, q } from '../../common/db';
import { badRequest, parse, zId } from '../../common/http';
import { logActivity } from '../../common/activity';
import { sha256 } from '../../common/hash';
import { requirePerm, scopedSystemIds } from '../auth/auth';
import { FINDINGS_COLUMNS, FINDINGS_FROM, FindingFilters, findingsWhere, getAudit } from '../audits/audits';
import { CHANGE_RU, FSTATUS_RU, IMPORT_STATUS_RU, OUTCOME_RU, RESULT_RU, SEVERITY_RU, TYPE_RU } from './labels';
import { config } from '../../config';

export const reportsRouter = Router();

const FILTER_KEYS: Array<keyof FindingFilters> = ['system_id', 'department_id', 'position_id', 'severity', 'finding_type', 'outcome', 'status', 'owner_user_id', 'search'];

async function loadReportData(req: Request, auditId: string) {
  const audit = await getAudit(auditId);
  if (audit.status !== 'COMPLETED') throw badRequest('Отчёт формируется только по выполненному аудиту');
  const filters: FindingFilters = {};
  for (const k of FILTER_KEYS) if (typeof req.query[k] === 'string' && req.query[k]) filters[k] = req.query[k] as string;
  const { where, params } = await findingsWhere(req, auditId, filters);
  const scope = await scopedSystemIds(req);
  const sev = `CASE f.severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END`;
  const [findings, snapshots, importErrors, comparison, systems, filterNames] = await Promise.all([
    q(`SELECT ${FINDINGS_COLUMNS}, f.details ${FINDINGS_FROM} WHERE ${where} ORDER BY ${sev}, f.finding_type, f.finding_key`, params),
    q(`SELECT COALESCE(e.employee_key, s.employee_key_raw) AS employee_key, COALESCE(e.full_name, s.full_name_raw) AS employee_name, d.name AS department, p.name AS position,
              COALESCE(sy.code, s.system_raw) AS system, s.login, COALESCE(ar.role_code, s.role_raw) AS role, COALESCE(m.code, s.module_raw) AS module,
              COALESCE(o.code, s.operation_raw) AS operation, o.name AS operation_name, s.assigned_at, s.result_status, s.normalized_status, s.review_reason, s.expanded_from_role,
              b.file_name, ir.row_number
         FROM access_snapshots s LEFT JOIN employees e ON e.id = s.employee_id LEFT JOIN departments d ON d.id = e.department_id LEFT JOIN positions p ON p.id = e.position_id
         LEFT JOIN systems sy ON sy.id = s.system_id LEFT JOIN access_roles ar ON ar.id = s.role_id LEFT JOIN modules m ON m.id = s.module_id
         LEFT JOIN operations o ON o.id = s.operation_id JOIN import_batches b ON b.id = s.batch_id JOIN import_rows ir ON ir.id = s.source_row_id
        WHERE s.audit_id = $1 AND ($2::uuid[] IS NULL OR s.system_id = ANY($2)) AND ($3::text IS NULL OR s.system_id = $3::uuid)
        ORDER BY s.access_key`, [auditId, scope, filters.system_id ?? null]),
    q(`SELECT b.file_name, r.sheet_name, r.row_number, r.normalized_status, r.error_column, r.error_text FROM import_rows r JOIN import_batches b ON b.id = r.batch_id
        WHERE b.audit_id = $1 AND r.normalized_status <> 'OK' ORDER BY b.file_name, r.row_number`, [auditId]),
    one(`SELECT c.*, fa.name AS from_name, fa.as_of_date AS from_date FROM audit_comparisons c JOIN audit_runs fa ON fa.id = c.from_audit_id
          WHERE c.to_audit_id = $1 ORDER BY c.created_at DESC LIMIT 1`, [auditId]),
    q(`SELECT DISTINCT sy.code, sy.name FROM access_snapshots s JOIN systems sy ON sy.id = s.system_id WHERE s.audit_id = $1 ORDER BY sy.code`, [auditId]),
    describeFilters(filters),
  ]);
  const comparisonItems = comparison ? await q('SELECT change_type, access_key, before_json, after_json FROM comparison_items WHERE comparison_id = $1 ORDER BY change_type, access_key', [comparison.id]) : [];
  const exceptions = (audit.rules_snapshot?.exceptions ?? []) as any[];
  const usedExceptionIds = new Set(findings.map((f) => f.exception_id).filter(Boolean));
  const excRows = exceptions.length ? await q(`SELECT x.*, e.employee_key, e.full_name, s.code AS system_code, ar.role_code, o.code AS operation_code
                                                 FROM exceptions x JOIN employees e ON e.id = x.employee_id JOIN systems s ON s.id = x.system_id
                                                 LEFT JOIN access_roles ar ON ar.id = x.role_id LEFT JOIN operations o ON o.id = x.operation_id
                                                WHERE x.id = ANY($1) ORDER BY x.valid_to`, [exceptions.map((x) => x.id)]) : [];
  return { audit, filters, filterNames, findings, snapshots, importErrors, comparison, comparisonItems, systems, exceptions: excRows, usedExceptionIds };
}

async function describeFilters(f: FindingFilters): Promise<string[]> {
  const out: string[] = [];
  if (f.system_id) out.push(`Система: ${(await one('SELECT code FROM systems WHERE id = $1', [f.system_id]))?.code ?? f.system_id}`);
  if (f.department_id) out.push(`Подразделение: ${(await one('SELECT name FROM departments WHERE id = $1', [f.department_id]))?.name ?? ''}`);
  if (f.position_id) out.push(`Должность: ${(await one('SELECT name FROM positions WHERE id = $1', [f.position_id]))?.name ?? ''}`);
  if (f.severity) out.push(`Критичность: ${f.severity.split(',').map((s) => SEVERITY_RU[s] ?? s).join(', ')}`);
  if (f.finding_type) out.push(`Тип: ${f.finding_type.split(',').map((s) => TYPE_RU[s] ?? s).join(', ')}`);
  if (f.outcome) out.push(`Результат: ${f.outcome.split(',').map((s) => OUTCOME_RU[s] ?? s).join(', ')}`);
  if (f.status) out.push(`Статус обработки: ${f.status.split(',').map((s) => FSTATUS_RU[s] ?? s).join(', ')}`);
  if (f.owner_user_id) out.push(`Владелец: ${(await one('SELECT full_name FROM users WHERE id = $1', [f.owner_user_id]))?.full_name ?? ''}`);
  if (f.search) out.push(`Поиск: «${f.search}»`);
  return out;
}

type ReportData = Awaited<ReturnType<typeof loadReportData>>;

function paramsRows(d: ReportData, req: Request): Array<[string, string]> {
  const a = d.audit;
  return [
    ['Аудит', a.name],
    ['Дата среза (as-of)', a.as_of_date],
    ['Системы', d.systems.map((s) => `${s.code} — ${s.name}`).join('; ') || '—'],
    ['Версия матрицы', `${a.matrix_version} — ${a.matrix_name}`],
    ['Контрольная сумма матрицы', a.matrix_checksum ?? '—'],
    ['Контрольная сумма версии правил (SoD, политика, исключения)', a.rules_checksum ?? '—'],
    ['Контрольная сумма исходного пакета', a.package_checksum ?? '—'],
    ['Контрольная сумма результатов', a.result_checksum ?? '—'],
    ['Файлы пакета', (a.summary?.files ?? []).map((f: any) => `${f.name} (SHA-256 ${f.sha256})`).join('\n')],
    ['Запущен', `${a.started_by_name ?? ''} ${a.started_at ? new Date(a.started_at).toLocaleString('ru-RU') : ''}`],
    ['Отчёт сформирован', `${new Date().toLocaleString('ru-RU')}, ${req.user!.fullName} (${req.user!.username})`],
    ['Фильтры отчёта', d.filterNames.join('; ') || 'нет'],
  ];
}

async function saveReport(req: Request, auditId: string, format: 'XLSX' | 'PDF', buf: Buffer, fileName: string, filters: unknown) {
  const dir = path.join(config.dataDir, 'reports', auditId);
  fs.mkdirSync(dir, { recursive: true });
  const stored = path.join(dir, fileName);
  fs.writeFileSync(stored, buf, { mode: 0o600 });
  const hash = sha256(buf);
  await q('INSERT INTO reports (audit_id, format, file_name, stored_path, sha256, filters, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7)',
    [auditId, format, fileName, path.relative(config.dataDir, stored), hash, JSON.stringify(filters), req.user!.id]);
  await logActivity(req, 'REPORT_EXPORTED', { category: 'AUDIT', entityType: 'audit', entityId: auditId, after: { format, fileName, sha256: hash, filters } });
}

const stamp = () => new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');

// ---------- XLSX ----------
reportsRouter.get('/audits/:id/report.xlsx', requirePerm('reports.export', 'findings.scoped'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const d = await loadReportData(req, id);
  const wb = new ExcelJS.Workbook();
  wb.creator = 'Access Rights Auditor';
  wb.created = new Date();
  const header = (ws: ExcelJS.Worksheet, cols: Array<[string, number]>) => {
    ws.columns = cols.map(([h, w]) => ({ header: h, width: w }));
    ws.getRow(1).font = { bold: true };
    ws.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFE7ECF3' } };
    ws.views = [{ state: 'frozen', ySplit: 1 }];
    ws.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: cols.length } };
  };
  // Значения пишутся как строки/числа — формулы в отчёт не попадают.
  const s = d.audit.summary ?? {};
  const sum = wb.addWorksheet('Сводка');
  sum.columns = [{ width: 48 }, { width: 90 }];
  sum.addRow(['Отчёт аудита полномочий — Access Rights Auditor']).font = { bold: true, size: 14 };
  sum.addRow([]);
  for (const [k, v] of paramsRows(d, req)) sum.addRow([k, v]).getCell(2).alignment = { wrapText: true };
  sum.addRow([]);
  sum.addRow(['Показатель', 'Значение']).font = { bold: true };
  const metrics: Array<[string, unknown]> = [
    ['Атомарных назначений', s.totalAccesses], ['Сотрудников', s.employees],
    ['Соответствует', s.byResult?.COMPLIANT], ['Нарушение', s.byResult?.VIOLATION], ['Покрыто исключением', s.byResult?.COVERED_BY_EXCEPTION], ['Требует проверки', s.byResult?.NEEDS_REVIEW],
    ['Находок всего', s.findings], ...Object.entries(SEVERITY_RU).map(([k, v]) => [`Находок: ${v}`, s.bySeverity?.[k] ?? 0] as [string, unknown]),
    ['Уволенных с доступом', s.terminatedWithAccess], ['Конфликтов SoD', s.sodConflicts], ['Истёкших исключений, затронувших назначения', s.expiredExceptionsMatched],
    ['Находок в отчёте (с учётом фильтров)', d.findings.length],
  ];
  for (const [k, v] of metrics) sum.addRow([k, v ?? 0]);
  sum.addRow([]);
  sum.addRow(['Тип находки', 'Количество']).font = { bold: true };
  for (const [k, v] of Object.entries(s.byType ?? {})) sum.addRow([TYPE_RU[k] ?? k, v]);

  const ws1 = wb.addWorksheet('Все назначения');
  header(ws1, [['Таб. №', 12], ['ФИО', 30], ['Подразделение', 24], ['Должность', 22], ['Система', 12], ['Логин', 14], ['Роль', 18], ['Модуль', 14], ['Операция', 18], ['Наименование операции', 28], ['Дата назначения', 14], ['Результат', 20], ['Нормализация', 14], ['Причина проверки', 40], ['Развёрнуто из роли', 10], ['Файл', 24], ['Строка', 8]]);
  for (const r of d.snapshots) ws1.addRow([r.employee_key, r.employee_name, r.department, r.position, r.system, r.login, r.role, r.module, r.operation, r.operation_name, r.assigned_at, RESULT_RU[r.result_status] ?? r.result_status, r.normalized_status, r.review_reason, r.expanded_from_role ? 'да' : '', r.file_name, r.row_number]);

  const findingCols: Array<[string, number]> = [['Критичность', 14], ['Тип', 30], ['Результат', 26], ['Код правила', 12], ['Таб. №', 12], ['ФИО', 28], ['Подразделение', 22], ['Должность', 22], ['Система', 12], ['Владелец системы', 22], ['Логин', 14], ['Роль', 16], ['Операция', 18], ['Ожидалось', 50], ['Фактически', 50], ['Объяснение', 70], ['Статус обработки', 16]];
  const findingRow = (f: any) => [SEVERITY_RU[f.severity], TYPE_RU[f.finding_type] ?? f.finding_type, OUTCOME_RU[f.outcome], f.rule_code, f.employee_key ?? f.employee_key_raw, f.employee_name, f.department_name, f.position_name, f.system_code, f.owner_name, f.login, f.role_code, f.operation_code, f.expected, f.actual, f.explanation, FSTATUS_RU[f.status]];
  const ws2 = wb.addWorksheet('Нарушения');
  header(ws2, findingCols);
  for (const f of d.findings.filter((x) => !x.finding_type.startsWith('SOD'))) ws2.addRow(findingRow(f));

  const ws3 = wb.addWorksheet('SoD');
  header(ws3, [['Критичность', 14], ['Правило', 18], ['Результат', 26], ['Таб. №', 12], ['ФИО', 28], ['Подразделение', 22], ['Сторона 1', 60], ['Сторона 2', 60], ['Прочие стороны', 40], ['Объяснение', 70], ['Статус обработки', 16]]);
  for (const f of d.findings.filter((x) => x.finding_type.startsWith('SOD'))) {
    const sides = (f.details?.sides ?? []) as Array<{ side: number; assignments: Array<{ label: string }> }>;
    const sideText = (n: number) => sides.filter((x) => x.side === n).flatMap((x) => x.assignments.map((a) => a.label)).join('\n');
    ws3.addRow([SEVERITY_RU[f.severity], f.rule_code, OUTCOME_RU[f.outcome], f.employee_key, f.employee_name, f.department_name, sideText(1), sideText(2),
      sides.filter((x) => x.side > 2).map((x) => `Сторона ${x.side}: ${x.assignments.map((a) => a.label).join('; ')}`).join('\n'), f.explanation, FSTATUS_RU[f.status]]);
  }

  const ws4 = wb.addWorksheet('Исключения');
  header(ws4, [['Заявка/решение', 18], ['Таб. №', 12], ['ФИО', 28], ['Система', 12], ['Роль', 16], ['Операция', 16], ['Причина', 40], ['Автор', 20], ['Согласовал', 20], ['С', 12], ['По', 12], ['Компенсирующий контроль', 40], ['Статус', 12], ['Состояние на дату аудита', 22], ['Применено в аудите', 12]]);
  for (const x of d.exceptions) {
    const state = x.status !== 'APPROVED' ? x.status : x.valid_to < d.audit.as_of_date ? 'Истекло' : x.valid_from > d.audit.as_of_date ? 'Ещё не действует' : 'Действует';
    ws4.addRow([x.ticket_ref, x.employee_key, x.full_name, x.system_code, x.role_code, x.operation_code, x.reason, x.author, x.approved_by, x.valid_from, x.valid_to, x.compensating_control, x.status, state, d.usedExceptionIds.has(x.id) ? 'да' : '']);
  }

  const ws5 = wb.addWorksheet('Ошибки импорта');
  header(ws5, [['Файл', 28], ['Лист', 14], ['Строка', 8], ['Статус', 14], ['Колонка', 22], ['Описание', 100]]);
  for (const r of d.importErrors) ws5.addRow([r.file_name, r.sheet_name, r.row_number, IMPORT_STATUS_RU[r.normalized_status] ?? r.normalized_status, r.error_column, r.error_text]);

  const ws6 = wb.addWorksheet('Изменения');
  header(ws6, [['Тип изменения', 26], ['Ключ', 60], ['Было', 60], ['Стало', 60]]);
  if (d.comparison) {
    ws6.addRow([`Сравнение с аудитом «${d.comparison.from_name}» (${d.comparison.from_date})`]);
    const brief = (j: any) => !j ? '' : j.finding_type ? `${TYPE_RU[j.finding_type] ?? j.finding_type}; ${SEVERITY_RU[j.severity]}; ${j.full_name ?? ''}` :
      `${j.employee_name ?? ''}; ${j.system}/${j.role}/${j.operation ?? ''}; подразделение: ${j.department ?? ''}; должность: ${j.position ?? ''}; результат: ${RESULT_RU[j.result_status] ?? ''}${j.changed ? `; изменено: ${j.changed.join(', ')}` : ''}`;
    for (const i of d.comparisonItems) ws6.addRow([CHANGE_RU[i.change_type] ?? i.change_type, i.access_key, brief(i.before_json), brief(i.after_json)]);
  } else {
    ws6.addRow(['Сравнение для этого аудита не выполнялось (раздел «История»).']);
  }

  const buf = Buffer.from(await wb.xlsx.writeBuffer());
  const fileName = `ARA_${d.audit.as_of_date}_${stamp()}.xlsx`;
  await saveReport(req, id, 'XLSX', buf, fileName, d.filters);
  res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  res.setHeader('Content-Disposition', `attachment; filename="${fileName}"`);
  res.send(buf);
});

// ---------- PDF ----------
const FONT = require.resolve('dejavu-fonts-ttf/ttf/DejaVuSans.ttf');
const FONT_BOLD = require.resolve('dejavu-fonts-ttf/ttf/DejaVuSans-Bold.ttf');

reportsRouter.get('/audits/:id/report.pdf', requirePerm('reports.export', 'findings.scoped'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const d = await loadReportData(req, id);
  const s = d.audit.summary ?? {};
  const doc = new PDFDocument({ size: 'A4', margin: 50, info: { Title: `Отчёт аудита полномочий — ${d.audit.name}`, Author: req.user!.fullName, Creator: 'Access Rights Auditor' }, bufferPages: true });
  doc.registerFont('R', FONT);
  doc.registerFont('B', FONT_BOLD);
  const chunks: Buffer[] = [];
  doc.on('data', (c) => chunks.push(c));
  const done = new Promise<Buffer>((resolve) => doc.on('end', () => resolve(Buffer.concat(chunks))));
  const W = doc.page.width - 100;

  // Титульная страница
  doc.font('B').fontSize(22).text('Отчёт аудита банковских полномочий', 50, 180, { width: W, align: 'center' });
  doc.moveDown(0.5).font('R').fontSize(13).text('Access Rights Auditor (ARA)', { width: W, align: 'center' });
  doc.moveDown(2).font('B').fontSize(15).text(d.audit.name, { width: W, align: 'center' });
  doc.moveDown(0.5).font('R').fontSize(12).text(`Дата среза: ${d.audit.as_of_date}`, { width: W, align: 'center' });
  doc.text(`Системы: ${d.systems.map((x) => x.code).join(', ') || '—'}`, { width: W, align: 'center' });
  doc.text(`Версия матрицы: ${d.audit.matrix_version}`, { width: W, align: 'center' });
  doc.moveDown(6).fontSize(10).text(`Сформирован: ${new Date().toLocaleString('ru-RU')}`, { width: W, align: 'center' });
  doc.text(`Автор: ${req.user!.fullName} (${req.user!.username})`, { width: W, align: 'center' });
  doc.moveDown(1).fontSize(8).fillColor('#555').text(`Контрольная сумма исходного пакета (SHA-256): ${d.audit.package_checksum}`, { width: W, align: 'center' });
  doc.fillColor('black');

  const h = (t: string) => { doc.moveDown(1).font('B').fontSize(14).text(t, { width: W }).moveDown(0.4).font('R').fontSize(10); };
  const kv = (rows: Array<[string, string]>) => {
    for (const [k, v] of rows) {
      if (doc.y > doc.page.height - 90) doc.addPage();
      const y = doc.y;
      doc.font('B').fontSize(9).text(k, 50, y, { width: 170 });
      const y1 = doc.y;
      doc.font('R').fontSize(9).text(v || '—', 230, y, { width: W - 180 });
      doc.y = Math.max(y1, doc.y) + 3;
      doc.x = 50;
    }
  };

  doc.addPage();
  h('1. Параметры аудита');
  kv(paramsRows(d, req));

  h('2. Сводные показатели');
  kv([
    ['Атомарных назначений', String(s.totalAccesses ?? 0)],
    ['Сотрудников', String(s.employees ?? 0)],
    ['Соответствует', String(s.byResult?.COMPLIANT ?? 0)],
    ['Нарушение', String(s.byResult?.VIOLATION ?? 0)],
    ['Покрыто исключением', String(s.byResult?.COVERED_BY_EXCEPTION ?? 0)],
    ['Требует проверки', String(s.byResult?.NEEDS_REVIEW ?? 0)],
    ['Находки по критичности', Object.entries(SEVERITY_RU).map(([k, v]) => `${v}: ${s.bySeverity?.[k] ?? 0}`).join('; ')],
    ['Уволенных с доступом', String(s.terminatedWithAccess ?? 0)],
    ['Конфликтов SoD', String(s.sodConflicts ?? 0)],
    ['Истёкших исключений', String(s.expiredExceptionsMatched ?? 0)],
    ['Находки по типам', Object.entries(s.byType ?? {}).map(([k, v]) => `${TYPE_RU[k] ?? k}: ${v}`).join('; ')],
    ['Ошибок/предупреждений импорта', String(d.importErrors.length)],
  ]);
  if (d.comparison) {
    h('Изменения относительно предыдущего аудита');
    kv(Object.entries(d.comparison.summary ?? {}).map(([k, v]) => [CHANGE_RU[k] ?? k, String(v)] as [string, string]));
  }

  h('3. Критические находки');
  const critical = d.findings.filter((f) => (f.severity === 'CRITICAL' || f.severity === 'HIGH') && f.outcome !== 'COVERED_BY_EXCEPTION');
  if (!critical.length) doc.text('Критических и высоких находок (с учётом фильтров) не выявлено.');
  const MAX = 300;
  critical.slice(0, MAX).forEach((f, i) => {
    if (doc.y > doc.page.height - 140) doc.addPage();
    doc.font('B').fontSize(9).fillColor(f.severity === 'CRITICAL' ? '#a40000' : '#9a4a00')
      .text(`${i + 1}. [${SEVERITY_RU[f.severity]}] ${TYPE_RU[f.finding_type] ?? f.finding_type} — ${f.employee_name ?? '—'} (${f.employee_key ?? f.employee_key_raw ?? '—'}), ${f.system_code ?? ''}`, { width: W });
    doc.fillColor('black').font('R').fontSize(8.5);
    doc.text(`Результат: ${OUTCOME_RU[f.outcome]}. Код правила: ${f.rule_code}. Статус: ${FSTATUS_RU[f.status]}`, { width: W });
    if (f.actual) doc.text(`Фактически: ${f.actual}`, { width: W });
    if (f.expected) doc.text(`Ожидалось: ${f.expected}`, { width: W });
    doc.text(`Объяснение: ${f.explanation}`, { width: W });
    doc.moveDown(0.5);
  });
  if (critical.length > MAX) doc.text(`… и ещё ${critical.length - MAX} находок — полный перечень в XLSX-отчёте.`);

  doc.addPage();
  h('4. Методология');
  doc.text([
    '1. Исходные выгрузки фактических доступов (XLSX/CSV) сохранены в неизменном виде; для каждого файла вычислена контрольная сумма SHA-256. Формулы и макросы не исполнялись.',
    '2. Строки нормализованы в атомарные назначения «сотрудник – система – логин – роль – модуль – операция». Составные профили ролей развёрнуты в операции по справочнику состава ролей.',
    '3. Сотрудники сопоставлены только по табельному номеру / уникальному ID (с учётом таблицы алиасов). ФИО используется как вспомогательный атрибут.',
    '4. Неизвестные и неоднозначные записи получили статус «Требует проверки» и исключены из автоматического вывода о нарушении.',
    `5. Каждое назначение сверено с утверждённой версией матрицы ${d.audit.matrix_version}, действующей на дату ${d.audit.as_of_date}: проверены статус сотрудника, разрешённость роли, операции и области действия (подразделение/должность), явные запреты.`,
    '6. Найденные отклонения сопоставлены с журналом согласованных исключений: действующее исключение не удаляет факт превышения, а маркирует его; истёкшие исключения не считаются действующими.',
    '7. Выполнены групповые SoD-проверки: конфликт фиксируется, если у сотрудника присутствуют все стороны конфликтующей комбинации; показываются исходные назначения каждой стороны.',
    '8. Критичность назначается настраиваемой политикой с учётом типа находки и уровня риска операции.',
    '9. Результаты сохранены как неизменяемый снимок; контрольные суммы матрицы, версии правил, пакета и результатов позволяют подтвердить воспроизводимость.',
  ].join('\n\n'), { width: W });
  h('5. Ограничения');
  doc.text([
    '• Анализ выполнен только по предоставленным файлам; прямое подключение к банковским системам, AD или IAM не выполнялось.',
    '• Качество выводов зависит от полноты и актуальности матрицы полномочий и кадрового справочника. Назначения вне матрицы помечаются «Требует проверки», а не нарушением.',
    '• Система не изменяет и не отзывает доступы в целевых системах; решение по каждой находке принимает ответственное лицо.',
    '• «Остаточный доступ после перевода» является кандидатом и требует подтверждения владельцем системы.',
    '• Отчёт не использует AI-модели в принятии решений; анализ выполнен детерминированным движком правил.',
  ].join('\n\n'), { width: W });

  // Нумерация страниц
  const range = doc.bufferedPageRange();
  for (let i = range.start; i < range.start + range.count; i++) {
    doc.switchToPage(i);
    doc.font('R').fontSize(7.5).fillColor('#666').text(`ARA · ${d.audit.name} · ${d.audit.as_of_date} · стр. ${i + 1} из ${range.count}`, 50, doc.page.height - 35, { width: W, align: 'center', lineBreak: false });
  }
  doc.end();
  const buf = await done;
  const fileName = `ARA_${d.audit.as_of_date}_${stamp()}.pdf`;
  await saveReport(req, id, 'PDF', buf, fileName, d.filters);
  res.setHeader('Content-Type', 'application/pdf');
  res.setHeader('Content-Disposition', `attachment; filename="${fileName}"`);
  res.send(buf);
});

reportsRouter.get('/audits/:id/reports', requirePerm('audit.view'), async (req, res) => {
  res.json(await q(`SELECT r.id, r.format, r.file_name, r.sha256, r.filters, r.created_at, u.full_name AS created_by_name FROM reports r LEFT JOIN users u ON u.id = r.created_by WHERE r.audit_id = $1 ORDER BY r.created_at DESC`, [parse(zId, req.params.id)]));
});
