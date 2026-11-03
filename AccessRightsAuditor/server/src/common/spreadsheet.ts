import ExcelJS from 'exceljs';
import { parse as parseCsv } from 'csv-parse/sync';
import { badRequest } from './http';

export interface Sheet {
  name: string;
  /** Номер строки в исходном файле (1-based) для каждой строки rows. */
  rowNumbers: number[];
  rows: string[][];
}

export interface Workbook {
  type: 'XLSX' | 'CSV';
  sheets: Sheet[];
  warnings: string[];
}

const pad = (n: number) => String(n).padStart(2, '0');
export const toIsoDate = (d: Date) => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;

export function detectFileType(name: string, buf: Buffer): 'XLSX' | 'CSV' {
  const lower = name.toLowerCase();
  if (/\.(xlsm|xlsb|xls|xltm)$/.test(lower)) throw badRequest('Файлы с макросами и старые форматы Excel (xls, xlsm, xlsb) не принимаются. Сохраните выгрузку как .xlsx или .csv');
  if (lower.endsWith('.xlsx')) {
    if (buf.length < 4 || buf.readUInt32LE(0) !== 0x04034b50) throw badRequest('Файл .xlsx повреждён или не является книгой Excel');
    if (buf.includes('vbaProject.bin') || buf.includes('macroEnabled')) throw badRequest('Книга содержит макросы (VBA) — загрузка запрещена');
    return 'XLSX';
  }
  if (lower.endsWith('.csv') || lower.endsWith('.txt')) {
    if (buf.length >= 4 && buf.readUInt32LE(0) === 0x04034b50) throw badRequest('Файл с расширением .csv является архивом — тип файла не соответствует содержимому');
    if (buf.subarray(0, 8192).includes(0)) throw badRequest('CSV-файл содержит двоичные данные');
    return 'CSV';
  }
  throw badRequest('Поддерживаются только файлы .xlsx и .csv');
}

function cellToString(v: ExcelJS.CellValue, onFormula: () => void): string {
  if (v === null || v === undefined) return '';
  if (v instanceof Date) return toIsoDate(v);
  if (typeof v === 'object') {
    const o = v as any;
    if ('formula' in o || 'sharedFormula' in o) {
      onFormula(); // формулы не исполняются: берётся только сохранённое значение
      return o.result === undefined || o.result === null ? '' : cellToString(o.result, onFormula);
    }
    if ('richText' in o) return o.richText.map((t: any) => t.text).join('');
    if ('text' in o) return String(o.text);
    if ('error' in o) return '';
    return '';
  }
  return String(v).trim();
}

export async function readWorkbook(name: string, buf: Buffer, opts: { maxRows?: number } = {}): Promise<Workbook> {
  const type = detectFileType(name, buf);
  const warnings: string[] = [];
  const maxRows = opts.maxRows ?? 500_000;
  if (type === 'XLSX') {
    const wb = new ExcelJS.Workbook();
    try {
      await wb.xlsx.load(buf as any);
    } catch {
      throw badRequest('Не удалось прочитать книгу Excel: файл повреждён или имеет неподдерживаемый формат');
    }
    const sheets: Sheet[] = [];
    let formulaCells = 0;
    wb.eachSheet((ws) => {
      const rows: string[][] = [];
      const rowNumbers: number[] = [];
      ws.eachRow({ includeEmpty: false }, (row, rowNumber) => {
        if (rows.length >= maxRows) return;
        const values: string[] = [];
        const count = Math.max(row.cellCount, row.actualCellCount);
        for (let c = 1; c <= count; c++) values.push(cellToString(row.getCell(c).value, () => formulaCells++));
        if (values.some((x) => x !== '')) {
          rows.push(values);
          rowNumbers.push(rowNumber);
        }
      });
      sheets.push({ name: ws.name, rows, rowNumbers });
    });
    if (formulaCells) warnings.push(`Обнаружено ячеек с формулами: ${formulaCells}. Формулы не исполнялись, использованы сохранённые в файле значения.`);
    return { type, sheets, warnings };
  }

  // CSV: UTF-8 (с BOM или без) либо Windows-1251.
  let text: string;
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(buf);
  } catch {
    text = new TextDecoder('windows-1251').decode(buf);
    warnings.push('Кодировка файла определена как Windows-1251');
  }
  text = text.replace(/^﻿/, '');
  const firstLine = text.split(/\r?\n/, 1)[0] ?? '';
  const delimiter = [';', ',', '\t', '|'].map((d) => [d, firstLine.split(d).length] as const).sort((a, b) => b[1] - a[1])[0][0];
  let records: Array<{ record: string[]; info: { lines: number } }>;
  try {
    records = parseCsv(text, { delimiter, relax_column_count: true, relax_quotes: true, skip_empty_lines: false, info: true, bom: true }) as any;
  } catch (e: any) {
    throw badRequest(`Ошибка разбора CSV: ${e.message}`);
  }
  const rows: string[][] = [];
  const rowNumbers: number[] = [];
  for (const r of records) {
    if (rows.length >= maxRows) break;
    const vals = r.record.map((x) => String(x ?? '').trim());
    if (vals.some((x) => x !== '')) {
      rows.push(vals);
      rowNumbers.push(r.info.lines);
    }
  }
  return { type, sheets: [{ name: 'CSV', rows, rowNumbers }], warnings };
}

/** Разбор даты из выгрузки: ГГГГ-ММ-ДД, ДД.ММ.ГГГГ, ДД/ММ/ГГГГ, серийный номер Excel. */
export function parseDateValue(v: string | null | undefined): { ok: true; value: string | null } | { ok: false } {
  if (v === null || v === undefined) return { ok: true, value: null };
  const s = String(v).trim();
  if (!s) return { ok: true, value: null };
  let y: number, m: number, d: number;
  let mt = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$/);
  if (mt) { y = +mt[1]; m = +mt[2]; d = +mt[3]; }
  else if ((mt = s.match(/^(\d{1,2})[./](\d{1,2})[./](\d{4})(?:\s.*)?$/))) { d = +mt[1]; m = +mt[2]; y = +mt[3]; }
  else if (/^\d{5}(\.\d+)?$/.test(s)) {
    const date = new Date(Date.UTC(1899, 11, 30) + Math.floor(Number(s)) * 86400000);
    return { ok: true, value: toIsoDate(date) };
  } else return { ok: false };
  const dt = new Date(Date.UTC(y, m - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d || y < 1900 || y > 2200) return { ok: false };
  return { ok: true, value: toIsoDate(dt) };
}

export const normHeader = (h: string) => h.toLowerCase().replace(/ё/g, 'е').replace(/[\s_\-./()№#]+/g, '');

/** Автоподбор колонки по синонимам заголовка. */
export function guessColumn(headers: string[], synonyms: string[]): number {
  const norm = headers.map(normHeader);
  for (const s of synonyms.map(normHeader)) {
    const i = norm.indexOf(s);
    if (i >= 0) return i;
  }
  for (const s of synonyms.map(normHeader)) {
    const i = norm.findIndex((h) => h.includes(s));
    if (i >= 0) return i;
  }
  return -1;
}

/** Табличный файл с фиксированными колонками (справочники, матрица): заголовок — первая строка. */
export function readTable(sheet: Sheet, columns: Record<string, string[]>): { headers: string[]; records: Array<{ rowNumber: number; values: Record<string, string> }>; missing: string[] } {
  const [headerRow, ...data] = sheet.rows;
  const headers = headerRow ?? [];
  const idx: Record<string, number> = {};
  const missing: string[] = [];
  for (const [key, syn] of Object.entries(columns)) {
    idx[key] = guessColumn(headers, [key, ...syn]);
    if (idx[key] < 0) missing.push(key);
  }
  const records = data.map((r, i) => ({
    rowNumber: sheet.rowNumbers[i + 1],
    values: Object.fromEntries(Object.entries(idx).map(([k, j]) => [k, j >= 0 ? (r[j] ?? '').trim() : ''])),
  }));
  return { headers, records, missing };
}
