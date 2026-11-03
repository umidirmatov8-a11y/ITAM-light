import { useState } from 'react';
import { useAuth } from '../auth';
import { api } from '../api';
import { CrudTable, enumOpt, opt } from '../components/crud';
import { Badge, PageHead, Tabs, useLoad } from '../components/ui';
import { RISK } from '../i18n';
import { invalidateLookups, useLookups } from '../lookups';
import { ReferenceImport } from './Reference';

type Tab = 'systems' | 'roles' | 'modules' | 'operations' | 'import';

export function SystemsPage() {
  const { can } = useAuth();
  const edit = can('reference.edit');
  const l = useLookups();
  const [tab, setTab] = useState<Tab>('systems');
  const users = useLoad<any[]>(() => api.get('/admin/user-options'));
  const sysOpt = opt(l?.systems);

  return (
    <div>
      <PageHead title="Системы и операции" sub="Каталог банковских систем, ролей, модулей и атомарных операций. Состав роли используется для разворачивания составных профилей." />
      <Tabs value={tab} onChange={setTab} items={[
        { id: 'systems', label: 'Системы' }, { id: 'roles', label: 'Роли' }, { id: 'modules', label: 'Модули' }, { id: 'operations', label: 'Операции' },
        { id: 'import', label: 'Импорт каталога', hidden: !edit },
      ]} />
      {tab === 'systems' && (
        <CrudTable endpoint="/reference/systems" entityName="система" canEdit={edit} defaults={{ is_active: true }}
          onSaved={invalidateLookups}
          columns={[
            { key: 'code', label: 'Код' }, { key: 'name', label: 'Наименование' }, { key: 'owner_name', label: 'Владелец' },
            { key: 'roles_count', label: 'Ролей', className: 'num' }, { key: 'operations_count', label: 'Операций', className: 'num' },
            { key: 'is_active', label: 'Активна', render: (r) => (r.is_active ? 'да' : 'нет') },
          ]}
          fields={[
            { name: 'code', label: 'Код', required: true }, { name: 'name', label: 'Наименование', required: true },
            { name: 'owner_user_id', label: 'Владелец системы (пользователь ARA)', type: 'select', options: opt(users.data ?? [], (u) => `${u.full_name} (${u.username})`), emptyLabel: '— не назначен —' },
            { name: 'is_active', label: 'Активна', type: 'checkbox' },
            { name: 'description', label: 'Описание', type: 'textarea' },
          ]} />
      )}
      {tab === 'roles' && (
        <CrudTable endpoint="/reference/roles" entityName="роль" canEdit={edit}
          filters={[{ name: 'system_id', label: 'Система', options: sysOpt }]}
          onSaved={invalidateLookups}
          columns={[
            { key: 'system_code', label: 'Система' }, { key: 'role_code', label: 'Код роли' }, { key: 'role_name', label: 'Наименование' },
            { key: 'operation_ids', label: 'Состав (операции)', render: (r) => {
              const ops = (r.operation_ids ?? []).map((id: string) => l?.operations.find((o) => o.id === id)?.code).filter(Boolean);
              return ops.length ? <span className="small">{ops.join(', ')}</span> : <span className="muted small">не задан</span>;
            } },
          ]}
          fields={[
            { name: 'system_id', label: 'Система', type: 'select', options: sysOpt, required: true, resets: ['operation_ids'] },
            { name: 'role_code', label: 'Код роли', required: true }, { name: 'role_name', label: 'Наименование', required: true },
            { name: 'description', label: 'Описание', type: 'textarea' },
            { name: 'operation_ids', label: 'Состав роли — операции (Ctrl/Shift для выбора нескольких)', type: 'multiselect',
              options: (f) => (l?.operations ?? []).filter((o) => o.system_id === f.system_id).map((o) => ({ value: o.id, label: `${o.code} — ${o.name}` })) },
          ]} />
      )}
      {tab === 'modules' && (
        <CrudTable endpoint="/reference/modules" entityName="модуль" canEdit={edit}
          filters={[{ name: 'system_id', label: 'Система', options: sysOpt }]}
          onSaved={invalidateLookups}
          columns={[{ key: 'system_code', label: 'Система' }, { key: 'code', label: 'Код' }, { key: 'name', label: 'Наименование' }]}
          fields={[
            { name: 'system_id', label: 'Система', type: 'select', options: sysOpt, required: true },
            { name: 'code', label: 'Код', required: true }, { name: 'name', label: 'Наименование', required: true },
          ]} />
      )}
      {tab === 'operations' && (
        <CrudTable endpoint="/reference/operations" entityName="операция" canEdit={edit} defaults={{ risk_level: 'MEDIUM' }}
          filters={[{ name: 'system_id', label: 'Система', options: sysOpt }]}
          onSaved={invalidateLookups}
          toBody={(f) => { const { system_id, ...rest } = f; void system_id; return rest; }}
          toForm={(r) => ({ ...r })}
          columns={[
            { key: 'system_code', label: 'Система' }, { key: 'module_code', label: 'Модуль' }, { key: 'code', label: 'Код' }, { key: 'name', label: 'Наименование' },
            { key: 'risk_level', label: 'Риск', render: (r) => <Badge value={r.risk_level} label={RISK} /> },
          ]}
          fields={[
            { name: 'system_id', label: 'Система', type: 'select', options: sysOpt, required: true, resets: ['module_id'] },
            { name: 'module_id', label: 'Модуль', type: 'select', required: true, options: (f) => opt((l?.modules ?? []).filter((m) => m.system_id === f.system_id)) },
            { name: 'code', label: 'Код', required: true }, { name: 'name', label: 'Наименование', required: true },
            { name: 'risk_level', label: 'Уровень риска', type: 'select', options: enumOpt(RISK), required: true, hint: 'Используется для эскалации критичности находок' },
          ]} />
      )}
      {tab === 'import' && <ReferenceImport kind="catalog" />}
    </div>
  );
}
