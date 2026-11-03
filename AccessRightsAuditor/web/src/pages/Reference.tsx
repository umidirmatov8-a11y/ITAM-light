import { useState } from 'react';
import { useAuth } from '../auth';
import { api } from '../api';
import { CrudTable, DataTable, enumOpt, opt } from '../components/crud';
import { Badge, ErrorBox, PageHead, Tabs, useAction, useLoad } from '../components/ui';
import { EMPLOYMENT, ENTITY_TYPE, fmtDate } from '../i18n';
import { invalidateLookups, useLookups } from '../lookups';

type Tab = 'employees' | 'departments' | 'positions' | 'aliases' | 'import';

export function ReferenceImport({ kind }: { kind: 'employees' | 'catalog' }) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<any>(null);
  const { busy, run } = useAction();
  const submit = async () => {
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    const r = await run(() => api.upload(`/reference/import/${kind}`, fd), 'Импорт выполнен');
    if (r) { setResult(r); invalidateLookups(); }
  };
  return (
    <div className="card">
      <h2>{kind === 'employees' ? 'Импорт кадрового справочника' : 'Импорт каталога систем, ролей, модулей и операций'}</h2>
      <p className="muted">
        {kind === 'employees'
          ? 'Колонки: Табельный номер*, ФИО*, Код подразделения, Код должности, Статус (Работает/Уволен/Отпуск/Переведён), Дата приёма, Дата увольнения, Прежнее подразделение, Прежняя должность, Дата перевода. Запись обновляется по табельному номеру.'
          : 'Колонки: Код системы*, Наименование системы, Код роли*, Наименование роли, Код модуля, Наименование модуля, Код операции, Наименование операции, Риск (LOW/MEDIUM/HIGH/CRITICAL). Строка «роль + операция» добавляет операцию в состав роли.'}
        {' '}Шаблон: <code>docs/import-templates/{kind === 'employees' ? 'hr_employees.csv' : 'catalog_roles_operations.csv'}</code>
      </p>
      <div className="row">
        <input type="file" accept=".xlsx,.csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} style={{ maxWidth: 420 }} />
        <button className="btn primary" disabled={!file || busy} onClick={submit}>{busy ? 'Импорт…' : 'Загрузить'}</button>
      </div>
      {result && (
        <div style={{ marginTop: 14 }}>
          <div className="alert ok">Загружено строк: {result.ok}. Ошибок: {result.errors.length}.</div>
          {result.warnings?.map((w: string) => <div key={w} className="alert warn">{w}</div>)}
          {result.created?.length > 0 && <div className="alert info">Созданы автоматически: {result.created.join(', ')}</div>}
          {result.errors.length > 0 && <DataTable rows={result.errors} columns={[{ key: 'row', label: 'Строка' }, { key: 'error', label: 'Ошибка' }]} />}
        </div>
      )}
    </div>
  );
}

export function ReferencePage() {
  const { can } = useAuth();
  const edit = can('reference.edit');
  const l = useLookups();
  const [tab, setTab] = useState<Tab>('employees');
  const depOpt = opt(l?.departments);
  const posOpt = opt(l?.positions);
  const empOptions = useLoad<any[]>(() => api.get('/reference/employee-options?search='), []);

  const aliasTargets = (f: Record<string, any>) => {
    const t = f.entity_type;
    if (t === 'SYSTEM') return opt(l?.systems);
    if (t === 'ROLE') return opt((l?.roles ?? []).filter((r) => !f.system_id || r.system_id === f.system_id));
    if (t === 'MODULE') return opt((l?.modules ?? []).filter((r) => !f.system_id || r.system_id === f.system_id));
    if (t === 'OPERATION') return opt((l?.operations ?? []).filter((r) => !f.system_id || r.system_id === f.system_id));
    return (empOptions.data ?? []).map((e) => ({ value: e.id, label: `${e.employee_key} — ${e.full_name}` }));
  };

  return (
    <div>
      <PageHead title="Оргструктура и кадры" sub="Кадровый справочник: сотрудник сопоставляется только по табельному номеру / уникальному ID; ФИО — вспомогательный атрибут." />
      <Tabs value={tab} onChange={setTab} items={[
        { id: 'employees', label: 'Сотрудники' }, { id: 'departments', label: 'Подразделения' }, { id: 'positions', label: 'Должности' },
        { id: 'aliases', label: 'Алиасы (нормализация)' }, { id: 'import', label: 'Импорт кадров', hidden: !edit },
      ]} />
      {tab === 'employees' && (
        <CrudTable endpoint="/reference/employees" entityName="сотрудник" canEdit={edit} defaults={{ employment_status: 'ACTIVE', hr_source: 'HR' }}
          filters={[{ name: 'department_id', label: 'Подразделение', options: depOpt }, { name: 'employment_status', label: 'Статус', options: enumOpt(EMPLOYMENT) }]}
          columns={[
            { key: 'employee_key', label: 'Таб. №' }, { key: 'full_name', label: 'ФИО' }, { key: 'department_name', label: 'Подразделение' }, { key: 'position_name', label: 'Должность' },
            { key: 'employment_status', label: 'Статус', render: (r) => <Badge value={r.employment_status === 'TERMINATED' ? 'TERMINATED' : r.employment_status === 'ACTIVE' ? 'ACTIVE' : 'MEDIUM'} label={EMPLOYMENT[r.employment_status]} /> },
            { key: 'valid_from', label: 'Принят', render: (r) => fmtDate(r.valid_from) }, { key: 'valid_to', label: 'Уволен', render: (r) => fmtDate(r.valid_to) },
            { key: 'transferred_at', label: 'Перевод', render: (r) => (r.transferred_at ? `${fmtDate(r.transferred_at)} из ${r.previous_department_name ?? '—'} / ${r.previous_position_name ?? '—'}` : '—') },
          ]}
          fields={[
            { name: 'employee_key', label: 'Табельный номер / ID', required: true }, { name: 'full_name', label: 'ФИО', required: true },
            { name: 'department_id', label: 'Подразделение', type: 'select', options: depOpt }, { name: 'position_id', label: 'Должность', type: 'select', options: posOpt },
            { name: 'employment_status', label: 'Статус', type: 'select', options: enumOpt(EMPLOYMENT), required: true },
            { name: 'hr_source', label: 'Кадровый источник', required: true },
            { name: 'valid_from', label: 'Дата приёма', type: 'date' }, { name: 'valid_to', label: 'Дата увольнения', type: 'date', hint: 'Последний рабочий день' },
            { name: 'previous_department_id', label: 'Прежнее подразделение (при переводе)', type: 'select', options: depOpt },
            { name: 'previous_position_id', label: 'Прежняя должность (при переводе)', type: 'select', options: posOpt },
            { name: 'transferred_at', label: 'Дата перевода', type: 'date' },
          ]}
          toBody={(f) => { const { department_name, position_name, previous_department_name, previous_position_name, id, updated_at, ...rest } = f; void [department_name, position_name, previous_department_name, previous_position_name, id, updated_at]; return rest; }} />
      )}
      {tab === 'departments' && (
        <CrudTable endpoint="/reference/departments" entityName="подразделение" canEdit={edit} defaults={{ is_active: true }} onSaved={invalidateLookups}
          columns={[{ key: 'code', label: 'Код' }, { key: 'name', label: 'Наименование' }, { key: 'parent_name', label: 'Вышестоящее' }, { key: 'is_active', label: 'Активно', render: (r) => (r.is_active ? 'да' : 'нет') }]}
          fields={[
            { name: 'code', label: 'Код', required: true }, { name: 'name', label: 'Наименование', required: true },
            { name: 'parent_id', label: 'Вышестоящее подразделение', type: 'select', options: depOpt }, { name: 'is_active', label: 'Активно', type: 'checkbox' },
          ]}
          toBody={({ code, name, parent_id, is_active }) => ({ code, name, parent_id, is_active })} />
      )}
      {tab === 'positions' && (
        <CrudTable endpoint="/reference/positions" entityName="должность" canEdit={edit} defaults={{ is_active: true }} onSaved={invalidateLookups}
          columns={[{ key: 'code', label: 'Код' }, { key: 'name', label: 'Наименование' }, { key: 'is_active', label: 'Активна', render: (r) => (r.is_active ? 'да' : 'нет') }]}
          fields={[{ name: 'code', label: 'Код', required: true }, { name: 'name', label: 'Наименование', required: true }, { name: 'is_active', label: 'Активна', type: 'checkbox' }]}
          toBody={({ code, name, is_active }) => ({ code, name, is_active })} />
      )}
      {tab === 'aliases' && (
        <>
          <div className="alert info">Алиас связывает альтернативное написание из выгрузки (старый код роли, другое название системы, прежний табельный номер) с записью справочника. Используется при импорте и при сравнении снимков.</div>
          <CrudTable endpoint="/reference/aliases" entityName="алиас" canEdit={edit} defaults={{ entity_type: 'SYSTEM' }}
            filters={[{ name: 'entity_type', label: 'Тип', options: enumOpt(ENTITY_TYPE) }]}
            columns={[
              { key: 'entity_type', label: 'Тип', render: (r) => ENTITY_TYPE[r.entity_type] }, { key: 'alias', label: 'Значение в выгрузке' },
              { key: 'target_label', label: 'Запись справочника' }, { key: 'system_code', label: 'Система' },
            ]}
            fields={[
              { name: 'entity_type', label: 'Тип', type: 'select', options: enumOpt(ENTITY_TYPE), required: true, resets: ['target_id'] },
              { name: 'system_id', label: 'Система (для ролей/модулей/операций)', type: 'select', options: opt(l?.systems), resets: ['target_id'], hidden: (f) => f.entity_type === 'SYSTEM' || f.entity_type === 'EMPLOYEE' },
              { name: 'alias', label: 'Значение в выгрузке', required: true },
              { name: 'target_id', label: 'Запись справочника', type: 'select', options: aliasTargets, required: true },
            ]}
            toBody={({ entity_type, system_id, alias, target_id }) => ({ entity_type, system_id: entity_type === 'SYSTEM' || entity_type === 'EMPLOYEE' ? null : system_id, alias, target_id })} />
        </>
      )}
      {tab === 'import' && <ReferenceImport kind="employees" />}
      <ErrorBox error={empOptions.error} />
    </div>
  );
}
