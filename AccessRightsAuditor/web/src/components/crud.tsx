import { ReactNode, useMemo, useState } from 'react';
import { api, qs } from '../api';
import { confirmAction, ErrorBox, Field, Loading, Modal, useAction, useDebounced, useLoad } from './ui';

export type Option = { value: string; label: string };
export interface FormField {
  name: string;
  label: string;
  type?: 'text' | 'select' | 'date' | 'checkbox' | 'textarea' | 'multiselect' | 'number';
  options?: Option[] | ((form: Record<string, any>) => Option[]);
  required?: boolean;
  full?: boolean;
  hint?: string;
  emptyLabel?: string;
  hidden?: (form: Record<string, any>) => boolean;
  /** При изменении поля сбрасывать указанные зависимые поля */
  resets?: string[];
}

export interface Column<T = any> {
  key: string;
  label: string;
  render?: (row: T) => ReactNode;
  className?: string;
}

export function FormFields({ fields, form, setForm }: { fields: FormField[]; form: Record<string, any>; setForm: (f: Record<string, any>) => void }) {
  const set = (f: FormField, v: unknown) => {
    const next = { ...form, [f.name]: v };
    for (const r of f.resets ?? []) next[r] = Array.isArray(form[r]) ? [] : '';
    setForm(next);
  };
  return (
    <div className="form">
      {fields.filter((f) => !f.hidden?.(form)).map((f) => {
        const opts = typeof f.options === 'function' ? f.options(form) : f.options ?? [];
        const v = form[f.name];
        let input: ReactNode;
        switch (f.type) {
          case 'select':
            input = (
              <select value={v ?? ''} onChange={(e) => set(f, e.target.value)} required={f.required}>
                <option value="">{f.emptyLabel ?? (f.required ? '— выберите —' : '— любое / не задано —')}</option>
                {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            );
            break;
          case 'multiselect':
            input = (
              <select multiple value={v ?? []} size={Math.min(10, Math.max(4, opts.length))} onChange={(e) => set(f, [...e.target.selectedOptions].map((o) => o.value))}>
                {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            );
            break;
          case 'checkbox':
            input = <label className="check"><input type="checkbox" checked={Boolean(v)} onChange={(e) => set(f, e.target.checked)} /> да</label>;
            break;
          case 'textarea':
            input = <textarea value={v ?? ''} onChange={(e) => set(f, e.target.value)} required={f.required} />;
            break;
          case 'date':
            input = <input type="date" value={v ?? ''} onChange={(e) => set(f, e.target.value)} required={f.required} />;
            break;
          case 'number':
            input = <input type="number" value={v ?? ''} onChange={(e) => set(f, e.target.value)} required={f.required} />;
            break;
          default:
            input = <input value={v ?? ''} onChange={(e) => set(f, e.target.value)} required={f.required} />;
        }
        return <Field key={f.name} label={f.label} required={f.required} hint={f.hint} full={f.full || f.type === 'textarea' || f.type === 'multiselect'}>{input}</Field>;
      })}
    </div>
  );
}

export function DataTable<T extends Record<string, any>>({ rows, columns, onRowClick, actions, empty = 'Нет данных' }: {
  rows: T[]; columns: Column<T>[]; onRowClick?: (r: T) => void; actions?: (r: T) => ReactNode; empty?: string;
}) {
  if (!rows.length) return <div className="empty">{empty}</div>;
  return (
    <div className="table-wrap">
      <table className="t">
        <thead><tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}{actions && <th />}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id ?? i} className={onRowClick ? 'clickable' : ''} onClick={() => onRowClick?.(r)}>
              {columns.map((c) => <td key={c.key} className={c.className}>{c.render ? c.render(r) : r[c.key] ?? '—'}</td>)}
              {actions && <td onClick={(e) => e.stopPropagation()} style={{ whiteSpace: 'nowrap' }}>{actions(r)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export interface CrudProps {
  endpoint: string;
  columns: Column[];
  fields: FormField[];
  canEdit: boolean;
  entityName: string;
  defaults?: Record<string, any>;
  toForm?: (row: any) => Record<string, any>;
  toBody?: (form: Record<string, any>) => Record<string, any>;
  filters?: FormField[];
  searchable?: boolean;
  allowDelete?: boolean;
  toolbar?: ReactNode;
  rowActions?: (row: any, reload: () => void) => ReactNode;
  onSaved?: () => void;
}

/** Универсальная таблица справочника с формой создания/редактирования. */
export function CrudTable(p: CrudProps) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<Record<string, any>>({});
  const s = useDebounced(search);
  const query = useMemo(() => qs({ search: s, ...filter }), [s, filter]);
  const { data, error, loading, reload } = useLoad<any[]>(() => api.get(`${p.endpoint}${query}`), [p.endpoint, query]);
  const [editing, setEditing] = useState<{ id?: string; form: Record<string, any> } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const { busy, run } = useAction();

  const open = (row?: any) => {
    setFormError(null);
    setEditing(row ? { id: row.id, form: p.toForm ? p.toForm(row) : { ...row } } : { form: { ...(p.defaults ?? {}) } });
  };
  const save = async () => {
    if (!editing) return;
    setFormError(null);
    const missing = p.fields.filter((f) => f.required && !f.hidden?.(editing.form) && (editing.form[f.name] === undefined || editing.form[f.name] === '' || editing.form[f.name] === null));
    if (missing.length) { setFormError(`Заполните обязательные поля: ${missing.map((f) => f.label).join(', ')}`); return; }
    const body = p.toBody ? p.toBody(editing.form) : editing.form;
    try {
      if (editing.id) await api.put(`${p.endpoint}/${editing.id}`, body);
      else await api.post(p.endpoint, body);
      setEditing(null);
      reload();
      p.onSaved?.();
    } catch (e: any) {
      setFormError(e.message);
    }
  };
  const remove = (row: any) => {
    if (!confirmAction(`Удалить запись «${row.name ?? row.code ?? row.full_name ?? row.alias ?? ''}»?`)) return;
    run(() => api.del(`${p.endpoint}/${row.id}`), 'Запись удалена').then(() => { reload(); p.onSaved?.(); });
  };

  return (
    <div>
      <div className="filters">
        {p.searchable !== false && (
          <div className="field grow"><label>Поиск</label><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Код, наименование…" /></div>
        )}
        {p.filters?.map((f) => {
          const opts = typeof f.options === 'function' ? f.options(filter) : f.options ?? [];
          return (
            <div className="field" key={f.name}>
              <label>{f.label}</label>
              <select value={filter[f.name] ?? ''} onChange={(e) => setFilter({ ...filter, [f.name]: e.target.value })}>
                <option value="">Все</option>
                {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          );
        })}
        <div className="spacer" />
        {p.toolbar}
        {p.canEdit && <button className="btn primary" onClick={() => open()}>+ Добавить</button>}
      </div>
      <ErrorBox error={error} />
      <div className="card flush">
        {loading && !data ? <Loading /> : (
          <DataTable rows={data ?? []} columns={p.columns} onRowClick={p.canEdit ? open : undefined}
            actions={(r) => <>{p.rowActions?.(r, reload)}{p.canEdit && p.allowDelete !== false && <button className="btn small danger" disabled={busy} onClick={() => remove(r)}>Удалить</button>}</>} />
        )}
        {data && <div className="pager muted small">Записей: {data.length}</div>}
      </div>
      {editing && (
        <Modal title={`${editing.id ? 'Изменение' : 'Добавление'}: ${p.entityName}`} onClose={() => setEditing(null)}
          footer={<><button className="btn" onClick={() => setEditing(null)}>Отмена</button><button className="btn primary" onClick={save}>Сохранить</button></>}>
          <ErrorBox error={formError} />
          <FormFields fields={p.fields} form={editing.form} setForm={(f) => setEditing({ ...editing, form: f })} />
        </Modal>
      )}
    </div>
  );
}

export const opt = (rows: any[] | undefined, label: (r: any) => string = (r) => `${r.code} — ${r.name}`): Option[] => (rows ?? []).map((r) => ({ value: r.id, label: label(r) }));
export const enumOpt = (m: Record<string, string>): Option[] => Object.entries(m).map(([value, label]) => ({ value, label }));
