import path from 'node:path';
import dotenv from 'dotenv';

/** Корень проекта AccessRightsAuditor (одинаково для src/ и dist/). */
export const ROOT_DIR = path.resolve(__dirname, '..', '..');
// В установленной версии (Windows) конфигурация лежит в %ProgramData%\ARA\config\ara.env — путь передаёт служба.
export const ENV_FILE = process.env.ARA_ENV_FILE || path.join(ROOT_DIR, '.env');
dotenv.config({ path: ENV_FILE, quiet: true } as any);

const env = process.env;

export const config = {
  host: env.ARA_HOST ?? '127.0.0.1',
  port: Number(env.ARA_PORT ?? 3000),
  dataDir: path.resolve(ROOT_DIR, env.ARA_DATA_DIR ?? 'data'),
  migrationsDir: path.join(ROOT_DIR, 'database', 'migrations'),
  webDist: path.join(ROOT_DIR, 'web', 'dist'),
  db: {
    connectionString: env.DATABASE_URL,
    host: env.PGHOST ?? 'localhost',
    port: Number(env.PGPORT ?? 5432),
    database: env.PGDATABASE ?? 'ara',
    user: env.PGUSER ?? 'ara',
    password: env.PGPASSWORD,
    ssl: env.PGSSLMODE === 'require' || env.PGSSLMODE === 'verify-full'
      ? { rejectUnauthorized: env.PGSSLMODE === 'verify-full' }
      : undefined,
  },
  pgDumpPath: env.ARA_PG_DUMP ?? 'pg_dump',
  secureCookies: env.ARA_SECURE_COOKIES === 'true',
};
