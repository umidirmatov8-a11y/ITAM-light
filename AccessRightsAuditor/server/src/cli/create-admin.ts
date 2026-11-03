import crypto from 'node:crypto';
import { migrate } from '../common/migrate';
import { pool } from '../common/db';
import { createUser } from './bootstrap';
import { validatePasswordStrength } from '../modules/auth/auth';

// Использование: npm run create-admin -- <логин> [пароль]
// Создаёт (или восстанавливает) учётную запись системного администратора.
async function main() {
  const [username = 'admin', pwd] = process.argv.slice(2);
  const password = pwd || `${crypto.randomBytes(9).toString('base64url')}7a`;
  const weak = validatePasswordStrength(password);
  if (weak) throw new Error(weak);
  await migrate(() => undefined);
  await createUser(username, 'Системный администратор', password, ['SYS_ADMIN', 'MATRIX_ADMIN', 'AUDITOR'], true);
  console.log(`Администратор «${username}» создан/восстановлен. Временный пароль: ${password}`);
}

main().catch((e) => { console.error(e.message); process.exitCode = 1; }).finally(() => pool.end());
