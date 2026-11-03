import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth';
import { api, qs } from '../api';
import { DataTable, enumOpt, FormField, FormFields, opt } from '../components/crud';
import { Badge, confirmAction, ErrorBox, Field, Loading, Modal, PageHead, Tabs, useAction, useDebounced, useLoad } from '../components/ui';
import { FINDING_TYPE, fmtDate, fmtDateTime, MATRIX_STATUS, RISK, SEVERITY, SEVERITIES } from '../i18n';
import { useLookups } from '../lookups';

export function MatrixPage() {
  const [tab, setTab] = useState<'matrix' | 'policy'>('matrix');
  return (
    <div>
      <PageHead title="Матрица полномочий" sub="Допустимость назначений с учётом системы, подразделения, должности, роли и операций. Утверждённые версии неизменяемы; аудит ссылается на конкретную версию." />
      <Tabs value={tab} onChange={setTab} items={[{ id: 'matrix', label: 'Версии и правила' }, { id: 'policy', label: 'Политика критичности' }]} />
      {tab === 'matrix' ? <MatrixVersions /> : <SeverityPolicy />}
    </div>
  );
}

function MatrixVersions() {
  const { can } = useAuth();
  const versions = useLoad<any[]>(() => api.get('/matrix/versions'));
  const [selected, setSelected] = useState<string | null>(null);
  const [newVersion, setNewVersion] = useState<Record<string, any> | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const { busy, run } = useAction();

  useEffect(() => {
    if (!selected && versions.data?.length) setSelected((versions.data.find((v) => v.status === 'APPROVED') ?? versions.data[0]).id);
  }, [versions.data, selected]);
  const v = versions.data?.find((x) => x.id === selected);

  const createVersion = async () => {
    setFormError(null);
    try {
      const r = await api.post('/matrix/versions', newVersion);
      setNewVersion(null);
      await versions.reload();
      setSelected(r.id);
    } catch (e: any) { setFormError(e.message); }
  };
  const act = async (path: string, ok: string, confirmText?: string) => {
    if (confirmText && !confirmAction(confirmText)) return;
    await run(() => api.post(`/matrix/versions/${selected}/${path}`), ok);
    versions.reload();
  };

  return (
    <div>
      <div className="card flush">
        <div className="filters" style={{ padding: '12px 12px 0' }}>
          <h3 style={{ margin: 0 }}>Версии матрицы</h3>
          <div className="spacer" />
          {can('matrix.edit') && <button className="btn primary" onClick={() => { setFormError(null); setNewVersion({ valid_from: new Date().toISOString().slice(0, 10), clone_from_id: selected ?? '' }); }}>+ Новая версия</button>}
        </div>
        <ErrorBox error={versions.error} />
        <DataTable rows={versions.data ?? []} onRowClick={(r) => setSelected(r.id)}
          columns={[
            { key: 'version', label: 'Версия', render: (r) => <b style={{ color: r.id === selected ? 'var(--primary)' : undefined }}>{r.id === selected ? '▸ ' : ''}{r.version}</b> },
            { key: 'name', label: 'Наименование' },
            { key: 'period', label: 'Период действия', render: (r) => `${fmtDate(r.valid_from)} — ${r.valid_to ? fmtDate(r.valid_to) : 'бессрочно'}` },
            { key: 'status', label: 'Статус', render: (r) => <Badge value={r.status} label={MATRIX_STATUS} /> },
            { key: 'rules_count', label: 'Правил', className: 'num' }, { key: 'audits_count', label: 'Аудитов', className: 'num' },
            { key: 'approved', label: 'Утверждена', render: (r) => (r.approved_at ? `${r.approved_by_name ?? ''}, ${fmtDateTime(r.approved_at)}` : '—') },
          ]} />
      </div>
      {v && (
        <div className="card">
          <div className="row">
            <div>
              <h2 style={{ margin: 0 }}>Версия {v.version}: {v.name}</h2>
              <div className="muted small">{v.description} {v.checksum && <>· SHA-256 правил: <code>{v.checksum.slice(0, 16)}…</code></>}</div>
            </div>
            <div className="spacer" />
            {v.status === 'DRAFT' && can('matrix.approve') && <button className="btn primary" disabled={busy} onClick={() => act('approve', 'Версия утверждена', 'Утвердить версию? После утверждения правила изменять нельзя.')}>Утвердить</button>}
            {v.status === 'APPROVED' && can('matrix.approve') && <button className="btn" disabled={busy} onClick={() => act('archive', 'Версия перенесена в архив', 'Перенести версию в архив?')}>В архив</button>}
            {v.status === 'DRAFT' && can('matrix.edit') && <button className="btn danger" disabled={busy} onClick={async () => { if (!confirmAction('Удалить черновик версии со всеми правилами?')) return; await run(() => api.del(`/matrix/versions/${v.id}`), 'Черновик удалён'); setSelected(null); versions.reload(); }}>Удалить черновик</button>}
          </div>
          {v.status !== 'DRAFT' && <div className="alert info" style={{ marginTop: 12 }}>Версия {MATRIX_STATUS[v.status].toLowerCase()} и не редактируется. Для изменений создайте новую версию на её основе.</div>}
        </div>
      )}
      {v && <MatrixRules version={v} onChanged={versions.reload} />}
      {newVersion && (
        <Modal title="Новая версия матрицы" onClose={() => setNewVersion(null)} footer={<><button className="btn" onClick={() => setNewVersion(null)}>Отмена</button><button className="btn primary" onClick={createVersion}>Создать</button></>}>
          <ErrorBox error={formError} />
          <FormFields form={newVersion} setForm={setNewVersion} fields={[
            { name: 'version', label: 'Номер версии', required: true, hint: 'Например, 2025.2' }, { name: 'name', label: 'Наименование', required: true },
            { name: 'valid_from', label: 'Действует с', type: 'date', required: true }, { name: 'valid_to', label: 'Действует по', type: 'date' },
            { name: 'clone_from_id', label: 'Скопировать правила из версии', type: 'select', options: (versions.data ?? []).map((x) => ({ value: x.id, label: `${x.version} — ${x.name}` })), emptyLabel: '— пустая версия —' },
            { name: 'description', label: 'Описание', type: 'textarea' },
          ]} />
        </Modal>
      )}
    </div>
  );
}

function MatrixRules({ version, onChanged }: { version: any; onChanged: () => void }) {
  const { can } = useAuth();
  const l = useLookups();
  const editable = version.status === 'DRAFT' && can('matrix.edit');
  const [filter, setFilter] = useState<Record<string, string>>({});
  const [search, setSearch] = useState('');
  const s = useDebounced(search);
  const query = useMemo(() => qs({ ...filter, search: s }), [filter, s]);
  const rules = useLoad<any[]>(() => api.get(`/matrix/versions/${version.id}/rules${query}`), [version.id, query]);
  const [editing, setEditing] = useState<{ id?: string; form: Record<string, any> } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const { busy, run } = useAction();

  const sysOpt = opt(l?.systems);
  const fields: FormField[] = [
    { name: 'system_id', label: 'Система', type: 'select', options: sysOpt, required: true, resets: ['role_id', 'module_id', 'operation_id'] },
    { name: 'effect', label: 'Эффект', type: 'select', options: [{ value: 'ALLOW', label: 'Разрешено' }, { value: 'DENY', label: 'Запрещено' }], required: true },
    { name: 'department_id', label: 'Подразделение', type: 'select', options: opt(l?.departments), emptyLabel: '— любое —' },
    { name: 'position_id', label: 'Должность', type: 'select', options: opt(l?.positions), emptyLabel: '— любая —' },
    { name: 'role_id', label: 'Роль', type: 'select', options: (f) => opt((l?.roles ?? []).filter((r) => r.system_id === f.system_id)), emptyLabel: '— любая роль системы —' },
    { name: 'module_id', label: 'Модуль', type: 'select', options: (f) => opt((l?.modules ?? []).filter((r) => r.system_id === f.system_id)), emptyLabel: '— весь состав роли —', resets: ['operation_id'] },
    { name: 'operation_id', label: 'Операция', type: 'select', options: (f) => opt((l?.operations ?? []).filter((r) => r.system_id === f.system_id && (!f.module_id || r.module_id === f.module_id))), emptyLabel: '— все операции состава роли/модуля —' },
    { name: 'severity', label: 'Критичность нарушения (для запрета)', type: 'select', options: enumOpt(RISK), emptyLabel: '— по политике —' },
    { name: 'source_ref', label: 'Основание (документ)', required: true }, { name: 'owner', label: 'Владелец правила', required: true },
    { name: 'valid_from', label: 'Действует с', type: 'date', required: true }, { name: 'valid_to', label: 'Действует по', type: 'date' },
    { name: 'status', label: 'Статус', type: 'select', options: [{ value: 'ACTIVE', label: 'Активно' }, { value: 'INACTIVE', label: 'Неактивно' }], required: true },
    { name: 'notes', label: 'Примечание', type: 'textarea' },
  ];
  const pick = (r: any) => Object.fromEntries(fields.map((f) => [f.name, r[f.name] ?? '']));
  const save = async () => {
    if (!editing) return;
    setFormError(null);
    try {
      if (editing.id) await api.put(`/matrix/rules/${editing.id}`, editing.form);
      else await api.post(`/matrix/versions/${version.id}/rules`, editing.form);
      setEditing(null);
      rules.reload();
      onChanged();
    } catch (e: any) { setFormError(e.message); }
  };
  const any = (v: any, label = 'любое') => v ?? <span className="muted">{label}</span>;

  return (
    <div>
      <div className="filters">
        <div className="field grow"><label>Поиск</label><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Основание, владелец, роль, операция" /></div>
        {[['system_id', 'Система', sysOpt], ['department_id', 'Подразделение', opt(l?.departments)], ['position_id', 'Должность', opt(l?.positions)],
          ['role_id', 'Роль', opt((l?.roles ?? []).filter((r) => !filter.system_id || r.system_id === filter.system_id))]].map(([k, label, o]: any) => (
          <div className="field" key={k}><label>{label}</label>
            <select value={filter[k] ?? ''} onChange={(e) => setFilter({ ...filter, [k]: e.target.value })}><option value="">Все</option>{o.map((x: any) => <option key={x.value} value={x.value}>{x.label}</option>)}</select>
          </div>
        ))}
        <div className="field"><label>Эффект</label><select value={filter.effect ?? ''} onChange={(e) => setFilter({ ...filter, effect: e.target.value })}><option value="">Все</option><option value="ALLOW">Разрешено</option><option value="DENY">Запрещено</option></select></div>
        {editable && <button className="btn" onClick={() => setImportOpen(true)}>Импорт из файла</button>}
        {editable && <button className="btn primary" onClick={() => { setFormError(null); setEditing({ form: { effect: 'ALLOW', status: 'ACTIVE', valid_from: version.valid_from, system_id: filter.system_id ?? '' } }); }}>+ Правило</button>}
      </div>
      <ErrorBox error={rules.error} />
      <div className="card flush">
        {rules.loading && !rules.data ? <Loading /> : (
          <DataTable rows={rules.data ?? []} onRowClick={editable ? (r) => { setFormError(null); setEditing({ id: r.id, form: pick(r) }); } : undefined}
            empty="Правил нет"
            columns={[
              { key: 'effect', label: 'Эффект', render: (r) => <Badge value={r.effect} label={{ ALLOW: 'Разрешено', DENY: 'Запрещено' }} /> },
              { key: 'system_code', label: 'Система' },
              { key: 'department_name', label: 'Подразделение', render: (r) => any(r.department_name) },
              { key: 'position_name', label: 'Должность', render: (r) => any(r.position_name, 'любая') },
              { key: 'role_code', label: 'Роль', render: (r) => (r.role_code ? `${r.role_code} — ${r.role_name}` : any(null, 'любая')) },
              { key: 'operation', label: 'Модуль / операция', render: (r) => (r.operation_code ? `${r.module_code ?? ''} / ${r.operation_code}` : r.module_code ? `${r.module_code} / все` : <span className="muted">состав роли</span>) },
              { key: 'source_ref', label: 'Основание' }, { key: 'owner', label: 'Владелец' },
              { key: 'period', label: 'Период', render: (r) => `${fmtDate(r.valid_from)} — ${r.valid_to ? fmtDate(r.valid_to) : '∞'}` },
              { key: 'status', label: 'Статус', render: (r) => (r.status === 'ACTIVE' ? 'активно' : <span className="muted">неактивно</span>) },
            ]}
            actions={editable ? (r) => <button className="btn small danger" disabled={busy} onClick={async () => { if (!confirmAction('Удалить правило?')) return; await run(() => api.del(`/matrix/rules/${r.id}`), 'Правило удалено'); rules.reload(); onChanged(); }}>Удалить</button> : undefined} />
        )}
        {rules.data && <div className="pager muted small">Правил: {rules.data.length}</div>}
      </div>
      {editing && (
        <Modal title={editing.id ? 'Изменение правила матрицы' : 'Новое правило матрицы'} onClose={() => setEditing(null)}
          footer={<><button className="btn" onClick={() => setEditing(null)}>Отмена</button><button className="btn primary" onClick={save}>Сохранить</button></>}>
          <div className="alert info small">Пустые поля означают «любое значение». Правило с ролью без операции разрешает стандартный состав роли (см. «Системы и операции → Роли»); операции сверх состава будут выявлены как избыточные.</div>
          <ErrorBox error={formError} />
          <FormFields fields={fields} form={editing.form} setForm={(f) => setEditing({ ...editing, form: f })} />
        </Modal>
      )}
      {importOpen && <MatrixImport versionId={version.id} onClose={() => { setImportOpen(false); rules.reload(); onChanged(); }} />}
    </div>
  );
}

function MatrixImport({ versionId, onClose }: { versionId: string; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [replace, setReplace] = useState(false);
  const [result, setResult] = useState<any>(null);
  const { busy, run } = useAction();
  const submit = async () => {
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    fd.append('replace', String(replace));
    const r = await run(() => api.upload(`/matrix/versions/${versionId}/import`, fd), 'Импорт выполнен');
    if (r) setResult(r);
  };
  return (
    <Modal title="Импорт правил матрицы" onClose={onClose} wide footer={<><button className="btn" onClick={onClose}>Закрыть</button><button className="btn primary" disabled={!file || busy} onClick={submit}>Загрузить</button></>}>
      <p className="muted">Колонки: Код системы*, Код подразделения, Код должности, Код роли, Код модуля, Код операции, Эффект (ALLOW/DENY), Критичность, Основание*, Владелец*, Дата начала, Дата окончания. Пусто или «*» — любое значение. Шаблон: <code>docs/import-templates/matrix_rules.csv</code></p>
      <div className="grid">
        <Field label="Файл XLSX или CSV"><input type="file" accept=".xlsx,.csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
        <label className="check"><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Заменить все правила черновика</label>
      </div>
      {result && (
        <div style={{ marginTop: 12 }}>
          <div className="alert ok">Импортировано правил: {result.ok}. Ошибок: {result.errors.length}.</div>
          {result.errors.length > 0 && <DataTable rows={result.errors} columns={[{ key: 'row', label: 'Строка' }, { key: 'error', label: 'Ошибка' }]} />}
        </div>
      )}
    </Modal>
  );
}

function SeverityPolicy() {
  const { can } = useAuth();
  const settings = useLoad<any>(() => api.get('/admin/settings'));
  const [policy, setPolicy] = useState<Record<string, any> | null>(null);
  const { busy, run } = useAction();
  useEffect(() => { if (settings.data) setPolicy({ ...settings.data.severity_policy }); }, [settings.data]);
  if (!can('matrix.edit', 'settings.manage')) return <div className="alert info">Политику критичности настраивает администратор матрицы.</div>;
  if (!policy) return <><ErrorBox error={settings.error} /><Loading /></>;
  const keys = [...Object.keys(FINDING_TYPE).filter((k) => k !== 'SOD_CONFLICT'), 'MATRIX_DEVIATION_WITH_EXCEPTION', 'EXCEPTION_EXPIRED'];
  const labels: Record<string, string> = { ...FINDING_TYPE, MATRIX_DEVIATION_WITH_EXCEPTION: 'Отклонение, покрытое исключением', EXCEPTION_EXPIRED: 'Истёкшее исключение (справочно)' };
  return (
    <div className="card">
      <p className="muted">Базовая критичность по типу находки. При включённой эскалации критичность повышается до уровня риска операции (например, лишняя операция «Удаление платежа» с риском CRITICAL станет критической). Критичность SoD-конфликта задаётся в самом SoD-правиле. Политика фиксируется в снимке каждого аудита.</p>
      <div className="form">
        {keys.map((k) => (
          <Field key={k} label={labels[k] ?? k}>
            <select value={policy[k] ?? ''} disabled={!can('matrix.edit')} onChange={(e) => setPolicy({ ...policy, [k]: e.target.value })}>
              {SEVERITIES.map((s) => <option key={s} value={s}>{SEVERITY[s]}</option>)}
            </select>
          </Field>
        ))}
        <label className="check full"><input type="checkbox" checked={policy.escalate_by_operation_risk !== false} disabled={!can('matrix.edit')} onChange={(e) => setPolicy({ ...policy, escalate_by_operation_risk: e.target.checked })} /> Эскалировать критичность по уровню риска операции</label>
      </div>
      {can('matrix.edit') && <div style={{ marginTop: 14 }}><button className="btn primary" disabled={busy} onClick={() => run(() => api.put('/admin/severity-policy', policy), 'Политика сохранена')}>Сохранить политику</button></div>}
    </div>
  );
}
