import crypto from 'node:crypto';
import { migrate } from '../common/migrate';
import { pool } from '../common/db';
import { createUser } from './bootstrap';
import { validatePasswordStrength } from '../modules/auth/auth';

// Использование: npm run create-admin -- <логин> [пароль] [--no-change]
// Пароль можно передать через переменную ARA_SETUP_ADMIN_PASSWORD (так делает установщик — не виден в списке процессов).
// --no-change — пароль задан администратором при установке, смена при первом входе не требуется.
async function main() {
  const args = process.argv.slice(2).filter((a) => !a.startsWith('--'));
  const noChange = process.argv.includes('--no-change');
  const username = args[0] || 'admin';
  const given = args[1] || process.env.ARA_SETUP_ADMIN_PASSWORD;
  const password = given || `${crypto.randomBytes(9).toString('base64url')}7a`;
  const weak = validatePasswordStrength(password);
  if (weak) throw new Error(weak);
  await migrate(() => undefined);
  await createUser(username, 'Системный администратор', password, ['SYS_ADMIN', 'MATRIX_ADMIN', 'AUDITOR'], !(noChange && given));
  console.log(given ? `Администратор «${username}» создан/обновлён.` : `Администратор «${username}» создан/восстановлен. Временный пароль: ${password}`);
}

main().catch((e) => { console.error(e.message); process.exitCode = 1; }).finally(() => pool.end());
