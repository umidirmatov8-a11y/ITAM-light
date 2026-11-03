import fs from 'node:fs';
import { createApp } from './app';
import { config } from './config';
import { migrate } from './common/migrate';
import { pool } from './common/db';
import { ensureInitialAdmin } from './cli/bootstrap';

async function main() {
  fs.mkdirSync(config.dataDir, { recursive: true, mode: 0o700 });
  await migrate();
  await ensureInitialAdmin();
  // Удаление истёкших сессий.
  setInterval(() => { pool.query(`DELETE FROM sessions WHERE expires_at < now() - interval '1 day'`).catch(() => undefined); }, 3600_000).unref();
  const app = createApp();
  app.listen(config.port, config.host, () => {
    console.log(`Access Rights Auditor запущен: http://${config.host === '0.0.0.0' ? 'localhost' : config.host}:${config.port}`);
    if (config.host !== '127.0.0.1' && config.host !== 'localhost') console.warn('ВНИМАНИЕ: сервер доступен по сети. Ограничьте доступ доверенным сегментом и используйте TLS-прокси.');
  });
}

main().catch((e) => {
  console.error('Ошибка запуска:', e?.message ?? e);
  if (e?.code === 'ECONNREFUSED' || e?.code === '28P01' || e?.code === '3D000') {
    console.error('Проверьте, что PostgreSQL запущен и параметры подключения в файле .env верны (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD).');
  }
  process.exit(1);
});
