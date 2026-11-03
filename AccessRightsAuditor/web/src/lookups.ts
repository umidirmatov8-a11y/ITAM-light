import { useEffect, useState } from 'react';
import { api } from './api';

export interface Lookups {
  systems: Array<{ id: string; code: string; name: string; owner_user_id: string | null; is_active: boolean }>;
  departments: Array<{ id: string; code: string; name: string }>;
  positions: Array<{ id: string; code: string; name: string }>;
  roles: Array<{ id: string; system_id: string; code: string; name: string }>;
  modules: Array<{ id: string; system_id: string; code: string; name: string }>;
  operations: Array<{ id: string; system_id: string; module_id: string; code: string; name: string; risk_level: string }>;
}

let cache: Lookups | null = null;
let pending: Promise<Lookups> | null = null;
const listeners = new Set<(l: Lookups) => void>();

export function loadLookups(force = false): Promise<Lookups> {
  if (cache && !force) return Promise.resolve(cache);
  if (!pending || force) {
    pending = api.get<Lookups>('/reference/lookups').then((l) => {
      cache = l;
      pending = null;
      listeners.forEach((fn) => fn(l));
      return l;
    });
  }
  return pending;
}

export const invalidateLookups = () => { loadLookups(true).catch(() => undefined); };

export function useLookups(): Lookups | null {
  const [l, setL] = useState<Lookups | null>(cache);
  useEffect(() => {
    listeners.add(setL);
    loadLookups().then(setL).catch(() => undefined);
    return () => { listeners.delete(setL); };
  }, []);
  return l;
}
