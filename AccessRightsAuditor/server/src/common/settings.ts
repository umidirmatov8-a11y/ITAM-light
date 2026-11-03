import { q } from './db';

let cache: { at: number; values: Record<string, any> } | null = null;

export async function getSettings(): Promise<Record<string, any>> {
  if (cache && Date.now() - cache.at < 5000) return cache.values;
  const rows = await q<{ key: string; value: any }>('SELECT key, value FROM app_settings');
  const values = Object.fromEntries(rows.map((r) => [r.key, r.value]));
  cache = { at: Date.now(), values };
  return values;
}

export function invalidateSettings() {
  cache = null;
}

export async function setting<T = any>(key: string, fallback: T): Promise<T> {
  const s = await getSettings();
  return (s[key] ?? fallback) as T;
}
