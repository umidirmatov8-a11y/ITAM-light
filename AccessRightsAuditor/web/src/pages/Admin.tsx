import { useEffect, useState } from 'react';
import { useAuth } from '../auth';
import { api, qs } from '../api';
import { DataTable, FormFields } from '../components/crud';
import { Badge, confirmAction, ErrorBox, Loading, Modal, PageHead, Tabs, useAction, useDebounced, useLoad } from '../components/ui';
import { APP_ROLES, fmtDateTime } from '../i18n';

type Tab = 'users' | 'roles' | 'activity' | 'settings' | 'backup';

export function AdminPage() {
  const { can } = useAuth();
  const items: Array<{ id: Tab; label: string; hidden?: boolean }> = [
    { id: 'users', label: 'Пользователи', hidden: !can('users.manage') },
    { id: 'roles', label: 'Роли приложения', hidden: !can('users.manage') },
    { id: 'activity', label: 'Журнал действий', hidden: !can('activity.view') },
    { id: 'settings', label: 'Параметры', hidden: !can('settings.manage') },
    { id: 'backup', label: 'Резервное копирование', hidden: !can('backup.manage') },
  ];
  const visible = items.filter((i) => !i.hidden);
  const [tab, setTab] = useState<Tab>(visible[0]?.id ?? 'activity');
  if (!visible.length) return <div className="alert info">Политика критичности находится в разделе «Матрица полномочий».</div>;
  return (
    <div>
      <PageHead title="Пользователи и настройки" sub="Права в ARA отделены от анализируемых банковских ролей. Все административные действия журналируются." />
      <Tabs value={tab} onChange={setTab} items={items} />
      {tab === 'users' && <Users />}
      {tab === 'roles' && <Roles />}
      {tab === 'activity' && <Activity />}
      {tab === 'settings' && <Settings />}
      {tab === 'backup' && <Backup />}
    </div>
  );
}

function Users() {
  const { user } = useAuth();
  const users = useLoad<any[]>(() => api.get('/admin/users'));
  const [editing, setEditing] = useState<{ id?: string; form: Record<string, any> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ username: string; password: string } | null>(null);
  const { busy, run } = useAction();

  const save = async () => {
    if (!editing) return;
    setError(null);
    const { username, fullName, isActive, roles, password } = editing.form;
    try {
      if (editing.id) await api.put(`/admin/users/${editing.id}`, { fullName, isActive, roles });
      else {
        const r = await api.post('/admin/users', { username, fullName, isActive, roles, password: password || undefined });
        if (r.temporaryPassword) setSecret({ username, password: r.temporaryPassword });
      }
      setEditing(null);
      users.reload();
    } catch (e: any) { setError(e.message); }
  };

  return (
    <div>
      <div className="filters"><div className="spacer" /><button className="btn primary" onClick={() => { setError(null); setEditing({ form: { isActive: true, roles: ['AUDITOR'] } }); }}>+ Пользователь</button></div>
      {secret && <div className="alert warn">Временный пароль пользователя <b>{secret.username}</b>: <code>{secret.password}</code> — передайте его защищённым каналом. При первом входе потребуется смена. <button className="btn small" onClick={() => setSecret(null)}>Скрыть</button></div>}
      <ErrorBox error={users.error} />
      <div className="card flush">
        {users.loading && !users.data ? <Loading /> : (
          <DataTable rows={users.data ?? []} onRowClick={(r) => { setError(null); setEditing({ id: r.id, form: { username: r.username, fullName: r.full_name, isActive: r.is_active, roles: r.roles } }); }}
            columns={[
              { key: 'username', label: 'Логин', render: (r) => <b>{r.username}</b> }, { key: 'full_name', label: 'ФИО' },
              { key: 'roles', label: 'Роли', render: (r) => <span className="small">{r.roles.map((x: string) => APP_ROLES[x] ?? x).join(', ')}</span> },
              { key: 'is_active', label: 'Статус', render: (r) => (r.locked_until && new Date(r.locked_until) > new Date() ? <Badge value="HIGH" label="Заблокирован" /> : r.is_active ? <Badge value="ACTIVE" label="Активен" /> : <Badge value="DRAFT" label="Отключён" />) },
              { key: 'must_change_password', label: 'Временный пароль', render: (r) => (r.must_change_password ? 'да' : '') },
              { key: 'last_login_at', label: 'Последний вход', render: (r) => fmtDateTime(r.last_login_at) },
            ]}
            actions={(r) => (
              <div className="row" style={{ gap: 6 }}>
                <button className="btn small" disabled={busy} onClick={async () => { if (confirmAction(`Сбросить пароль пользователя ${r.username}?`)) { const x = await run(() => api.post(`/admin/users/${r.id}/reset-password`)); if (x) { setSecret({ username: r.username, password: x.temporaryPassword }); users.reload(); } } }}>Сбросить пароль</button>
                {r.locked_until && new Date(r.locked_until) > new Date() && <button className="btn small" onClick={async () => { await run(() => api.post(`/admin/users/${r.id}/unlock`), 'Разблокирован'); users.reload(); }}>Разблокировать</button>}
              </div>
            )} />
        )}
      </div>
      {editing && (
        <Modal title={editing.id ? `Пользователь ${editing.form.username}` : 'Новый пользователь'} onClose={() => setEditing(null)}
          footer={<><button className="btn" onClick={() => setEditing(null)}>Отмена</button><button className="btn primary" onClick={save}>Сохранить</button></>}>
          <ErrorBox error={error} />
          {editing.id === user?.id && <div className="alert warn small">Это ваша учётная запись: снять с себя роль администратора или отключить себя нельзя.</div>}
          <FormFields form={editing.form} setForm={(f) => setEditing({ ...editing, form: f })} fields={[
            { name: 'username', label: 'Логин', required: true, hidden: () => Boolean(editing.id) },
            { name: 'fullName', label: 'ФИО', required: true },
            { name: 'isActive', label: 'Активен', type: 'checkbox' },
            { name: 'password', label: 'Начальный пароль (пусто — сгенерировать)', hidden: () => Boolean(editing.id), hint: 'Не менее 10 символов, буквы и цифры. Пользователь сменит его при первом входе.' },
            { name: 'roles', label: 'Роли приложения (Ctrl — несколько)', type: 'multiselect', options: Object.entries(APP_ROLES).map(([value, label]) => ({ value, label })), required: true },
          ]} />
          <p className="muted small">Владелец системы видит находки только по системам, где он назначен владельцем (раздел «Системы и операции»).</p>
        </Modal>
      )}
    </div>
  );
}

const PERM_RU: Record<string, string> = {
  'users.manage': 'Управление пользователями', 'settings.manage': 'Настройки приложения', 'backup.manage': 'Резервное копирование', 'activity.view': 'Журнал действий',
  'reference.view': 'Просмотр справочников', 'reference.edit': 'Изменение справочников', 'matrix.edit': 'Изменение матрицы', 'matrix.approve': 'Утверждение матрицы',
  'sod.edit': 'Изменение SoD-правил', 'exceptions.view': 'Просмотр исключений', 'exceptions.edit': 'Ведение исключений', 'dashboard.view': 'Главная',
  'audit.view': 'Просмотр аудитов', 'audit.create': 'Создание аудитов', 'import.run': 'Импорт выгрузок', 'audit.run': 'Запуск аудита',
  'findings.view': 'Просмотр находок', 'findings.edit': 'Обработка находок', 'findings.comment': 'Комментарии к находкам', 'findings.scoped': 'Только свои системы',
  'reports.export': 'Экспорт отчётов', 'comparisons.run': 'Сравнение снимков',
};

function Roles() {
  const roles = useLoad<any[]>(() => api.get('/admin/roles'));
  return (
    <div className="card flush">
      <ErrorBox error={roles.error} />
      <DataTable rows={roles.data ?? []} columns={[
        { key: 'name', label: 'Роль', render: (r) => <><b>{r.name}</b><div className="small muted">{r.code}</div></> },
        { key: 'permissions', label: 'Разрешения', render: (r) => <span className="small">{r.permissions.map((p: string) => PERM_RU[p] ?? p).join(' · ')}</span> },
      ]} />
    </div>
  );
}

function Activity() {
  const [category, setCategory] = useState('');
  const [search, setSearch] = useState('');
  const s = useDebounced(search);
  const rows = useLoad<any[]>(() => api.get(`/admin/activity${qs({ category, search: s, limit: 500 })}`), [category, s]);
  const [open, setOpen] = useState<any>(null);
  return (
    <div>
      <div className="filters">
        <div className="field grow"><label>Поиск</label><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Действие, пользователь, объект" /></div>
        <div className="field"><label>Категория</label>
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Все</option><option value="AUTH">Входы и сессии</option><option value="ADMIN">Административные</option><option value="DATA">Справочники и исключения</option><option value="AUDIT">Аудиты и отчёты</option>
          </select>
        </div>
      </div>
      <div className="alert info small">Журнал неизменяем: изменение и удаление записей запрещено на уровне базы данных.</div>
      <ErrorBox error={rows.error} />
      <div className="card flush">
        <DataTable rows={rows.data ?? []} onRowClick={setOpen} columns={[
          { key: 'created_at', label: 'Время', render: (r) => fmtDateTime(r.created_at) }, { key: 'actor_name', label: 'Пользователь' },
          { key: 'category', label: 'Категория' }, { key: 'action', label: 'Действие', render: (r) => <code>{r.action}</code> },
          { key: 'entity', label: 'Объект', render: (r) => <span className="small">{r.entity_type} {r.entity_id ? <code>{String(r.entity_id).slice(0, 8)}</code> : ''}</span> },
          { key: 'ip', label: 'IP' },
        ]} />
      </div>
      {open && (
        <Modal wide title={`Запись журнала #${open.id}`} onClose={() => setOpen(null)}>
          <dl className="kv small"><dt>Время</dt><dd>{fmtDateTime(open.created_at)}</dd><dt>Пользователь</dt><dd>{open.actor_name}</dd><dt>Действие</dt><dd>{open.action}</dd><dt>Объект</dt><dd>{open.entity_type} {open.entity_id}</dd></dl>
          <div className="grid cols-2" style={{ marginTop: 12 }}>
            <div><h3>До</h3><pre className="side-box small pre">{open.before_json ? JSON.stringify(open.before_json, null, 2) : '—'}</pre></div>
            <div><h3>После</h3><pre className="side-box small pre">{open.after_json ? JSON.stringify(open.after_json, null, 2) : '—'}</pre></div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Settings() {
  const s = useLoad<any>(() => api.get('/admin/settings'));
  const info = useLoad<any>(() => api.get('/admin/system-info'));
  const [form, setForm] = useState<Record<string, any> | null>(null);
  const { busy, run } = useAction();
  useEffect(() => { if (s.data) setForm({ ...s.data }); }, [s.data]);
  if (!form) return <><ErrorBox error={s.error} /><Loading /></>;
  return (
    <div className="grid cols-2">
      <div className="card">
        <h2>Безопасность и хранение</h2>
        <FormFields form={form} setForm={setForm} fields={[
          { name: 'session_idle_minutes', label: 'Тайм-аут бездействия, мин', type: 'number' },
          { name: 'session_max_hours', label: 'Максимальная длительность сессии, ч', type: 'number' },
          { name: 'max_failed_logins', label: 'Неудачных попыток входа до блокировки', type: 'number' },
          { name: 'lockout_minutes', label: 'Длительность блокировки, мин', type: 'number' },
          { name: 'max_upload_mb', label: 'Максимальный размер загружаемого файла, МБ', type: 'number' },
          { name: 'retention_days', label: 'Срок хранения выгрузок и отчётов, дней', type: 'number', hint: 'Справочный параметр политики хранения банка' },
        ]} />
        <div style={{ marginTop: 14 }}>
          <button className="btn primary" disabled={busy} onClick={async () => { await run(() => api.put('/admin/settings', {
            session_idle_minutes: form.session_idle_minutes, session_max_hours: form.session_max_hours, max_failed_logins: form.max_failed_logins,
            lockout_minutes: form.lockout_minutes, max_upload_mb: form.max_upload_mb, retention_days: form.retention_days,
          }), 'Настройки сохранены'); s.reload(); }}>Сохранить</button>
        </div>
      </div>
      <div className="card">
        <h2>Сведения о системе</h2>
        <ErrorBox error={info.error} />
        {info.data && (
          <dl className="kv small">
            <dt>Node.js</dt><dd>{info.data.node}</dd>
            <dt>База данных</dt><dd>{info.data.db?.database} ({info.data.db?.size})</dd>
            <dt>PostgreSQL</dt><dd>{info.data.db?.version}</dd>
            <dt>TLS к PostgreSQL</dt><dd>{info.data.dbSsl === null ? 'нет данных' : info.data.dbSsl ? 'да' : 'нет (допустимо только для локального подключения)'}</dd>
            <dt>Адрес сервера</dt><dd>{info.data.host}:{info.data.port}</dd>
            <dt>Каталог данных</dt><dd><code>{info.data.dataDir}</code></dd>
          </dl>
        )}
      </div>
    </div>
  );
}

function Backup() {
  const list = useLoad<any[]>(() => api.get('/admin/backups'));
  const { busy, run } = useAction();
  return (
    <div>
      <div className="card">
        <h2>Резервное копирование</h2>
        <p className="muted">Создаёт дамп PostgreSQL (pg_dump, формат custom) и копию файлового хранилища (оригиналы импортов и отчёты) в каталоге <code>data/backups</code>. Для восстановления используйте <code>pg_restore</code> (см. README). Регулярно проверяйте восстановление.</p>
        <button className="btn primary" disabled={busy} onClick={async () => { await run(() => api.post('/admin/backups'), 'Резервная копия создана'); list.reload(); }}>{busy ? 'Создание…' : 'Создать резервную копию'}</button>
      </div>
      <ErrorBox error={list.error} />
      <div className="card flush">
        <DataTable rows={list.data ?? []} empty="Резервных копий нет" columns={[
          { key: 'name', label: 'Копия' }, { key: 'files', label: 'Состав', render: (r) => r.files.join(', ') },
          { key: 'size', label: 'Размер', render: (r) => `${(r.size / 1048576).toFixed(2)} МБ` },
        ]} />
      </div>
    </div>
  );
}
