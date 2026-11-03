import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth';
import { api } from '../api';
import { DataTable } from '../components/crud';
import { Badge, ErrorBox, Field, Loading, PageHead, Tabs, useAction, useLoad } from '../components/ui';
import { ATTR, AUDIT_STATUS, CHANGE, FINDING_TYPE, fmtDate, fmtDateTime, RESULT, SEVERITY } from '../i18n';

const ORDER = ['ADDED', 'REMOVED', 'CHANGED', 'NEW_FINDING', 'RESOLVED', 'PERSISTING', 'AMBIGUOUS'];

export function HistoryPage() {
  const { can } = useAuth();
  const audits = useLoad<any[]>(() => api.get('/audits'));
  const comparisons = useLoad<any[]>(() => api.get('/comparisons'));
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const { busy, run } = useAction();
  const completed = (audits.data ?? []).filter((a) => a.status === 'COMPLETED');

  const compare = async () => {
    const r = await run(() => api.post('/comparisons', { from_audit_id: from, to_audit_id: to }), 'Сравнение выполнено');
    if (r) { await comparisons.reload(); setSelected(r.id); }
  };

  return (
    <div>
      <PageHead title="История и сравнение снимков" sub="Сравнение выполняется по стабильному ключу: ID сотрудника + система + логин + роль + модуль + операция (с учётом таблицы алиасов), а не по номеру строки Excel." />
      <div className="grid cols-2">
        <div className="card">
          <h2>История аудитов</h2>
          <ErrorBox error={audits.error} />
          <DataTable rows={audits.data ?? []} empty="Аудитов нет"
            columns={[
              { key: 'name', label: 'Аудит', render: (r) => <Link to={`/audits/${r.id}`}>{r.name}</Link> },
              { key: 'as_of_date', label: 'Дата среза', render: (r) => fmtDate(r.as_of_date) },
              { key: 'matrix_version', label: 'Матрица' },
              { key: 'status', label: 'Статус', render: (r) => <Badge value={r.status} label={AUDIT_STATUS} /> },
              { key: 'findings', label: 'Находок', render: (r) => r.summary?.findings ?? '—' },
            ]} />
        </div>
        <div className="card">
          <h2>Сравнить два снимка</h2>
          {can('comparisons.run') ? (
            <div className="grid">
              <Field label="Предыдущий аудит (было)"><select value={from} onChange={(e) => setFrom(e.target.value)}><option value="">— выберите —</option>{completed.map((a) => <option key={a.id} value={a.id}>{fmtDate(a.as_of_date)} — {a.name}</option>)}</select></Field>
              <Field label="Новый аудит (стало)"><select value={to} onChange={(e) => setTo(e.target.value)}><option value="">— выберите —</option>{completed.map((a) => <option key={a.id} value={a.id}>{fmtDate(a.as_of_date)} — {a.name}</option>)}</select></Field>
              <div><button className="btn primary" disabled={!from || !to || from === to || busy} onClick={compare}>Сравнить</button></div>
            </div>
          ) : <p className="muted">Запуск сравнения доступен аудитору ИБ.</p>}
          <h3 style={{ marginTop: 18 }}>Выполненные сравнения</h3>
          <DataTable rows={comparisons.data ?? []} onRowClick={(r) => setSelected(r.id)} empty="Сравнений нет"
            columns={[
              { key: 'pair', label: 'Было → стало', render: (r) => <span style={{ fontWeight: r.id === selected ? 600 : undefined }}>{fmtDate(r.from_date)} → {fmtDate(r.to_date)}</span> },
              { key: 'summary', label: 'Изменения', render: (r) => <span className="small">+{r.summary?.ADDED ?? 0} / −{r.summary?.REMOVED ?? 0} назн.; новых нарушений {r.summary?.NEW_FINDING ?? 0}</span> },
              { key: 'created_at', label: 'Выполнено', render: (r) => <span className="small">{fmtDateTime(r.created_at)}</span> },
            ]} />
        </div>
      </div>
      {selected && <ComparisonView id={selected} />}
    </div>
  );
}

function ComparisonView({ id }: { id: string }) {
  const [type, setType] = useState('ADDED');
  const head = useLoad<any>(() => api.get(`/comparisons/${id}?change_type=__none__`), [id]);
  const items = useLoad<any>(() => api.get(`/comparisons/${id}?change_type=${type}`), [id, type]);
  const c = head.data?.comparison;
  const assign = (j: any) => j && <>{j.employee_name ?? '—'} <span className="muted">({j.employee_key ?? '?'})</span> · {j.system}/{j.role}{j.operation ? `/${j.operation}` : ''}{j.login ? ` · ${j.login}` : ''}</>;
  const finding = (j: any) => j && <><Badge value={j.severity} label={SEVERITY} /> {FINDING_TYPE[j.finding_type] ?? j.finding_type} — {j.full_name ?? '—'}</>;
  const isFinding = ['NEW_FINDING', 'RESOLVED', 'PERSISTING'].includes(type);
  return (
    <div className="card">
      {!c ? <Loading /> : (
        <>
          <h2>Сравнение: «{c.from_name}» ({fmtDate(c.from_date)}) → «{c.to_name}» ({fmtDate(c.to_date)})</h2>
          <Tabs value={type} onChange={setType} items={ORDER.map((k) => ({ id: k, label: CHANGE[k], count: c.summary?.[k] ?? 0 }))} />
          {type === 'AMBIGUOUS' && <div className="alert warn">Записи с неустойчивым ключом (сотрудник не сопоставлен или неизвестные справочные значения) не участвуют в автоматическом сравнении.</div>}
          {type === 'CHANGED' && <div className="alert info">Назначение есть в обоих снимках, но изменились атрибуты: подразделение, должность, статус сотрудника, дата назначения или результат проверки.</div>}
          <ErrorBox error={items.error} />
          {items.loading && !items.data ? <Loading /> : (
            <DataTable rows={items.data?.items ?? []} empty="Изменений этого типа нет"
              columns={isFinding ? [
                { key: 'before', label: 'Было', render: (r) => finding(r.before_json) ?? <span className="muted">—</span> },
                { key: 'after', label: 'Стало', render: (r) => finding(r.after_json) ?? <span className="muted">—</span> },
                { key: 'explanation', label: 'Объяснение', render: (r) => <span className="small">{(r.after_json ?? r.before_json)?.explanation}</span> },
              ] : [
                { key: 'item', label: 'Назначение', render: (r) => assign(r.after_json ?? r.before_json) },
                { key: 'changed', label: 'Изменения', render: (r) => (r.before_json?.changed ? <span className="small">{r.before_json.changed.map((k: string) => `${ATTR[k] ?? k}: ${fmtV(k, r.before_json[k])} → ${fmtV(k, r.after_json?.[k])}`).join('; ')}</span> : null) },
                { key: 'result', label: 'Результат', render: (r) => { const j = r.after_json ?? r.before_json; return j?.result_status ? <Badge value={j.result_status} label={RESULT} /> : null; } },
                { key: 'access_key', label: 'Ключ', render: (r) => <code className="small">{r.access_key}</code> },
              ]} />
          )}
        </>
      )}
    </div>
  );
}

function fmtV(k: string, v: any) {
  if (v === null || v === undefined || v === '') return '—';
  if (k === 'result_status') return RESULT[v] ?? v;
  if (k === 'assigned_at') return fmtDate(v);
  return String(v);
}
