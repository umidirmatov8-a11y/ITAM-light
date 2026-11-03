import crypto from 'node:crypto';
import { one, tx } from '../common/db';
import { hashPassword } from '../modules/auth/auth';

/**
 * Первый запуск: если пользователей нет, создаётся администратор.
 * Пароль берётся из ARA_ADMIN_PASSWORD или генерируется и выводится в консоль один раз; при первом входе его нужно сменить.
 */
export async function ensureInitialAdmin(): Promise<void> {
  const n = await one('SELECT count(*)::int AS n FROM users');
  if (n.n > 0) return;
  const username = process.env.ARA_ADMIN_USERNAME || 'admin';
  const password = process.env.ARA_ADMIN_PASSWORD || `${crypto.randomBytes(9).toString('base64url')}7a`;
  await createUser(username, 'Системный администратор', password, ['SYS_ADMIN', 'MATRIX_ADMIN', 'AUDITOR'], true);
  console.log('==============================================================');
  console.log(' Создан первый администратор ARA');
  console.log(`   Логин:  ${username}`);
  if (!process.env.ARA_ADMIN_PASSWORD) console.log(`   Пароль: ${password}   (временный — смените при первом входе)`);
  console.log('==============================================================');
}

export async function createUser(username: string, fullName: string, password: string, roles: string[], mustChange: boolean): Promise<string> {
  const hash = await hashPassword(password);
  return tx(async (c) => {
    const u = (await c.query(`INSERT INTO users (username, password_hash, full_name, must_change_password) VALUES ($1,$2,$3,$4)
                              ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, must_change_password = EXCLUDED.must_change_password, is_active = true
                              RETURNING id`, [username, hash, fullName, mustChange])).rows[0];
    await c.query('DELETE FROM user_role_assignments WHERE user_id = $1', [u.id]);
    await c.query('INSERT INTO user_role_assignments (user_id, role_id) SELECT $1, id FROM app_roles WHERE code = ANY($2)', [u.id, roles]);
    await c.query(`INSERT INTO activity_logs (actor_name, action, category, entity_type, entity_id, after_json) VALUES ('system', 'USER_CREATED_CLI', 'ADMIN', 'user', $1, $2)`,
      [u.id, JSON.stringify({ username, roles })]);
    return u.id;
  });
}
