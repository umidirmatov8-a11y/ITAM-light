import { useState } from 'react';
import { useAuth } from '../auth';
import { api } from '../api';
import { DataTable, enumOpt, FormFields } from '../components/crud';
import { Badge, confirmAction, ErrorBox, Field, Loading, Modal, PageHead, useAction, useLoad } from '../components/ui';
import { fmtDate, RISK } from '../i18n';
import { useLookups } from '../lookups';

interface Item { side: number; item_type: 'OPERATION' | 'ROLE'; operation_id: string; role_id: string }

export function SodPage() {
  const { can } = useAuth();
  const edit = can('sod.edit');
  const l = useLookups();
  const rules = useLoad<any[]>(() => api.get('/sod/rules'));
  const [editing, setEditing] = useState<{ id?: string; form: Record<string, any>; items: Item[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { busy, run } = useAction();

  const open = (r?: any) => {
    setError(null);
    if (!r) {
      setEditing({ form: { severity: 'HIGH', scope: 'EMPLOYEE', status: 'ACTIVE', valid_from: new Date().toISOString().slice(0, 10) }, items: [
        { side: 1, item_type: 'OPERATION', operation_id: '', role_id: '' }, { side: 2, item_type: 'OPERATION', operation_id: '', role_id: '' },
      ] });
      return;
    }
    const { items, id, created_at, updated_at, ...form } = r;
    void created_at; void updated_at;
    setEditing({ id, form: Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v ?? ''])), items: items.map((i: any) => ({ side: i.side, item_type: i.item_type, operation_id: i.operation_id ?? '', role_id: i.role_id ?? '' })) });
  };
  const save = async () => {
    if (!editing) return;
    setError(null);
    const body = { ...editing.form, items: editing.items };
    try {
      if (editing.id) await api.put(`/sod/rules/${editing.id}`, body);
      else await api.post('/sod/rules', body);
      setEditing(null);
      rules.reload();
    } catch (e: any) { setError(e.message); }
  };
  const setItem = (i: number, patch: Partial<Item>) => editing && setEditing({ ...editing, items: editing.items.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
  const sysCode = (sid: string) => l?.systems.find((s) => s.id === sid)?.code ?? '';

  return (
    <div>
      <PageHead title="SoD-правила" sub="Конфликтующие полномочия (разделение обязанностей). Конфликт фиксируется, если у сотрудника есть хотя бы одно полномочие каждой стороны. Внутри стороны элементы объединяются по «ИЛИ».">
        {edit && <button className="btn primary" onClick={() => open()}>+ Правило SoD</button>}
      </PageHead>
      <ErrorBox error={rules.error} />
      <div className="card flush">
        {rules.loading && !rules.data ? <Loading /> : (
          <DataTable rows={rules.data ?? []} onRowClick={edit ? open : undefined} empty="SoD-правила не заданы"
            columns={[
              { key: 'code', label: 'Код', render: (r) => <b>{r.code}</b> }, { key: 'name', label: 'Наименование' },
              { key: 'severity', label: 'Критичность', render: (r) => <Badge value={r.severity} label={RISK} /> },
              { key: 'items', label: 'Конфликтующие полномочия', render: (r) => {
                const sides = [...new Set<number>(r.items.map((i: any) => i.side))].sort();
                return <span className="small">{sides.map((s) => r.items.filter((i: any) => i.side === s).map((i: any) => i.label).join(' или ')).join('  ×  ')}</span>;
              } },
              { key: 'scope', label: 'Область', render: (r) => (r.scope === 'EMPLOYEE' ? 'Сотрудник (все системы)' : 'Сотрудник в пределах системы') },
              { key: 'compensating_control', label: 'Компенсирующий контроль', render: (r) => (r.compensating_control ? <span className="small">{r.compensating_control}<div className="muted">утв.: {r.compensating_approved_by}</div></span> : <span className="badge HIGH">жёсткий конфликт</span>) },
              { key: 'period', label: 'Период', render: (r) => `${fmtDate(r.valid_from)} — ${r.valid_to ? fmtDate(r.valid_to) : '∞'}` },
              { key: 'status', label: 'Статус', render: (r) => <Badge value={r.status} label={{ ACTIVE: 'Активно', INACTIVE: 'Неактивно' }} /> },
            ]}
            actions={edit ? (r) => <button className="btn small danger" disabled={busy} onClick={async () => { if (confirmAction(`Удалить правило ${r.code}? Рекомендуется деактивация.`)) { await run(() => api.del(`/sod/rules/${r.id}`), 'Правило удалено'); rules.reload(); } }}>Удалить</button> : undefined} />
        )}
      </div>
      <div className="alert info">Найденные конфликты SoD отображаются в результатах аудита (вкладка «Находки», тип «Конфликт SoD») с обеими сторонами конфликта и исходными назначениями.</div>
      {editing && (
        <Modal wide title={editing.id ? 'Изменение правила SoD' : 'Новое правило SoD'} onClose={() => setEditing(null)}
          footer={<><button className="btn" onClick={() => setEditing(null)}>Отмена</button><button className="btn primary" onClick={save}>Сохранить</button></>}>
          <ErrorBox error={error} />
          <FormFields form={editing.form} setForm={(f) => setEditing({ ...editing, form: f })} fields={[
            { name: 'code', label: 'Код', required: true }, { name: 'name', label: 'Наименование', required: true },
            { name: 'severity', label: 'Критичность', type: 'select', options: enumOpt(RISK), required: true },
            { name: 'scope', label: 'Область проверки', type: 'select', required: true, options: [{ value: 'EMPLOYEE', label: 'Сотрудник (все системы)' }, { value: 'EMPLOYEE_SYSTEM', label: 'Сотрудник в пределах одной системы' }] },
            { name: 'process', label: 'Бизнес-процесс' },
            { name: 'status', label: 'Статус', type: 'select', required: true, options: [{ value: 'ACTIVE', label: 'Активно' }, { value: 'INACTIVE', label: 'Неактивно' }] },
            { name: 'valid_from', label: 'Действует с', type: 'date', required: true }, { name: 'valid_to', label: 'Действует по', type: 'date' },
            { name: 'justification', label: 'Обоснование', type: 'textarea', required: true },
            { name: 'compensating_control', label: 'Компенсирующий контроль (если утверждён)', type: 'textarea' },
            { name: 'compensating_approved_by', label: 'Кем утверждён контроль (владелец процесса)' },
            { name: 'compensating_approved_at', label: 'Дата утверждения контроля', type: 'date' },
          ]} />
          <h3 style={{ marginTop: 16 }}>Конфликтующие полномочия</h3>
          {editing.items.map((it, i) => (
            <div className="row" key={i} style={{ marginBottom: 8, alignItems: 'flex-end' }}>
              <Field label="Сторона"><input type="number" min={1} max={10} value={it.side} onChange={(e) => setItem(i, { side: Number(e.target.value) || 1 })} style={{ width: 80 }} /></Field>
              <Field label="Тип">
                <select value={it.item_type} onChange={(e) => setItem(i, { item_type: e.target.value as Item['item_type'] })}><option value="OPERATION">Операция</option><option value="ROLE">Роль</option></select>
              </Field>
              <div style={{ flex: 1, minWidth: 260 }}>
                <Field label={it.item_type === 'OPERATION' ? 'Операция' : 'Роль'}>
                  {it.item_type === 'OPERATION' ? (
                    <select value={it.operation_id} onChange={(e) => setItem(i, { operation_id: e.target.value })}>
                      <option value="">— выберите —</option>
                      {(l?.operations ?? []).map((o) => <option key={o.id} value={o.id}>{sysCode(o.system_id)} / {o.code} — {o.name}</option>)}
                    </select>
                  ) : (
                    <select value={it.role_id} onChange={(e) => setItem(i, { role_id: e.target.value })}>
                      <option value="">— выберите —</option>
                      {(l?.roles ?? []).map((o) => <option key={o.id} value={o.id}>{sysCode(o.system_id)} / {o.code} — {o.name}</option>)}
                    </select>
                  )}
                </Field>
              </div>
              <button className="btn small danger" disabled={editing.items.length <= 2} onClick={() => setEditing({ ...editing, items: editing.items.filter((_, j) => j !== i) })}>×</button>
            </div>
          ))}
          <button className="btn small" onClick={() => setEditing({ ...editing, items: [...editing.items, { side: Math.max(...editing.items.map((x) => x.side)), item_type: 'OPERATION', operation_id: '', role_id: '' }] })}>+ Элемент</button>
        </Modal>
      )}
    </div>
  );
}
