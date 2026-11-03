import { pool } from '../common/db';
import { createBackup } from '../common/backup';

// Использование: node server/dist/cli/backup.js [метка]  — используется установщиком перед обновлением.
createBackup(process.argv[2] ?? '')
  .then((r) => console.log(`Резервная копия создана: ${r.dir}`))
  .catch((e) => { console.error(`Ошибка резервного копирования: ${e.message}`); process.exitCode = 1; })
  .finally(() => pool.end());
