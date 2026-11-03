import { Fragment, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth';
import { api, download, qs } from '../api';
import { DataTable } from '../components/crud';
import { Badge, confirmAction, ErrorBox, Field, Loading, Modal, PageHead, Pager, Tabs, useAction, useDebounced, useLoad } from '../components/ui';
import { AUDIT_STATUS, BATCH_STATUS, FINDING_STATUS, FINDING_TYPE, fmtDate, fmtDateTime, fmtNum, OUTCOME, RESULT, ROW_STATUS, SEVERITY } from '../i18n';
import { useLookups } from '../lookups';
import { BatchRows, ImportWizard } from './ImportWizard';

type Tab = 'overview' | 'import' | 'findings' | 'snapshots' | 'errors' | 'reports';

export function AuditDetailPage() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const { can } = useAuth();
  const nav = useNavigate();
  const audit = useLoad<any>(() => api.get(`/audits/${id}`), [id]);
  const a = audit.data;
  const draft = a && (a.status === 'DRAFT' || a.status === 'FAILED');
  const tab = (params.get('tab') as Tab) ?? (a ? (draft ? 'import' : 'overview') : 'overview');
  const setTab = (t: Tab) => setParams({ tab: t }, { replace: true });
  const { busy, run } = useAction();
  const [verify, setVerify] = useState<any>(null);

  if (audit.loading && !a) return <Loading />;
  if (audit.error) return <ErrorBox error={audit.error} />;
  const s = a.summary ?? {};

  const execute = async () => {
    if (!confirmAction('Запустить аудит? После выполнения снимок станет неизменяемым: загрузка файлов и повторный расчёт будут недоступны.')) return;
    await run(() => api.post(`/audits/${id}/run`), 'Аудит выполнен');
    await audit.reload();
    setTab('overview');
  };

  return (
    <div>
      <PageHead title={a.name} sub={<>Дата среза {fmtDate(a.as_of_date)} · матрица {a.matrix_version ?? '—'} · <Badge value={a.status} label={AUDIT_STATUS} /></>}>
        <Link className="btn" to="/audits">← К списку</Link>
        {draft && can('audit.run') && <button className="btn primary" disabled={busy} onClick={execute}>{busy ? 'Выполнение…' : 'Запустить аудит'}</button>}
        {a.status === 'COMPLETED' && <button className="btn" disabled={busy} onClick={async () => setVerify(await run(() => api.post(`/audits/${id}/verify`)))}>Проверить воспроизводимость</button>}
        {draft && can('audit.create') && <button className="btn danger" disabled={busy} onClick={async () => { if (confirmAction('Удалить черновик аудита вместе с загруженными файлами?')) { await run(() => api.del(`/audits/${id}`), 'Аудит удалён'); nav('/audits'); } }}>Удалить</button>}
      </PageHead>
      {a.status === 'FAILED' && <div className="alert error">Ошибка выполнения: {a.error_text}</div>}
      {verify && (
        <div className={`alert ${verify.reproducible && verify.rulesOk && verify.matrixOk && verify.packageOk ? 'ok' : 'error'}`}>
          {verify.reproducible ? 'Повторный расчёт по сохранённому снимку дал идентичный результат.' : 'Повторный расчёт дал другой результат!'}
          {' '}Контрольные суммы: результаты {verify.reproducible ? '✓' : '✗'}, версия правил {verify.rulesOk ? '✓' : '✗'}, матрица {verify.matrixOk ? '✓' : '✗'}, исходный пакет {verify.packageOk ? '✓' : '✗'}.
        </div>
      )}
      <Tabs value={tab} onChange={setTab} items={[
        { id: 'overview', label: 'Параметры и сводка' },
        { id: 'import', label: 'Импорт', count: Number(a.batches_count) },
        { id: 'findings', label: 'Находки', count: s.findings, hidden: a.status !== 'COMPLETED' },
        { id: 'snapshots', label: 'Все назначения', count: Number(a.snapshots_count) },
        { id: 'errors', label: 'Ошибки импорта' },
        { id: 'reports', label: 'Отчёты', hidden: a.status !== 'COMPLETED' },
      ]} />
      {tab === 'overview' && <Overview a={a} />}
      {tab === 'import' && <ImportTab audit={a} onChanged={audit.reload} />}
      {tab === 'findings' && a.status === 'COMPLETED' && <FindingsTab audit={a} />}
      {tab === 'snapshots' && <SnapshotsTab audit={a} />}
      {tab === 'errors' && <ImportErrors auditId={a.id} />}
      {tab === 'reports' && a.status === 'COMPLETED' && <ReportsTab audit={a} />}
    </div>
  );
}

function Overview({ a }: { a: any }) {
  const s = a.summary ?? {};
  return (
    <div className="grid cols-2">
      <div className="card">
        <h2>Параметры</h2>
        <dl className="kv">
          <dt>Дата среза</dt><dd>{fmtDate(a.as_of_date)}</dd>
          <dt>Версия матрицы</dt><dd>{a.matrix_version ? `${a.matrix_version} — ${a.matrix_name}` : '—'}</dd>
          <dt>Создан</dt><dd>{a.created_by_name}, {fmtDateTime(a.created_at)}</dd>
          <dt>Запущен</dt><dd>{a.started_by_name ? `${a.started_by_name}, ${fmtDateTime(a.started_at)}` : '—'}</dd>
          <dt>Завершён</dt><dd>{fmtDateTime(a.completed_at)}{s.durationMs ? ` (${(s.durationMs / 1000).toFixed(1)} с)` : ''}</dd>
          <dt>Описание</dt><dd>{a.description ?? '—'}</dd>
        </dl>
        {a.status === 'COMPLETED' && (
          <>
            <h3 style={{ marginTop: 16 }}>Контрольные суммы (SHA-256)</h3>
            <dl className="kv small">
              <dt>Исходный пакет</dt><dd><code>{a.package_checksum}</code></dd>
              <dt>Матрица</dt><dd><code>{a.matrix_checksum}</code></dd>
              <dt>Версия правил</dt><dd><code>{a.rules_checksum}</code></dd>
              <dt>Результаты</dt><dd><code>{a.result_checksum}</code></dd>
            </dl>
            <h3 style={{ marginTop: 16 }}>Файлы пакета</h3>
            {(s.files ?? []).map((f: any) => <div key={f.sha256} className="small"><b>{f.name}</b> — {f.rows} строк<br /><code>{f.sha256}</code></div>)}
          </>
        )}
      </div>
      <div className="card">
        <h2>Сводка</h2>
        {a.status !== 'COMPLETED' ? <p className="muted">Аудит ещё не выполнен. Загрузите и обработайте файлы на вкладке «Импорт», затем нажмите «Запустить аудит».</p> : (
          <>
            <div className="kpis">
              <div className="kpi"><div className="label">Назначений</div><div className="value">{fmtNum(s.totalAccesses)}</div></div>
              <div className="kpi ok"><div className="label">Соответствует</div><div className="value">{fmtNum(s.byResult?.COMPLIANT)}</div></div>
              <div className="kpi high"><div className="label">Нарушение</div><div className="value">{fmtNum(s.byResult?.VIOLATION)}</div></div>
              <div className="kpi"><div className="label">Покрыто исключением</div><div className="value">{fmtNum(s.byResult?.COVERED_BY_EXCEPTION)}</div></div>
              <div className="kpi warn"><div className="label">Требует проверки</div><div className="value">{fmtNum(s.byResult?.NEEDS_REVIEW)}</div></div>
            </div>
            <h3>Находки по критичности</h3>
            <div className="row" style={{ marginBottom: 12 }}>{Object.entries(SEVERITY).map(([k, v]) => <span key={k}><Badge value={k} label={v} /> {s.bySeverity?.[k] ?? 0}</span>)}</div>
            <h3>Находки по типам</h3>
            <dl className="kv">{Object.entries(s.byType ?? {}).map(([k, v]) => <Fragment key={k}><dt>{FINDING_TYPE[k] ?? k}</dt><dd>{String(v)}</dd></Fragment>)}</dl>
            <dl className="kv" style={{ marginTop: 12 }}>
              <dt>Уволенных с доступом</dt><dd>{s.terminatedWithAccess}</dd>
              <dt>Конфликтов SoD</dt><dd>{s.sodConflicts}</dd>
              <dt>Истёкших исключений (затронули назначения)</dt><dd>{s.expiredExceptionsMatched}</dd>
            </dl>
          </>
        )}
      </div>
    </div>
  );
}

function ImportTab({ audit, onChanged }: { audit: any; onChanged: () => void }) {
  const { can } = useAuth();
  const batches = useLoad<any[]>(() => api.get(`/audits/${audit.id}/batches`), [audit.id]);
  const [wizard, setWizard] = useState<any>(null);
  const [rowsOf, setRowsOf] = useState<any>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const { busy, run } = useAction();
  const draft = audit.status === 'DRAFT' || audit.status === 'FAILED';
  const editable = draft && can('import.run');

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    const fd = new FormData();
    [...files].forEach((f) => fd.append('files', f));
    const created = await run(() => api.upload(`/audits/${audit.id}/batches`, fd), 'Файлы загружены');
    if (fileRef.current) fileRef.current.value = '';
    await batches.reload();
    onChanged();
    if (created?.length === 1) setWizard(created[0]);
  };

  return (
    <div>
      {editable && (
        <div className="card">
          <h2>Загрузка выгрузок фактических доступов</h2>
          <p className="muted">Форматы XLSX и CSV (UTF-8 или Windows-1251), можно несколько файлов в один пакет. Оригинал сохраняется в защищённом хранилище с контрольной суммой SHA-256. Макросы не принимаются, формулы не исполняются.</p>
          <div className="row">
            <input ref={fileRef} type="file" multiple accept=".xlsx,.csv" onChange={(e) => upload(e.target.files)} disabled={busy} style={{ maxWidth: 460 }} />
            {busy && <span className="muted">Загрузка…</span>}
          </div>
        </div>
      )}
      {!draft && <div className="alert info">Аудит выполнен — пакет импорта зафиксирован и не изменяется.</div>}
      <ErrorBox error={batches.error} />
      <div className="card flush">
        <DataTable rows={batches.data ?? []} empty="Файлы не загружены"
          columns={[
            { key: 'file_name', label: 'Файл', render: (r) => <><b>{r.file_name}</b><div className="small muted">{r.file_type} · {(r.file_size / 1024).toFixed(1)} КБ · {r.uploaded_by_name} · {fmtDateTime(r.uploaded_at)}</div><code className="small">{r.sha256}</code></> },
            { key: 'status', label: 'Статус', render: (r) => <Badge value={r.status} label={BATCH_STATUS} /> },
            { key: 'sheet_name', label: 'Лист' },
            { key: 'total_rows', label: 'Строк', className: 'num' }, { key: 'ok_rows', label: 'OK', className: 'num' },
            { key: 'warning_rows', label: 'Предупр./дубли', className: 'num' }, { key: 'error_rows', label: 'Ошибки', className: 'num' },
          ]}
          actions={(r) => (
            <div className="row" style={{ gap: 6 }}>
              {editable && <button className="btn small primary" onClick={() => setWizard(r)}>{r.status === 'UPLOADED' ? 'Сопоставить колонки' : 'Обработать заново'}</button>}
              {r.status !== 'UPLOADED' && <button className="btn small" onClick={() => setRowsOf(r)}>Строки</button>}
              {editable && <button className="btn small danger" disabled={busy} onClick={async () => { if (confirmAction(`Удалить файл «${r.file_name}» из пакета?`)) { await run(() => api.del(`/batches/${r.id}`), 'Файл удалён'); batches.reload(); onChanged(); } }}>Удалить</button>}
            </div>
          )} />
      </div>
      {wizard && <ImportWizard batch={wizard} onClose={() => setWizard(null)} onDone={() => { batches.reload(); onChanged(); }} />}
      {rowsOf && <BatchRows batch={rowsOf} onClose={() => setRowsOf(null)} />}
    </div>
  );
}

function ImportErrors({ auditId }: { auditId: string }) {
  const rows = useLoad<any[]>(() => api.get(`/audits/${auditId}/import-errors`), [auditId]);
  return (
    <div className="card flush">
      <ErrorBox error={rows.error} />
      <DataTable rows={rows.data ?? []} empty="Ошибок и предупреждений импорта нет"
        columns={[
          { key: 'file_name', label: 'Файл' }, { key: 'sheet_name', label: 'Лист' }, { key: 'row_number', label: 'Строка' },
          { key: 'normalized_status', label: 'Статус', render: (r) => <Badge value={r.normalized_status} label={ROW_STATUS} /> },
          { key: 'error_column', label: 'Колонка' }, { key: 'error_text', label: 'Описание' },
        ]} />
    </div>
  );
}

const FILTER_INIT = { system_id: '', department_id: '', position_id: '', severity: '', finding_type: '', outcome: '', status: '', owner_user_id: '', search: '' };

function useFindingFilters() {
  const [f, setF] = useState<Record<string, string>>(FILTER_INIT);
  const search = useDebounced(f.search);
  const effective = useMemo(() => ({ ...f, search }), [f, search]);
  return { f, setF, effective };
}

function FindingFiltersBar({ f, setF }: { f: Record<string, string>; setF: (x: Record<string, string>) => void }) {
  const l = useLookups();
  const users = useLoad<any[]>(() => api.get('/admin/user-options').catch(() => []));
  const sel = (k: string, label: string, options: Array<[string, string]>) => (
    <div className="field"><label>{label}</label>
      <select value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}><option value="">Все</option>{options.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>
    </div>
  );
  return (
    <div className="filters">
      <div className="field grow"><label>Поиск</label><input value={f.search} onChange={(e) => setF({ ...f, search: e.target.value })} placeholder="ФИО, таб. №, логин, текст объяснения" /></div>
      {sel('system_id', 'Система', (l?.systems ?? []).map((s) => [s.id, s.code]))}
      {sel('department_id', 'Подразделение', (l?.departments ?? []).map((s) => [s.id, s.name]))}
      {sel('position_id', 'Должность', (l?.positions ?? []).map((s) => [s.id, s.name]))}
      {sel('severity', 'Критичность', Object.entries(SEVERITY))}
      {sel('finding_type', 'Тип нарушения', Object.entries(FINDING_TYPE))}
      {sel('outcome', 'Результат', Object.entries(OUTCOME))}
      {sel('status', 'Статус обработки', Object.entries(FINDING_STATUS))}
      {sel('owner_user_id', 'Владелец системы', (users.data ?? []).map((u) => [u.id, u.full_name]))}
      <button className="btn" onClick={() => setF(FILTER_INIT)}>Сбросить</button>
    </div>
  );
}

function FindingsTab({ audit }: { audit: any }) {
  const { f, setF, effective } = useFindingFilters();
  const [offset, setOffset] = useState(0);
  const limit = 100;
  const query = qs({ ...effective, limit, offset });
  const data = useLoad<any>(() => api.get(`/audits/${audit.id}/findings${query}`), [audit.id, query]);
  const [open, setOpen] = useState<string | null>(null);
  const { can } = useAuth();
  const { busy, run } = useAction();
  const setFilters = (x: Record<string, string>) => { setOffset(0); setF(x); };

  return (
    <div>
      <FindingFiltersBar f={f} setF={setFilters} />
      <div className="row" style={{ marginBottom: 10 }}>
        <span className="muted small">Найдено: {data.data?.total ?? '…'}</span>
        <div className="spacer" />
        {can('reports.export', 'findings.scoped') && <>
          <button className="btn" disabled={busy} onClick={() => run(() => download(`/audits/${audit.id}/report.xlsx${qs(effective)}`), 'Отчёт XLSX сформирован')}>Экспорт XLSX (с фильтрами)</button>
          <button className="btn" disabled={busy} onClick={() => run(() => download(`/audits/${audit.id}/report.pdf${qs(effective)}`), 'Отчёт PDF сформирован')}>Экспорт PDF</button>
        </>}
      </div>
      <ErrorBox error={data.error} />
      <div className="card flush">
        {data.loading && !data.data ? <Loading /> : (
          <DataTable rows={data.data?.rows ?? []} onRowClick={(r) => setOpen(r.id)} empty="Находок по выбранным фильтрам нет"
            columns={[
              { key: 'severity', label: 'Критичность', render: (r) => <Badge value={r.severity} label={SEVERITY} /> },
              { key: 'finding_type', label: 'Тип', render: (r) => <>{FINDING_TYPE[r.finding_type] ?? r.finding_type}<div className="small muted">{r.rule_code}</div></> },
              { key: 'outcome', label: 'Результат', render: (r) => <Badge value={r.outcome} label={OUTCOME} /> },
              { key: 'employee', label: 'Сотрудник', render: (r) => <>{r.employee_name ?? '—'}<div className="small muted">{r.employee_key ?? r.employee_key_raw} {r.position_name ? `· ${r.position_name}` : ''}</div></> },
              { key: 'system_code', label: 'Система' },
              { key: 'what', label: 'Роль / операция', render: (r) => (r.role_code ? <>{r.role_code}{r.operation_code && <div className="small muted">{r.operation_code}</div>}</> : <span className="muted small">групповая (SoD)</span>) },
              { key: 'explanation', label: 'Объяснение', render: (r) => <span className="small">{r.explanation.length > 180 ? `${r.explanation.slice(0, 180)}…` : r.explanation}</span> },
              { key: 'status', label: 'Обработка', render: (r) => <Badge value={r.status} label={FINDING_STATUS} /> },
            ]} />
        )}
        {data.data && <Pager total={data.data.total} limit={limit} offset={offset} onChange={setOffset} />}
      </div>
      {open && <FindingCard id={open} onClose={() => setOpen(null)} onChanged={data.reload} />}
    </div>
  );
}

function FindingCard({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { can } = useAuth();
  const d = useLoad<any>(() => api.get(`/findings/${id}`), [id]);
  const [comment, setComment] = useState('');
  const [status, setStatus] = useState('');
  const { busy, run } = useAction();
  const f = d.data?.finding;
  const canEdit = can('findings.edit');
  const canComment = can('findings.comment', 'findings.edit');
  const statusOptions = canEdit ? Object.entries(FINDING_STATUS) : Object.entries(FINDING_STATUS).filter(([k]) => k === 'CONFIRMED' || k === 'DISPUTED');

  const submit = async () => {
    const r = await run(() => api.post(`/findings/${id}/comments`, { text: comment, status: status || undefined }), 'Сохранено');
    if (r) { setComment(''); setStatus(''); d.reload(); onChanged(); }
  };

  return (
    <Modal wide title="Карточка находки" onClose={onClose}>
      <ErrorBox error={d.error} />
      {!f ? <Loading /> : (
        <div className="grid cols-2">
          <div>
            <div className="row" style={{ marginBottom: 10 }}>
              <Badge value={f.severity} label={SEVERITY} /><Badge value={f.outcome} label={OUTCOME} /><Badge value={f.status} label={FINDING_STATUS} />
              <span className="muted small">{f.rule_code}</span>
            </div>
            <h2>{FINDING_TYPE[f.finding_type] ?? f.finding_type}</h2>
            <p className="pre">{f.explanation}</p>
            <dl className="kv small">
              <dt>Сотрудник</dt><dd>{f.employee_name ?? '—'} ({f.employee_key ?? f.employee_key_raw ?? '—'})</dd>
              <dt>Подразделение / должность</dt><dd>{f.department_name ?? '—'} / {f.position_name ?? '—'}</dd>
              <dt>Система</dt><dd>{f.system_code ? `${f.system_code} — ${f.system_name}` : '—'}{f.owner_name ? ` (владелец: ${f.owner_name})` : ''}</dd>
            </dl>
            <h3 style={{ marginTop: 14 }}>Ожидаемое право</h3>
            <div className="side-box small pre">{f.expected ?? '—'}</div>
            <h3>Фактическое право</h3>
            <div className="side-box small pre">{f.actual ?? '—'}</div>
            {f.details?.sides && (
              <>
                <h3>Стороны конфликта SoD</h3>
                {f.details.sides.map((s: any) => (
                  <div className="side-box small" key={s.side}>
                    <b>Сторона {s.side}:</b> {s.capabilities.join(' / ')}
                    <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{s.assignments.map((x: any) => <li key={x.snapshotId}>{x.label}</li>)}</ul>
                  </div>
                ))}
              </>
            )}
            {d.data.exception && (
              <>
                <h3>Исключение</h3>
                <div className="side-box small">
                  <b>{d.data.exception.ticket_ref}</b> — {d.data.exception.reason}<br />
                  Период: {fmtDate(d.data.exception.valid_from)} — {fmtDate(d.data.exception.valid_to)}; согласовал: {d.data.exception.approved_by}<br />
                  Компенсирующий контроль: {d.data.exception.compensating_control}
                </div>
              </>
            )}
            {d.data.matrixRules?.length > 0 && (
              <>
                <h3>Правила матрицы</h3>
                {d.data.matrixRules.map((r: any) => (
                  <div className="side-box small" key={r.id}>{r.effect === 'ALLOW' ? 'Разрешено' : 'Запрещено'}: роль {r.role_code ?? 'любая'}{r.operation_code ? `, операция ${r.operation_code}` : ''}; {r.department_name ?? 'любое подразделение'} / {r.position_name ?? 'любая должность'}; основание: {r.source_ref} ({r.owner})</div>
                ))}
              </>
            )}
          </div>
          <div>
            {d.data.snapshot && (
              <>
                <h3>Исходное назначение (доказательство)</h3>
                <div className="side-box small">
                  Файл <b>{d.data.snapshot.file_name}</b>, лист «{d.data.snapshot.sheet_name}», строка {d.data.snapshot.row_number}
                  {d.data.snapshot.expanded_from_role && <div className="muted">Операция получена разворачиванием состава роли</div>}
                  <div className="muted">SHA-256 файла: <code>{d.data.snapshot.sha256}</code></div>
                  <table className="t" style={{ marginTop: 6 }}><tbody>{Object.entries(d.data.snapshot.raw_json).map(([k, v]) => <tr key={k}><td className="muted">{k}</td><td>{String(v)}</td></tr>)}</tbody></table>
                </div>
              </>
            )}
            <h3 style={{ marginTop: 14 }}>Обработка и комментарии</h3>
            {d.data.comments.length === 0 && <div className="muted small">Комментариев нет</div>}
            {d.data.comments.map((c: any) => (
              <div key={c.id} className="side-box small">
                <b>{c.author_name}</b> <span className="muted">{fmtDateTime(c.created_at)}</span>
                {c.new_status && <> · статус → <Badge value={c.new_status} label={FINDING_STATUS} /></>}
                <div className="pre">{c.text}</div>
              </div>
            ))}
            {canComment && (
              <div className="grid" style={{ marginTop: 10 }}>
                <Field label="Комментарий"><textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder={canEdit ? 'Комментарий аудитора' : 'Подтвердите или оспорьте замечание с обоснованием'} /></Field>
                <Field label="Изменить статус">
                  <select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">— не менять —</option>{statusOptions.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
                </Field>
                <div><button className="btn primary" disabled={busy || !comment.trim()} onClick={submit}>Сохранить</button></div>
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

function SnapshotsTab({ audit }: { audit: any }) {
  const l = useLookups();
  const [filter, setFilter] = useState({ result_status: '', system_id: '', search: '' });
  const search = useDebounced(filter.search);
  const [offset, setOffset] = useState(0);
  const limit = 100;
  const query = qs({ ...filter, search, limit, offset });
  const data = useLoad<any>(() => api.get(`/audits/${audit.id}/snapshots${query}`), [audit.id, query]);
  const set = (x: any) => { setOffset(0); setFilter(x); };
  return (
    <div>
      <div className="filters">
        <div className="field grow"><label>Поиск</label><input value={filter.search} onChange={(e) => set({ ...filter, search: e.target.value })} placeholder="ФИО, таб. №, логин, роль, операция" /></div>
        <div className="field"><label>Результат</label><select value={filter.result_status} onChange={(e) => set({ ...filter, result_status: e.target.value })}><option value="">Все</option>{Object.entries(RESULT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div className="field"><label>Система</label><select value={filter.system_id} onChange={(e) => set({ ...filter, system_id: e.target.value })}><option value="">Все</option>{(l?.systems ?? []).map((s) => <option key={s.id} value={s.id}>{s.code}</option>)}</select></div>
      </div>
      {data.data?.byResult && <div className="row small" style={{ marginBottom: 10 }}>{data.data.byResult.map((b: any) => <span key={b.result_status ?? 'none'}><Badge value={b.result_status ?? 'DRAFT'} label={b.result_status ? RESULT : 'не проверено'} /> {b.n}</span>)}</div>}
      <ErrorBox error={data.error} />
      <div className="card flush">
        {data.loading && !data.data ? <Loading /> : (
          <DataTable rows={data.data?.rows ?? []} empty="Назначений нет"
            columns={[
              { key: 'employee', label: 'Сотрудник', render: (r) => <>{r.employee_name ?? '—'}<div className="small muted">{r.employee_key}</div></> },
              { key: 'system_code', label: 'Система' }, { key: 'login', label: 'Логин' },
              { key: 'role_code', label: 'Роль' }, { key: 'module_code', label: 'Модуль' },
              { key: 'operation_code', label: 'Операция', render: (r) => <>{r.operation_code ?? '—'}{r.expanded_from_role && <div className="small muted">из состава роли</div>}</> },
              { key: 'assigned_at', label: 'Назначено', render: (r) => fmtDate(r.assigned_at) },
              { key: 'result_status', label: 'Результат', render: (r) => (r.result_status ? <Badge value={r.result_status} label={RESULT} /> : <span className="muted small">не проверено</span>) },
              { key: 'review_reason', label: 'Нормализация', render: (r) => (r.normalized_status === 'OK' ? 'OK' : <span className="small" style={{ color: 'var(--warn)' }}>{r.review_reason}</span>) },
              { key: 'src', label: 'Источник', render: (r) => <span className="small muted">{r.file_name}, стр. {r.row_number}</span> },
            ]} />
        )}
        {data.data && <Pager total={data.data.total} limit={limit} offset={offset} onChange={setOffset} />}
      </div>
    </div>
  );
}

function ReportsTab({ audit }: { audit: any }) {
  const { can } = useAuth();
  const reports = useLoad<any[]>(() => api.get(`/audits/${audit.id}/reports`), [audit.id]);
  const { f, setF, effective } = useFindingFilters();
  const { busy, run } = useAction();
  const [open, setOpen] = useState(false);
  const exp = async (fmt: 'xlsx' | 'pdf') => { await run(() => download(`/audits/${audit.id}/report.${fmt}${qs(effective)}`), `Отчёт ${fmt.toUpperCase()} сформирован`); reports.reload(); };
  return (
    <div>
      <div className="card">
        <h2>Сформировать отчёт</h2>
        <p className="muted">XLSX: сводка, все назначения, нарушения, SoD, исключения, ошибки импорта, изменения между периодами. PDF: титульная страница, параметры, сводные показатели, критические находки, методология и ограничения. В отчёте указываются дата, автор, системы, версия матрицы и контрольные суммы.</p>
        <button className="btn link" onClick={() => setOpen(!open)}>{open ? 'Скрыть фильтры' : 'Фильтры отчёта (необязательно)'}</button>
        {open && <div style={{ marginTop: 10 }}><FindingFiltersBar f={f} setF={setF} /></div>}
        {can('reports.export', 'findings.scoped') ? (
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn primary" disabled={busy} onClick={() => exp('xlsx')}>Скачать XLSX</button>
            <button className="btn primary" disabled={busy} onClick={() => exp('pdf')}>Скачать PDF</button>
          </div>
        ) : <div className="alert info">Нет права на экспорт отчётов.</div>}
      </div>
      <div className="card flush">
        <div style={{ padding: '12px 12px 0' }}><h3>Сформированные отчёты</h3></div>
        <DataTable rows={reports.data ?? []} empty="Отчёты ещё не формировались"
          columns={[
            { key: 'created_at', label: 'Дата', render: (r) => fmtDateTime(r.created_at) }, { key: 'format', label: 'Формат' },
            { key: 'file_name', label: 'Файл' }, { key: 'created_by_name', label: 'Автор' },
            { key: 'filters', label: 'Фильтры', render: (r) => <span className="small">{Object.entries(r.filters ?? {}).map(([k, v]) => `${k}=${v}`).join('; ') || '—'}</span> },
            { key: 'sha256', label: 'SHA-256', render: (r) => <code className="small">{r.sha256.slice(0, 16)}…</code> },
          ]} />
      </div>
    </div>
  );
}
