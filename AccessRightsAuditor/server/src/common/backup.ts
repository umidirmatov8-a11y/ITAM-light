import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { config } from '../config';

export function dirSize(p: string): number {
  const st = fs.statSync(p);
  if (!st.isDirectory()) return st.size;
  return fs.readdirSync(p).reduce((s, f) => s + dirSize(path.join(p, f)), 0);
}

/** Резервная копия: дамп PostgreSQL (pg_dump, формат custom) + файловое хранилище (импорты, отчёты). */
export async function createBackup(label = ''): Promise<{ name: string; dir: string; files: string[] }> {
  const name = new Date().toISOString().replace(/[:.]/g, '-') + (label ? `_${label}` : '');
  const dir = path.join(config.dataDir, 'backups', name);
  fs.mkdirSync(dir, { recursive: true });
  const env = { ...process.env };
  const args = ['--format=custom', '--no-owner', `--file=${path.join(dir, 'ara-db.dump')}`];
  if (config.db.connectionString) args.push(`--dbname=${config.db.connectionString}`);
  else {
    args.push(`--host=${config.db.host}`, `--port=${config.db.port}`, `--username=${config.db.user}`, config.db.database);
    if (config.db.password) env.PGPASSWORD = config.db.password;
  }
  try {
    await new Promise<void>((resolve, reject) =>
      execFile(config.pgDumpPath, args, { env, timeout: 30 * 60 * 1000 }, (err, _o, stderr) => (err ? reject(new Error(stderr || err.message)) : resolve())));
  } catch (e) {
    fs.rmSync(dir, { recursive: true, force: true });
    throw e;
  }
  for (const sub of ['imports', 'reports']) {
    const src = path.join(config.dataDir, sub);
    if (fs.existsSync(src)) fs.cpSync(src, path.join(dir, sub), { recursive: true });
  }
  return { name, dir, files: fs.readdirSync(dir) };
}
