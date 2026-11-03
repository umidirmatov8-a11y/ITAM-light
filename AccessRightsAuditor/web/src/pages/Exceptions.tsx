import { useState } from 'react';
import { useAuth } from '../auth';
import { api, qs } from '../api';
import { DataTable, FormFields, opt } from '../components/crud';
import { Badge, confirmAction, ErrorBox, Loading, Modal, PageHead, useAction, useDebounced, useLoad } from '../components/ui';
import { EXC_STATUS, fmtDate } from '../i18n';
import { useLookups } from '../lookups';

const FIELDS = ['employee_id', 'system_id', 'role_id', 'operation_id', 'ticket_ref', 'author', 'approved_by', 'reason', 'valid_from', 'valid_to', 'compensating_control', 'status'];

export function ExceptionsPage() {
  const { can, user } = useAuth();
  const edit = can('exceptions.edit');
  const l = useLookups();
  const [filter, setFilter] = useState({ search: '', system_id: '', effective_status: '' });
  const search = useDebounced(filter.search);
  const list = useLoad<any[]>(() => api.get(`/exceptions${qs({ ...filter, search })}`), [filter.system_id, filter.effective_status, search]);
  const [empSearch, setEmpSearch] = useState('');
  const empQ = useDebounced(empSearch);
  const employees = useLoad<any[]>(() => api.get(`/reference/employee-options?search=${encodeURIComponent(empQ)}`), [empQ]);
  const [editing, setEditing] = useState<{ id?: string; form: Record<string, any>; empLabel?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { busy, run } = useAction();

  const open = (r?: any) => {
    setError(null);
    setEmpSearch('');
    if (r) setEditing({ id: r.id, form: Object.fromEntries(FIELDS.map((k) => [k, r[k] ?? ''])), empLabel: `${r.employee_key} — ${r.employee_name}` });
    else setEditing({ form: { status: 'APPROVED', author: user?.fullName ?? '', valid_from: new Date().toISOString().slice(0, 10) } });
  };
  const save = async () => {
    if (!editing) return;
    setError(null);
    try {
      if (editing.id) await api.put(`/exceptions/${editing.id}`, editing.form);
      else await api.post('/exceptions', editing.form);
      setEditing(null);
      list.reload();
    } catch (e: any) { setError(e.message); }
  };

  const empOptions = [
    ...(editing?.empLabel && editing.form.employee_id ? [{ value: editing.form.employee_id, label: editing.empLabel }] : []),
    ...(employees.data ?? []).filter((e) => e.id !== editing?.form.employee_id || !editing?.empLabel).map((e) => ({ value: e.id, label: `${e.employee_key} — ${e.full_name}` })),
  ];

  return (
    <div>
      <PageHead title="Журнал исключений" sub="Согласованные исключения не удаляют факт превышения: находка маркируется «Покрыто исключением». Истёкшие исключения выявляются при каждом запуске аудита и не считаются действующими.">
        {edit && <button className="btn primary" onClick={() => open()}>+ Исключение</button>}
      </PageHead>
      <div className="filters">
        <div className="field grow"><label>Поиск</label><input value={filter.search} onChange={(e) => setFilter({ ...filter, search: e.target.value })} placeholder="Номер заявки, ФИО, таб. №" /></div>
        <div className="field"><label>Система</label><select value={filter.system_id} onChange={(e) => setFilter({ ...filter, system_id: e.target.value })}><option value="">Все</option>{(l?.systems ?? []).map((s) => <option key={s.id} value={s.id}>{s.code}</option>)}</select></div>
        <div className="field"><label>Состояние</label><select value={filter.effective_status} onChange={(e) => setFilter({ ...filter, effective_status: e.target.value })}><option value="">Все</option>{['ACTIVE', 'EXPIRED', 'PENDING', 'DRAFT', 'REVOKED'].map((k) => <option key={k} value={k}>{EXC_STATUS[k]}</option>)}</select></div>
      </div>
      <ErrorBox error={list.error} />
      <div className="card flush">
        {list.loading && !list.data ? <Loading /> : (
          <DataTable rows={list.data ?? []} onRowClick={edit ? open : undefined} empty="Исключений нет"
            columns={[
              { key: 'ticket_ref', label: 'Заявка / решение', render: (r) => <b>{r.ticket_ref}</b> },
              { key: 'employee', label: 'Сотрудник', render: (r) => <>{r.employee_name}<div className="small muted">{r.employee_key}</div></> },
              { key: 'scope', label: 'Право', render: (r) => <>{r.system_code}{r.role_code && ` / роль ${r.role_code}`}{r.operation_code && ` / ${r.operation_code}`}</> },
              { key: 'reason', label: 'Причина', render: (r) => <span className="small">{r.reason}</span> },
              { key: 'approved_by', label: 'Согласовал' },
              { key: 'period', label: 'Срок', render: (r) => `${fmtDate(r.valid_from)} — ${fmtDate(r.valid_to)}` },
              { key: 'compensating_control', label: 'Компенсирующий контроль', render: (r) => <span className="small">{r.compensating_control}</span> },
              { key: 'effective_status', label: 'Состояние', render: (r) => <Badge value={r.effective_status} label={EXC_STATUS} /> },
            ]}
            actions={edit ? (r) => (r.status !== 'REVOKED' ? <button className="btn small danger" disabled={busy} onClick={async () => { if (confirmAction(`Отозвать исключение ${r.ticket_ref}?`)) { await run(() => api.post(`/exceptions/${r.id}/revoke`), 'Исключение отозвано'); list.reload(); } }}>Отозвать</button> : null) : undefined} />
        )}
      </div>
      {editing && (
        <Modal title={editing.id ? 'Изменение исключения' : 'Новое исключение'} onClose={() => setEditing(null)}
          footer={<><button className="btn" onClick={() => setEditing(null)}>Отмена</button><button className="btn primary" onClick={save}>Сохранить</button></>}>
          <ErrorBox error={error} />
          <div className="field" style={{ marginBottom: 10 }}>
            <label>Найти сотрудника (таб. № или ФИО)</label>
            <input value={empSearch} onChange={(e) => setEmpSearch(e.target.value)} placeholder="Начните вводить…" />
          </div>
          <FormFields form={editing.form} setForm={(f) => setEditing({ ...editing, form: f })} fields={[
            { name: 'employee_id', label: 'Сотрудник', type: 'select', options: empOptions, required: true, full: true },
            { name: 'system_id', label: 'Система', type: 'select', options: opt(l?.systems), required: true, resets: ['role_id', 'operation_id'] },
            { name: 'status', label: 'Статус', type: 'select', required: true, options: [{ value: 'APPROVED', label: 'Согласовано' }, { value: 'DRAFT', label: 'Черновик' }, { value: 'REVOKED', label: 'Отозвано' }] },
            { name: 'role_id', label: 'Роль', type: 'select', options: (f) => opt((l?.roles ?? []).filter((r) => r.system_id === f.system_id)), emptyLabel: '— любая роль —' },
            { name: 'operation_id', label: 'Операция', type: 'select', options: (f) => opt((l?.operations ?? []).filter((r) => r.system_id === f.system_id)), emptyLabel: '— любая операция —' },
            { name: 'ticket_ref', label: 'Номер заявки / решения', required: true }, { name: 'author', label: 'Автор', required: true },
            { name: 'approved_by', label: 'Согласующий', required: true }, { name: 'valid_from', label: 'Дата начала', type: 'date', required: true },
            { name: 'valid_to', label: 'Дата окончания', type: 'date', required: true },
            { name: 'reason', label: 'Причина', type: 'textarea', required: true },
            { name: 'compensating_control', label: 'Компенсирующий контроль', type: 'textarea', required: true },
          ]} />
        </Modal>
      )}
    </div>
  );
}
