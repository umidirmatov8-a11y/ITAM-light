import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { Router } from 'express';
import { z } from 'zod';
import { one, q, tx } from '../../common/db';
import { badRequest, notFound, parse, zId } from '../../common/http';
import { logActivity } from '../../common/activity';
import { getSettings, invalidateSettings } from '../../common/settings';
import { hashPassword, requirePerm, validatePasswordStrength } from '../auth/auth';
import { config } from '../../config';
import { createBackup, dirSize } from '../../common/backup';

export const adminRouter = Router();

// ---------- Пользователи ----------
adminRouter.get('/users', requirePerm('users.manage'), async (_req, res) => {
  res.json(await q(`
    SELECT u.id, u.username, u.full_name, u.is_active, u.must_change_password, u.locked_until, u.last_login_at, u.created_at,
           COALESCE(array_agg(r.code ORDER BY r.code) FILTER (WHERE r.code IS NOT NULL), '{}') AS roles
      FROM users u LEFT JOIN user_role_assignments ura ON ura.user_id = u.id LEFT JOIN app_roles r ON r.id = ura.role_id
     GROUP BY u.id ORDER BY u.username`));
});

adminRouter.get('/roles', requirePerm('users.manage'), async (_req, res) => {
  res.json(await q(`SELECT r.id, r.code, r.name, array_agg(p.permission_code ORDER BY p.permission_code) AS permissions
                      FROM app_roles r LEFT JOIN app_role_permissions p ON p.role_id = r.id GROUP BY r.id ORDER BY r.code`));
});

// Список пользователей для выбора владельца системы (минимальные данные).
adminRouter.get('/user-options', requirePerm('reference.view'), async (_req, res) => {
  res.json(await q(`SELECT id, username, full_name FROM users WHERE is_active ORDER BY full_name`));
});

const userSchema = z.object({
  username: z.string().trim().min(3).max(64).regex(/^[A-Za-z0-9._-]+$/, 'латиница, цифры, . _ -'),
  fullName: z.string().trim().min(1),
  isActive: z.boolean().default(true),
  roles: z.array(z.enum(['SYS_ADMIN', 'MATRIX_ADMIN', 'AUDITOR', 'SYSTEM_OWNER', 'VIEWER'])).min(1, 'назначьте хотя бы одну роль'),
  password: z.string().optional(),
});

async function setRoles(c: any, userId: string, roles: string[]) {
  await c.query('DELETE FROM user_role_assignments WHERE user_id = $1', [userId]);
  await c.query(`INSERT INTO user_role_assignments (user_id, role_id) SELECT $1, id FROM app_roles WHERE code = ANY($2)`, [userId, roles]);
}

adminRouter.post('/users', requirePerm('users.manage'), async (req, res) => {
  const b = parse(userSchema, req.body);
  const password = b.password || crypto.randomBytes(9).toString('base64url') + '7a';
  const weak = validatePasswordStrength(password);
  if (weak) throw badRequest(weak);
  const hash = await hashPassword(password);
  const user = await tx(async (c) => {
    const u = (await c.query(`INSERT INTO users (username, password_hash, full_name, is_active, must_change_password) VALUES ($1,$2,$3,$4,true) RETURNING id, username`,
      [b.username, hash, b.fullName, b.isActive])).rows[0];
    await setRoles(c, u.id, b.roles);
    await logActivity(req, 'USER_CREATED', { category: 'ADMIN', entityType: 'user', entityId: u.id, after: { username: b.username, fullName: b.fullName, roles: b.roles } }, c);
    return u;
  });
  res.status(201).json({ ...user, temporaryPassword: b.password ? undefined : password });
});

adminRouter.put('/users/:id', requirePerm('users.manage'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const b = parse(userSchema.omit({ password: true, username: true }), req.body);
  if (id === req.user!.id && (!b.isActive || !b.roles.includes('SYS_ADMIN')) && req.user!.roles.includes('SYS_ADMIN')) {
    throw badRequest('Нельзя отключить себя или снять с себя роль системного администратора');
  }
  await tx(async (c) => {
    const before = (await c.query(`SELECT u.full_name, u.is_active, array_agg(r.code) AS roles FROM users u LEFT JOIN user_role_assignments a ON a.user_id=u.id LEFT JOIN app_roles r ON r.id=a.role_id WHERE u.id=$1 GROUP BY u.id`, [id])).rows[0];
    if (!before) throw notFound();
    await c.query('UPDATE users SET full_name=$2, is_active=$3 WHERE id=$1', [id, b.fullName, b.isActive]);
    await setRoles(c, id, b.roles);
    if (!b.isActive) await c.query('UPDATE sessions SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL', [id]);
    await logActivity(req, 'USER_UPDATED', { category: 'ADMIN', entityType: 'user', entityId: id, before, after: b }, c);
  });
  res.json({ ok: true });
});

adminRouter.post('/users/:id/reset-password', requirePerm('users.manage'), async (req, res) => {
  const id = parse(zId, req.params.id);
  const password = crypto.randomBytes(9).toString('base64url') + '7a';
  const r = await q('UPDATE users SET password_hash=$2, must_change_password=true, failed_attempts=0, locked_until=NULL WHERE id=$1 RETURNING id', [id, await hashPassword(password)]);
  if (!r.length) throw notFound();
  await q('UPDATE sessions SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL', [id]);
  await logActivity(req, 'USER_PASSWORD_RESET', { category: 'ADMIN', entityType: 'user', entityId: id });
  res.json({ temporaryPassword: password });
});

adminRouter.post('/users/:id/unlock', requirePerm('users.manage'), async (req, res) => {
  const id = parse(zId, req.params.id);
  await q('UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=$1', [id]);
  await logActivity(req, 'USER_UNLOCKED', { category: 'ADMIN', entityType: 'user', entityId: id });
  res.json({ ok: true });
});

// ---------- Настройки ----------
const settingsSchema = z.object({
  session_idle_minutes: z.coerce.number().int().min(5).max(240),
  session_max_hours: z.coerce.number().int().min(1).max(24),
  max_failed_logins: z.coerce.number().int().min(3).max(20),
  lockout_minutes: z.coerce.number().int().min(1).max(1440),
  max_upload_mb: z.coerce.number().int().min(1).max(200),
  retention_days: z.coerce.number().int().min(30).max(36500),
}).partial();

adminRouter.get('/settings', requirePerm('settings.manage', 'matrix.edit'), async (_req, res) => {
  res.json(await getSettings());
});

adminRouter.put('/settings', requirePerm('settings.manage'), async (req, res) => {
  const b = parse(settingsSchema, req.body);
  const before = await getSettings();
  for (const [k, v] of Object.entries(b)) {
    await q(`INSERT INTO app_settings (key, value, updated_by, updated_at) VALUES ($1, $2, $3, now())
             ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = now()`, [k, JSON.stringify(v), req.user!.id]);
  }
  invalidateSettings();
  await logActivity(req, 'SETTINGS_UPDATED', { category: 'ADMIN', entityType: 'settings', before: Object.fromEntries(Object.keys(b).map((k) => [k, before[k]])), after: b });
  res.json(await getSettings());
});

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'REVIEW'] as const;
// Политика критичности — часть «версии правил», её меняет администратор матрицы.
adminRouter.put('/severity-policy', requirePerm('matrix.edit'), async (req, res) => {
  const b = parse(z.record(z.string(), z.union([z.enum(SEVERITIES), z.boolean()])), req.body);
  const before = (await getSettings()).severity_policy;
  await q(`UPDATE app_settings SET value=$1, updated_by=$2, updated_at=now() WHERE key='severity_policy'`, [JSON.stringify(b), req.user!.id]);
  invalidateSettings();
  await logActivity(req, 'SEVERITY_POLICY_UPDATED', { category: 'ADMIN', entityType: 'settings', entityId: 'severity_policy', before, after: b });
  res.json(b);
});

// ---------- Журнал действий ----------
adminRouter.get('/activity', requirePerm('activity.view'), async (req, res) => {
  const { category, search, limit = '200', offset = '0' } = req.query as Record<string, string>;
  const params: unknown[] = [];
  const where: string[] = [];
  if (category) { params.push(category); where.push(`category = $${params.length}`); }
  if (search) { params.push(`%${search}%`); where.push(`(action ILIKE $${params.length} OR actor_name ILIKE $${params.length} OR entity_type ILIKE $${params.length})`); }
  params.push(Math.min(Number(limit) || 200, 1000), Number(offset) || 0);
  const rows = await q(`SELECT * FROM activity_logs ${where.length ? 'WHERE ' + where.join(' AND ') : ''} ORDER BY id DESC LIMIT $${params.length - 1} OFFSET $${params.length}`, params);
  res.json(rows);
});

// ---------- Резервное копирование ----------
adminRouter.get('/backups', requirePerm('backup.manage'), async (_req, res) => {
  const dir = path.join(config.dataDir, 'backups');
  if (!fs.existsSync(dir)) return res.json([]);
  res.json(fs.readdirSync(dir).filter((d) => fs.statSync(path.join(dir, d)).isDirectory()).sort().reverse().map((name) => {
    const files = fs.readdirSync(path.join(dir, name));
    return { name, files, size: dirSize(path.join(dir, name)) };
  }));
});

adminRouter.post('/backups', requirePerm('backup.manage'), async (req, res) => {
  try {
    const r = await createBackup();
    await logActivity(req, 'BACKUP_CREATED', { category: 'ADMIN', entityType: 'backup', entityId: r.name, after: { files: r.files } });
    res.json(r);
  } catch (e: any) {
    await logActivity(req, 'BACKUP_FAILED', { category: 'ADMIN', entityType: 'backup', after: { error: String(e.message).slice(0, 500) } });
    throw badRequest(`Не удалось выполнить pg_dump: ${String(e.message).slice(0, 300)}. Укажите путь к pg_dump в ARA_PG_DUMP или используйте scripts/backup.ps1`);
  }
});

// ---------- Справка о системе ----------
adminRouter.get('/system-info', requirePerm('settings.manage'), async (_req, res) => {
  const db = await one(`SELECT version() AS version, current_database() AS database, pg_size_pretty(pg_database_size(current_database())) AS size`);
  const ssl = await one(`SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()`).catch(() => null);
  res.json({ node: process.version, db, dbSsl: ssl?.ssl ?? null, dataDir: config.dataDir, host: config.host, port: config.port });
});
