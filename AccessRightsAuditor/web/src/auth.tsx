import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { api, onUnauthorized } from './api';

export interface User {
  id: string;
  username: string;
  fullName: string;
  roles: string[];
  permissions: string[];
  mustChangePassword: boolean;
}

interface AuthState {
  user: User | null;
  ready: boolean;
  locked: boolean;
  idleMinutes: number;
  login: (u: string, p: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  can: (...perms: string[]) => boolean;
}

const Ctx = createContext<AuthState>(null as any);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [locked, setLocked] = useState(false);
  const [idleMinutes, setIdle] = useState(30);
  const lastActivity = useRef(Date.now());

  const refresh = useCallback(async () => {
    try {
      const r = await api.get('/auth/me');
      setUser(r.user ?? null);
      if (r.user) setIdle(r.idleMinutes);
      setLocked(false);
    } catch {
      setUser(null);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => onUnauthorized(() => { setUser((u) => { if (u) setLocked(true); return u; }); }), []);

  // Блокировка сессии по бездействию (сервер также завершает сессию по тайм-ауту).
  useEffect(() => {
    if (!user) return;
    const mark = () => { lastActivity.current = Date.now(); };
    const events = ['mousedown', 'keydown', 'scroll', 'touchstart'];
    events.forEach((e) => window.addEventListener(e, mark, { passive: true }));
    const t = setInterval(() => {
      if (!locked && Date.now() - lastActivity.current > idleMinutes * 60_000) {
        api.post('/auth/logout').catch(() => undefined);
        setLocked(true);
      }
    }, 15_000);
    return () => { events.forEach((e) => window.removeEventListener(e, mark)); clearInterval(t); };
  }, [user, idleMinutes, locked]);

  const login = async (username: string, password: string) => {
    const r = await api.post('/auth/login', { username, password });
    if (user && r.user.id !== user.id) window.location.assign('/');
    setUser(r.user);
    setLocked(false);
    lastActivity.current = Date.now();
    const me = await api.get('/auth/me');
    setIdle(me.idleMinutes);
  };
  const logout = async () => {
    await api.post('/auth/logout').catch(() => undefined);
    setUser(null);
    setLocked(false);
  };
  const can = (...perms: string[]) => Boolean(user && perms.some((p) => user.permissions.includes(p)));

  return <Ctx.Provider value={{ user, ready, locked, idleMinutes, login, logout, refresh, can }}>{children}</Ctx.Provider>;
}
