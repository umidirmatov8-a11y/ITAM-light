import crypto from 'node:crypto';
import bcrypt from 'bcryptjs';
import { NextFunction, Request, Response, Router } from 'express';
import { z } from 'zod';
import { one, q } from '../../common/db';
import { forbidden, HttpError, parse } from '../../common/http';
import { logActivity } from '../../common/activity';
import { setting } from '../../common/settings';
import { sha256 } from '../../common/hash';
import { config } from '../../config';

export interface AuthUser {
  id: string;
  username: string;
  fullName: string;
  roles: string[];
  permissions: Set<string>;
  mustChangePassword: boolean;
  sessionId: string;
}

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      user?: AuthUser;
    }
  }
}

export const COOKIE = 'ara_sid';
const BCRYPT_ROUNDS = 12;

export const hashPassword = (p: string) => bcrypt.hash(p, BCRYPT_ROUNDS);

export function validatePasswordStrength(p: string): string | null {
  if (p.length < 10) return 'Пароль должен содержать не менее 10 символов';
  if (!/[A-Za-zА-Яа-я]/.test(p) || !/\d/.test(p)) return 'Пароль должен содержать буквы и цифры';
  return null;
}

async function loadUser(userId: string, sessionId: string): Promise<AuthUser | null> {
  const u = await one(`SELECT id, username, full_name, is_active, must_change_password FROM users WHERE id = $1`, [userId]);
  if (!u || !u.is_active) return null;
  const roles = await q<{ code: string; permission_code: string | null }>(
    `SELECT r.code, p.permission_code FROM user_role_assignments ura
       JOIN app_roles r ON r.id = ura.role_id
       LEFT JOIN app_role_permissions p ON p.role_id = r.id
      WHERE ura.user_id = $1`, [userId]);
  return {
    id: u.id,
    username: u.username,
    fullName: u.full_name,
    roles: [...new Set(roles.map((r) => r.code))],
    permissions: new Set(roles.map((r) => r.permission_code).filter(Boolean) as string[]),
    mustChangePassword: u.must_change_password,
    sessionId,
  };
}

/** Проверяет cookie сессии, тайм-аут бездействия и продлевает сессию. */
export async function sessionMiddleware(req: Request, res: Response, next: NextFunction) {
  const token = req.cookies?.[COOKIE];
  if (!token) return next();
  const idle = Number(await setting('session_idle_minutes', 30));
  const s = await one(
    `UPDATE sessions SET last_seen_at = now()
      WHERE token_hash = $1 AND revoked_at IS NULL AND expires_at > now()
        AND last_seen_at > now() - make_interval(mins => $2::int)
      RETURNING id, user_id`, [sha256(token), idle]);
  if (s) {
    const user = await loadUser(s.user_id, s.id);
    if (user) req.user = user;
  } else {
    res.clearCookie(COOKIE);
  }
  next();
}

export function requireAuth(req: Request, _res: Response, next: NextFunction) {
  if (!req.user) return next(new HttpError(401, 'Требуется вход в систему'));
  // До смены временного пароля доступны только операции с паролем и сессией.
  if (req.user.mustChangePassword && !req.path.startsWith('/auth/')) {
    return next(new HttpError(403, 'Необходимо сменить временный пароль'));
  }
  next();
}

export const can = (req: Request, perm: string) => Boolean(req.user?.permissions.has(perm));

export function requirePerm(...perms: string[]) {
  return (req: Request, _res: Response, next: NextFunction) => {
    if (!req.user) return next(new HttpError(401, 'Требуется вход в систему'));
    if (!perms.some((p) => req.user!.permissions.has(p))) return next(forbidden());
    next();
  };
}

/** Для владельца системы — список систем, по которым разрешён просмотр. null = без ограничений. */
export async function scopedSystemIds(req: Request): Promise<string[] | null> {
  const u = req.user!;
  const unrestricted = ['findings.edit', 'reports.export', 'matrix.edit', 'users.manage'].some((p) => u.permissions.has(p));
  if (unrestricted || !u.permissions.has('findings.scoped')) return null;
  const rows = await q<{ id: string }>('SELECT id FROM systems WHERE owner_user_id = $1', [u.id]);
  return rows.map((r) => r.id);
}

export function userDto(u: AuthUser) {
  return { id: u.id, username: u.username, fullName: u.fullName, roles: u.roles, permissions: [...u.permissions].sort(), mustChangePassword: u.mustChangePassword };
}

export const authRouter = Router();

authRouter.post('/login', async (req, res) => {
  const { username, password } = parse(z.object({ username: z.string().trim().min(1), password: z.string().min(1) }), req.body);
  const u = await one(`SELECT * FROM users WHERE lower(username) = lower($1)`, [username]);
  const maxFailed = Number(await setting('max_failed_logins', 5));
  const lockMinutes = Number(await setting('lockout_minutes', 15));
  const fail = async (reason: string) => {
    await logActivity(req, 'LOGIN_FAILED', { category: 'AUTH', entityType: 'user', entityId: u?.id ?? null, actorId: u?.id ?? null, actorName: username, after: { reason } });
    throw new HttpError(401, 'Неверное имя пользователя или пароль');
  };
  if (!u) return fail('unknown_user');
  if (!u.is_active) return fail('inactive');
  if (u.locked_until && new Date(u.locked_until) > new Date()) {
    await logActivity(req, 'LOGIN_LOCKED', { category: 'AUTH', entityType: 'user', entityId: u.id, actorId: u.id, actorName: u.username });
    throw new HttpError(423, `Учётная запись временно заблокирована до ${new Date(u.locked_until).toLocaleString('ru-RU')}`);
  }
  const ok = await bcrypt.compare(password, u.password_hash);
  if (!ok) {
    const attempts = u.failed_attempts + 1;
    if (attempts >= maxFailed) {
      await q(`UPDATE users SET failed_attempts = 0, locked_until = now() + make_interval(mins => $2::int) WHERE id = $1`, [u.id, lockMinutes]);
      await logActivity(req, 'USER_LOCKED', { category: 'AUTH', entityType: 'user', entityId: u.id, actorId: u.id, actorName: u.username });
    } else {
      await q(`UPDATE users SET failed_attempts = $2 WHERE id = $1`, [u.id, attempts]);
    }
    return fail('bad_password');
  }
  await q(`UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = now() WHERE id = $1`, [u.id]);
  const token = crypto.randomBytes(32).toString('base64url');
  const maxHours = Number(await setting('session_max_hours', 10));
  const s = await one(
    `INSERT INTO sessions (token_hash, user_id, expires_at, ip, user_agent) VALUES ($1,$2, now() + make_interval(hours => $3::int), $4, $5) RETURNING id`,
    [sha256(token), u.id, maxHours, req.ip ?? null, String(req.headers['user-agent'] ?? '').slice(0, 300)]);
  res.cookie(COOKIE, token, { httpOnly: true, sameSite: 'strict', secure: config.secureCookies, path: '/' });
  const user = await loadUser(u.id, s!.id);
  await logActivity(req, 'LOGIN', { category: 'AUTH', entityType: 'user', entityId: u.id, actorId: u.id, actorName: u.username });
  res.json({ user: userDto(user!) });
});

authRouter.post('/logout', async (req, res) => {
  if (req.user) {
    await q('UPDATE sessions SET revoked_at = now() WHERE id = $1', [req.user.sessionId]);
    await logActivity(req, 'LOGOUT', { category: 'AUTH', entityType: 'user', entityId: req.user.id });
  }
  res.clearCookie(COOKIE);
  res.json({ ok: true });
});

authRouter.get('/me', async (req, res) => {
  if (!req.user) { res.json({ user: null }); return; }
  res.json({ user: userDto(req.user), idleMinutes: Number(await setting('session_idle_minutes', 30)) });
});

authRouter.post('/change-password', async (req, res) => {
  if (!req.user) throw new HttpError(401, 'Требуется вход в систему');
  const { currentPassword, newPassword } = parse(z.object({ currentPassword: z.string(), newPassword: z.string() }), req.body);
  const u = await one('SELECT password_hash FROM users WHERE id = $1', [req.user.id]);
  if (!u || !(await bcrypt.compare(currentPassword, u.password_hash))) throw new HttpError(400, 'Текущий пароль указан неверно');
  const weak = validatePasswordStrength(newPassword);
  if (weak) throw new HttpError(400, weak);
  if (newPassword === currentPassword) throw new HttpError(400, 'Новый пароль должен отличаться от текущего');
  await q('UPDATE users SET password_hash = $2, must_change_password = false WHERE id = $1', [req.user.id, await hashPassword(newPassword)]);
  await q('UPDATE sessions SET revoked_at = now() WHERE user_id = $1 AND id <> $2 AND revoked_at IS NULL', [req.user.id, req.user.sessionId]);
  await logActivity(req, 'PASSWORD_CHANGED', { category: 'AUTH', entityType: 'user', entityId: req.user.id });
  res.json({ ok: true });
});
