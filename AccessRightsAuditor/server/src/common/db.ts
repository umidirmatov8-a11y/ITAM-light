import { Pool, PoolClient, QueryResultRow, types } from 'pg';
import { config } from '../config';

// date (OID 1082) возвращаем строкой YYYY-MM-DD, без сдвига часового пояса.
types.setTypeParser(1082, (v) => v);
// bigint (OID 20) — числом (счётчики).
types.setTypeParser(20, (v) => Number(v));

const useUrl = Boolean(config.db.connectionString);
export const pool = new Pool({
  connectionString: config.db.connectionString,
  host: useUrl ? undefined : config.db.host,
  port: useUrl ? undefined : config.db.port,
  database: useUrl ? undefined : config.db.database,
  user: useUrl ? undefined : config.db.user,
  password: useUrl ? undefined : config.db.password,
  ssl: config.db.ssl,
  max: 10,
});

export type Db = Pool | PoolClient;

export async function q<T extends QueryResultRow = any>(sql: string, params: unknown[] = [], db: Db = pool): Promise<T[]> {
  const r = await db.query<T>(sql, params as any[]);
  return r.rows;
}

export async function one<T extends QueryResultRow = any>(sql: string, params: unknown[] = [], db: Db = pool): Promise<T | null> {
  const rows = await q<T>(sql, params, db);
  return rows[0] ?? null;
}

export async function tx<T>(fn: (c: PoolClient) => Promise<T>): Promise<T> {
  const c = await pool.connect();
  try {
    await c.query('BEGIN');
    const r = await fn(c);
    await c.query('COMMIT');
    return r;
  } catch (e) {
    await c.query('ROLLBACK').catch(() => undefined);
    throw e;
  } finally {
    c.release();
  }
}

/** Пакетная вставка: строки разбиваются на порции, чтобы не превышать лимит параметров PostgreSQL. */
export async function bulkInsert(db: Db, table: string, columns: string[], rows: unknown[][], returning?: string): Promise<any[]> {
  const out: any[] = [];
  const chunk = Math.max(1, Math.floor(60000 / columns.length));
  for (let i = 0; i < rows.length; i += chunk) {
    const part = rows.slice(i, i + chunk);
    const params: unknown[] = [];
    const values = part.map((r) => `(${r.map((v) => { params.push(v); return `$${params.length}`; }).join(',')})`).join(',');
    const res = await db.query(`INSERT INTO ${table} (${columns.join(',')}) VALUES ${values}${returning ? ` RETURNING ${returning}` : ''}`, params as any[]);
    out.push(...res.rows);
  }
  return out;
}
