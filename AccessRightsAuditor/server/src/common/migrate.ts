import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pool } from './db';
import { config } from '../config';

export async function migrate(log: (m: string) => void = console.log): Promise<void> {
  const c = await pool.connect();
  try {
    await c.query(`CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())`);
    const applied = new Map((await c.query('SELECT name, checksum FROM schema_migrations')).rows.map((r) => [r.name, r.checksum]));
    const files = fs.readdirSync(config.migrationsDir).filter((f) => f.endsWith('.sql')).sort();
    for (const f of files) {
      const sql = fs.readFileSync(path.join(config.migrationsDir, f), 'utf8');
      const sum = crypto.createHash('sha256').update(sql).digest('hex');
      if (applied.has(f)) {
        if (applied.get(f) !== sum) log(`ВНИМАНИЕ: миграция ${f} изменена после применения`);
        continue;
      }
      log(`Применение миграции ${f}`);
      await c.query('BEGIN');
      try {
        await c.query(sql);
        await c.query('INSERT INTO schema_migrations (name, checksum) VALUES ($1, $2)', [f, sum]);
        await c.query('COMMIT');
      } catch (e) {
        await c.query('ROLLBACK');
        throw e;
      }
    }
  } finally {
    c.release();
  }
}
