import { Request, Router } from 'express';
import { z, ZodObject } from 'zod';
import { Db, one, q, tx } from './db';
import { notFound, parse, zId } from './http';
import { logActivity } from './activity';
import { requirePerm } from '../modules/auth/auth';

export interface CrudDef {
  path: string;
  table: string;
  entity: string;
  schema: ZodObject<any>;
  /** SELECT … FROM <table> t … — без WHERE/ORDER. */
  selectSql: string;
  orderBy: string;
  viewPerm: string;
  editPerm: string;
  searchCols?: string[];
  /** query-параметр → SQL-выражение для фильтра на равенство */
  filters?: Record<string, string>;
  beforeSave?: (data: Record<string, unknown>, db: Db) => Promise<Record<string, unknown>>;
  afterSave?: (id: string, data: Record<string, unknown>, db: Db, req: Request) => Promise<void>;
  /** Поля тела запроса, которые не сохраняются в таблицу напрямую (обрабатываются в afterSave). */
  virtualFields?: string[];
  limit?: number;
}

export function mountCrud(router: Router, def: CrudDef) {
  const base = `/${def.path}`;

  router.get(base, requirePerm(def.viewPerm), async (req, res) => {
    const params: unknown[] = [];
    const where: string[] = [];
    const { search } = req.query as Record<string, string>;
    if (search && def.searchCols?.length) {
      params.push(`%${search}%`);
      where.push(`(${def.searchCols.map((c) => `${c} ILIKE $${params.length}`).join(' OR ')})`);
    }
    for (const [param, expr] of Object.entries(def.filters ?? {})) {
      const v = req.query[param];
      if (typeof v === 'string' && v !== '') {
        params.push(v);
        where.push(`${expr} = $${params.length}`);
      }
    }
    const limit = Math.min(Number(req.query.limit) || def.limit || 5000, 20000);
    const rows = await q(`${def.selectSql} ${where.length ? 'WHERE ' + where.join(' AND ') : ''} ORDER BY ${def.orderBy} LIMIT ${limit}`, params);
    res.json(rows);
  });

  router.get(`${base}/:id`, requirePerm(def.viewPerm), async (req, res) => {
    const row = await one(`${def.selectSql} WHERE t.id = $1`, [parse(zId, req.params.id)]);
    if (!row) throw notFound();
    res.json(row);
  });

  const columnsOf = (data: Record<string, unknown>) => Object.keys(data).filter((k) => !def.virtualFields?.includes(k));

  router.post(base, requirePerm(def.editPerm), async (req, res) => {
    let data = parse(def.schema, req.body) as Record<string, unknown>;
    const row = await tx(async (c) => {
      if (def.beforeSave) data = await def.beforeSave(data, c);
      const cols = columnsOf(data);
      const r = (await c.query(`INSERT INTO ${def.table} (${cols.join(',')}) VALUES (${cols.map((_, i) => `$${i + 1}`).join(',')}) RETURNING id`, cols.map((k) => data[k]))).rows[0];
      if (def.afterSave) await def.afterSave(r.id, data, c, req);
      await logActivity(req, `${def.entity.toUpperCase()}_CREATED`, { category: 'DATA', entityType: def.entity, entityId: r.id, after: data }, c);
      return r;
    });
    res.status(201).json(await one(`${def.selectSql} WHERE t.id = $1`, [row.id]));
  });

  router.put(`${base}/:id`, requirePerm(def.editPerm), async (req, res) => {
    const id = parse(zId, req.params.id);
    let data = parse(def.schema, req.body) as Record<string, unknown>;
    await tx(async (c) => {
      const before = (await c.query(`SELECT * FROM ${def.table} WHERE id = $1`, [id])).rows[0];
      if (!before) throw notFound();
      if (def.beforeSave) data = await def.beforeSave(data, c);
      const cols = columnsOf(data);
      if (cols.length) await c.query(`UPDATE ${def.table} SET ${cols.map((k, i) => `${k} = $${i + 2}`).join(', ')} WHERE id = $1`, [id, ...cols.map((k) => data[k])]);
      if (def.afterSave) await def.afterSave(id, data, c, req);
      await logActivity(req, `${def.entity.toUpperCase()}_UPDATED`, { category: 'DATA', entityType: def.entity, entityId: id, before, after: data }, c);
    });
    res.json(await one(`${def.selectSql} WHERE t.id = $1`, [id]));
  });

  router.delete(`${base}/:id`, requirePerm(def.editPerm), async (req, res) => {
    const id = parse(zId, req.params.id);
    await tx(async (c) => {
      const before = (await c.query(`SELECT * FROM ${def.table} WHERE id = $1`, [id])).rows[0];
      if (!before) throw notFound();
      await c.query(`DELETE FROM ${def.table} WHERE id = $1`, [id]);
      await logActivity(req, `${def.entity.toUpperCase()}_DELETED`, { category: 'DATA', entityType: def.entity, entityId: id, before }, c);
    });
    res.json({ ok: true });
  });
}

export { z };
