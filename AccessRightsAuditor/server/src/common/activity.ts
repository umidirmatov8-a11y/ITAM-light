import { Request } from 'express';
import { Db, pool } from './db';

export type ActivityCategory = 'GENERAL' | 'ADMIN' | 'AUTH' | 'DATA' | 'AUDIT';

export async function logActivity(
  req: Request | null,
  action: string,
  opts: { category?: ActivityCategory; entityType?: string; entityId?: string | null; before?: unknown; after?: unknown; actorId?: string | null; actorName?: string | null } = {},
  db: Db = pool,
): Promise<void> {
  const user = req?.user;
  await db.query(
    `INSERT INTO activity_logs (actor_user_id, actor_name, action, category, entity_type, entity_id, before_json, after_json, ip)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
    [
      opts.actorId ?? user?.id ?? null,
      opts.actorName ?? user?.username ?? null,
      action,
      opts.category ?? 'GENERAL',
      opts.entityType ?? null,
      opts.entityId ?? null,
      opts.before === undefined ? null : JSON.stringify(redact(opts.before)),
      opts.after === undefined ? null : JSON.stringify(redact(opts.after)),
      req?.ip ?? null,
    ],
  );
}

function redact(v: unknown): unknown {
  if (!v || typeof v !== 'object') return v;
  if (Array.isArray(v)) return v.map(redact);
  const out: Record<string, unknown> = {};
  for (const [k, val] of Object.entries(v)) out[k] = /password|token/i.test(k) ? '***' : redact(val);
  return out;
}
