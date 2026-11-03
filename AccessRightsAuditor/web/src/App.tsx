import { FormEvent, ReactNode, useState } from 'react';
import { Navigate, NavLink, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth';
import { api } from './api';
import { APP_ROLES } from './i18n';
import { ErrorBox, Field } from './components/ui';
import { DashboardPage } from './pages/Dashboard';
import { SystemsPage } from './pages/Systems';
import { ReferencePage } from './pages/Reference';
import { MatrixPage } from './pages/Matrix';
import { AuditsPage } from './pages/Audits';
import { AuditDetailPage } from './pages/AuditDetail';
import { SodPage } from './pages/Sod';
import { ExceptionsPage } from './pages/Exceptions';
import { HistoryPage } from './pages/History';
import { AdminPage } from './pages/Admin';

const Logo = () => (
  <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7" fill="#1f4e8c" /><path d="M16 6l8 3v6c0 5-3.4 9.2-8 11-4.6-1.8-8-6-8-11V9z" fill="none" stroke="#fff" strokeWidth="2.2" /><path d="M12 16l3 3 5-6" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
);

function LoginForm({ lockedFor }: { lockedFor?: string }) {
  const { login } = useAuth();
  const [username, setU] = useState(lockedFor ?? '');
  const [password, setP] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try { await login(username, password); } catch (er: any) { setError(er.message); } finally { setBusy(false); }
  };
  return (
    <form className="card login" onSubmit={submit}>
      <div className="brand-big"><Logo /><div><h1 style={{ fontSize: 18 }}>Access Rights Auditor</h1><div className="muted small">Система аудита банковских полномочий</div></div></div>
      {lockedFor && <div className="alert info">Сессия заблокирована из-за бездействия. Войдите снова.</div>}
      <ErrorBox error={error} />
      <div className="grid">
        <Field label="Имя пользователя"><input autoFocus={!lockedFor} value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" required /></Field>
        <Field label="Пароль"><input autoFocus={Boolean(lockedFor)} type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required /></Field>
        <button className="btn primary" disabled={busy} type="submit" style={{ justifyContent: 'center' }}>{busy ? 'Вход…' : 'Войти'}</button>
      </div>
    </form>
  );
}

function ChangePassword({ forced, onDone }: { forced?: boolean; onDone?: () => void }) {
  const { refresh, logout } = useAuth();
  const [f, setF] = useState({ currentPassword: '', newPassword: '', repeat: '' });
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (f.newPassword !== f.repeat) { setError('Пароли не совпадают'); return; }
    try {
      await api.post('/auth/change-password', { currentPassword: f.currentPassword, newPassword: f.newPassword });
      setOk(true);
      await refresh();
      onDone?.();
    } catch (er: any) { setError(er.message); }
  };
  return (
    <form className="card login" onSubmit={submit}>
      <h2>{forced ? 'Смена временного пароля' : 'Смена пароля'}</h2>
      {forced && <div className="alert warn">Перед началом работы необходимо сменить временный пароль.</div>}
      <ErrorBox error={error} />
      {ok && <div className="alert ok">Пароль изменён</div>}
      <div className="grid">
        <Field label="Текущий пароль"><input type="password" value={f.currentPassword} onChange={(e) => setF({ ...f, currentPassword: e.target.value })} autoComplete="current-password" required /></Field>
        <Field label="Новый пароль" hint="Не менее 10 символов, буквы и цифры"><input type="password" value={f.newPassword} onChange={(e) => setF({ ...f, newPassword: e.target.value })} autoComplete="new-password" required /></Field>
        <Field label="Повторите новый пароль"><input type="password" value={f.repeat} onChange={(e) => setF({ ...f, repeat: e.target.value })} autoComplete="new-password" required /></Field>
        <div className="row"><button className="btn primary" type="submit">Сменить пароль</button>{forced && <button type="button" className="btn" onClick={logout}>Выйти</button>}</div>
      </div>
    </form>
  );
}

function Guard({ perm, children }: { perm: string[]; children: ReactNode }) {
  const { can } = useAuth();
  if (!can(...perm)) return <div className="alert error">Недостаточно прав для просмотра раздела</div>;
  return <>{children}</>;
}

export function App() {
  const { user, ready, locked, logout, can } = useAuth();
  const [showPwd, setShowPwd] = useState(false);
  if (!ready) return <div className="empty">Загрузка…</div>;
  if (!user) return <div className="login-wrap"><LoginForm /></div>;
  if (user.mustChangePassword) return <div className="login-wrap"><ChangePassword forced /></div>;

  const nav: Array<{ to: string; label: string; perm: string[]; group?: string }> = [
    { to: '/', label: 'Главная', perm: ['dashboard.view'] },
    { to: '/audits', label: 'Аудиты и импорт', perm: ['audit.view'], group: 'Аудит' },
    { to: '/history', label: 'История и сравнение', perm: ['audit.view'] },
    { to: '/exceptions', label: 'Исключения', perm: ['exceptions.view'] },
    { to: '/matrix', label: 'Матрица полномочий', perm: ['reference.view'], group: 'Нормативные данные' },
    { to: '/sod', label: 'SoD-правила', perm: ['reference.view'] },
    { to: '/systems', label: 'Системы и операции', perm: ['reference.view'] },
    { to: '/reference', label: 'Оргструктура и кадры', perm: ['reference.view'] },
    { to: '/admin', label: 'Пользователи и настройки', perm: ['users.manage', 'settings.manage', 'activity.view', 'backup.manage', 'matrix.edit'], group: 'Администрирование' },
  ];

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand"><Logo /><div>ARA<small>Access Rights Auditor</small></div></div>
        <nav className="nav">
          {nav.filter((n) => can(...n.perm)).map((n) => (
            <div key={n.to}>
              {n.group && <div className="group">{n.group}</div>}
              <NavLink to={n.to} end={n.to === '/'}>{n.label}</NavLink>
            </div>
          ))}
        </nav>
        <div className="userbox">
          <b>{user.fullName}</b>
          <div>{user.roles.map((r) => APP_ROLES[r] ?? r).join(', ')}</div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn small" onClick={() => setShowPwd(true)}>Пароль</button>
            <button className="btn small" onClick={logout}>Выйти</button>
          </div>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Guard perm={['dashboard.view']}><DashboardPage /></Guard>} />
          <Route path="/audits" element={<Guard perm={['audit.view']}><AuditsPage /></Guard>} />
          <Route path="/audits/:id" element={<Guard perm={['audit.view']}><AuditDetailPage /></Guard>} />
          <Route path="/history" element={<Guard perm={['audit.view']}><HistoryPage /></Guard>} />
          <Route path="/exceptions" element={<Guard perm={['exceptions.view']}><ExceptionsPage /></Guard>} />
          <Route path="/matrix" element={<Guard perm={['reference.view']}><MatrixPage /></Guard>} />
          <Route path="/sod" element={<Guard perm={['reference.view']}><SodPage /></Guard>} />
          <Route path="/systems" element={<Guard perm={['reference.view']}><SystemsPage /></Guard>} />
          <Route path="/reference" element={<Guard perm={['reference.view']}><ReferencePage /></Guard>} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      {showPwd && <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && setShowPwd(false)}><div><ChangePassword onDone={() => setTimeout(() => setShowPwd(false), 800)} /></div></div>}
      {locked && <div className="lock"><LoginForm lockedFor={user.username} /></div>}
    </div>
  );
}
