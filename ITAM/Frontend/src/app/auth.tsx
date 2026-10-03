import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { get, post, ApiError } from '@/api/client';
import type { Me } from '@/api/types';
import { configureFormat } from '@/utils/format';
import { setLanguage } from '@/i18n';
import i18n from '@/i18n';

interface AuthState {
  me?: Me;
  loading: boolean;
  can: (permission: string) => boolean;
  canAny: (...permissions: string[]) => boolean;
  refresh: () => Promise<unknown>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({ loading: true, can: () => false, canAny: () => false, refresh: async () => undefined, logout: async () => undefined });

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const query = useQuery<Me | null>({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        const me = await get<Me>('/auth/me');
        configureFormat({ timeZone: me.timeZone || me.orgTimeZone, dateFormat: me.dateFormat, currency: me.currency });
        if (me.language && me.language !== i18n.language && !localStorage.getItem('itam.lang')) setLanguage(me.language);
        return me;
      } catch (e) {
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
  const me = query.data ?? undefined;
  const perms = useMemo(() => new Set(me?.permissions ?? []), [me]);
  const can = useCallback((p: string) => perms.has(p) || perms.has('system.admin'), [perms]);
  const canAny = useCallback((...ps: string[]) => ps.some((p) => perms.has(p)) || perms.has('system.admin'), [perms]);
  const logout = useCallback(async () => {
    try {
      await post('/auth/logout');
    } finally {
      qc.clear();
      window.location.href = '/login';
    }
  }, [qc]);
  return (
    <AuthContext.Provider value={{ me, loading: query.isLoading, can, canAny, refresh: () => query.refetch(), logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

export function Can({ perm, any, children, fallback = null }: { perm?: string; any?: string[]; children: ReactNode; fallback?: ReactNode }) {
  const { can, canAny } = useAuth();
  const allowed = perm ? can(perm) : any ? canAny(...any) : true;
  return <>{allowed ? children : fallback}</>;
}
