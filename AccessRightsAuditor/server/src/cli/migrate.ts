import { migrate } from '../common/migrate';
import { pool } from '../common/db';

migrate()
  .then(() => console.log('Миграции применены'))
  .catch((e) => { console.error(e.message); process.exitCode = 1; })
  .finally(() => pool.end());
