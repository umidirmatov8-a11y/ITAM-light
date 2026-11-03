import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { DataTable } from '../components/crud';
import { Badge, ErrorBox, Field, Loading, Modal, useLoad } from '../components/ui';
import { ROW_STATUS } from '../i18n';
import { useLookups } from '../lookups';

type Columns = Record<string, number>;

/** Мастер сопоставления колонок: лист → строка заголовка → поля → предпросмотр → обработка. */
export function ImportWizard({ batch, onClose, onDone }: { batch: any; onClose: () => void; onDone: () => void }) {
  const l = useLookups();
  const [headerRow, setHeaderRow] = useState<number>(batch.mapping_json?.headerRow ?? 1);
  const preview = useLoad<any>(() => api.get(`/batches/${batch.id}/preview?headerRow=${headerRow}`), [batch.id, headerRow]);
  const templates = useLoad<any[]>(() => api.get('/import-templates'));
  const [sheet, setSheet] = useState<string>(batch.mapping_json?.sheet ?? '');
  const [columns, setColumns] = useState<Columns>(batch.mapping_json?.columns ?? {});
  const [defaultSystemId, setDefaultSystem] = useState<string>(batch.mapping_json?.defaultSystemId ?? '');
  const [split, setSplit] = useState<boolean>(batch.mapping_json?.splitMultiValues ?? true);
  const [expand, setExpand] = useState<boolean>(batch.mapping_json?.expandRoles ?? true);
  const [templateName, setTemplateName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const sheetData = useMemo(() => preview.data?.sheets.find((s: any) => s.name === sheet), [preview.data, sheet]);
  useEffect(() => {
    if (!preview.data) return;
    const first = preview.data.sheets.find((s: any) => s.name === sheet) ?? preview.data.sheets.find((s: any) => s.totalRows > 0) ?? preview.data.sheets[0];
    if (first && first.name !== sheet) setSheet(first.name);
    if (first && !batch.mapping_json && Object.keys(columns).length === 0) setColumns(first.suggested);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview.data]);

  const fields: Record<string, { label: string; required: boolean }> = preview.data?.fields ?? {};
  const headers: string[] = sheetData?.headers ?? [];
  const applyTemplate = (id: string) => {
    const t = templates.data?.find((x) => x.id === id);
    if (!t) return;
    const m = t.mapping;
    // Колонки шаблона сопоставляются по названию заголовка, а не по номеру.
    const byName: Columns = {};
    for (const [k, idx] of Object.entries(m.columns ?? {}) as Array<[string, number]>) {
      const name = m.headers?.[idx];
      byName[k] = name ? headers.findIndex((h) => h === name) : idx;
    }
    setColumns(byName);
    setDefaultSystem(m.defaultSystemId ?? '');
    setSplit(m.splitMultiValues ?? true);
    setExpand(m.expandRoles ?? true);
    if (m.headerRow) setHeaderRow(m.headerRow);
  };

  const process = async () => {
    setError(null);
    setBusy(true);
    try {
      const r = await api.post(`/batches/${batch.id}/process`, {
        sheet, headerRow, columns, defaultSystemId: defaultSystemId || null, splitMultiValues: split, expandRoles: expand,
        saveTemplateName: templateName.trim() || undefined,
      });
      setResult(r);
      onDone();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const mapped = new Set(Object.values(columns).filter((v) => v >= 0));
  return (
    <Modal wide title={`Сопоставление колонок: ${batch.file_name}`} onClose={onClose}
      footer={result ? <button className="btn primary" onClick={onClose}>Готово</button> : <><button className="btn" onClick={onClose}>Отмена</button><button className="btn primary" disabled={busy || !sheet} onClick={process}>{busy ? 'Обработка…' : 'Обработать файл'}</button></>}>
      <ErrorBox error={preview.error ?? error} />
      {preview.data?.warnings?.map((w: string) => <div key={w} className="alert warn">{w}</div>)}
      {!preview.data ? <Loading /> : result ? (
        <div>
          <div className={`alert ${result.errors ? 'warn' : 'ok'}`}>Файл обработан: строк {result.total}, без замечаний {result.ok}, с предупреждениями {result.warnings}, дублей {result.duplicates}, ошибок (карантин) {result.errors}. Создано атомарных назначений: {result.snapshots}.</div>
          <p className="muted">Строки с ошибками не прервали импорт; они помещены в карантин и видны на вкладке «Ошибки импорта» с указанием листа, строки и колонки. Неоднозначные записи получили статус «Требует проверки».</p>
        </div>
      ) : (
        <>
          <div className="grid cols-3">
            <Field label="Лист">
              <select value={sheet} onChange={(e) => setSheet(e.target.value)}>
                {preview.data.sheets.map((s: any) => <option key={s.name} value={s.name}>{s.name} ({s.totalRows} строк)</option>)}
              </select>
            </Field>
            <Field label="Строка заголовка"><input type="number" min={1} value={headerRow} onChange={(e) => setHeaderRow(Math.max(1, Number(e.target.value) || 1))} /></Field>
            <Field label="Шаблон сопоставления">
              <select value="" onChange={(e) => applyTemplate(e.target.value)}>
                <option value="">— применить шаблон —</option>
                {(templates.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </Field>
          </div>
          <h3 style={{ marginTop: 16 }}>Поля</h3>
          <div className="form" style={{ gridTemplateColumns: 'repeat(4, minmax(0,1fr))' }}>
            {Object.entries(fields).map(([k, f]) => (
              <Field key={k} label={f.label} required={f.required && !(k === 'system' && defaultSystemId)}>
                <select value={columns[k] ?? -1} onChange={(e) => setColumns({ ...columns, [k]: Number(e.target.value) })}>
                  <option value={-1}>— не используется —</option>
                  {headers.map((h, i) => <option key={i} value={i}>{h || `Колонка ${i + 1}`}</option>)}
                </select>
              </Field>
            ))}
            <Field label="Система по умолчанию" hint="Если в файле нет колонки «Система» (выгрузка одной системы)">
              <select value={defaultSystemId} onChange={(e) => setDefaultSystem(e.target.value)}>
                <option value="">— нет —</option>
                {(l?.systems ?? []).map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
              </select>
            </Field>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <label className="check"><input type="checkbox" checked={split} onChange={(e) => setSplit(e.target.checked)} /> Разделять несколько значений в ячейке (; | перенос строки) на отдельные права</label>
            <label className="check"><input type="checkbox" checked={expand} onChange={(e) => setExpand(e.target.checked)} /> Разворачивать роль без операций в её состав</label>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <Field label="Сохранить сопоставление как шаблон (необязательно)"><input value={templateName} onChange={(e) => setTemplateName(e.target.value)} placeholder="Например: Smart Bank — стандартная выгрузка" style={{ width: 380 }} /></Field>
          </div>
          <h3 style={{ marginTop: 16 }}>Предпросмотр (первые строки)</h3>
          <div className="table-wrap" style={{ maxHeight: 300, border: '1px solid var(--border)', borderRadius: 6 }}>
            <table className="t">
              <thead><tr>{headers.map((h, i) => <th key={i} style={{ background: mapped.has(i) ? 'var(--primary-soft)' : undefined }}>{h || `Колонка ${i + 1}`}{mapped.has(i) && <div className="small" style={{ color: 'var(--primary)' }}>{Object.entries(columns).filter(([, v]) => v === i).map(([k]) => fields[k]?.label).join(', ')}</div>}</th>)}</tr></thead>
              <tbody>{(sheetData?.preview ?? []).map((r: string[], i: number) => <tr key={i}>{headers.map((_, j) => <td key={j}>{r[j]}</td>)}</tr>)}</tbody>
            </table>
          </div>
        </>
      )}
    </Modal>
  );
}

export function BatchRows({ batch, onClose }: { batch: any; onClose: () => void }) {
  const [status, setStatus] = useState('');
  const rows = useLoad<any[]>(() => api.get(`/batches/${batch.id}/rows${status ? `?status=${status}` : ''}`), [batch.id, status]);
  return (
    <Modal wide title={`Строки файла: ${batch.file_name}`} onClose={onClose}>
      <div className="filters">
        <div className="field"><label>Статус строки</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Все</option>{Object.entries(ROW_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        </div>
      </div>
      <ErrorBox error={rows.error} />
      {rows.loading && !rows.data ? <Loading /> : (
        <DataTable rows={rows.data ?? []} columns={[
          { key: 'row_number', label: 'Строка' },
          { key: 'normalized_status', label: 'Статус', render: (r) => <Badge value={r.normalized_status} label={ROW_STATUS} /> },
          { key: 'raw', label: 'Исходные данные', render: (r) => <span className="small">{Object.entries(r.raw_json).map(([k, v]) => `${k}: ${v}`).join(' · ')}</span> },
          { key: 'error_text', label: 'Замечание', render: (r) => <span className="small">{r.error_column ? <b>[{r.error_column}] </b> : null}{r.error_text}</span> },
        ]} />
      )}
    </Modal>
  );
}
