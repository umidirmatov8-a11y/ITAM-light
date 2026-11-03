import { Router } from 'express';
import { one, q } from '../../common/db';
import { requirePerm, scopedSystemIds } from '../auth/auth';

export const dashboardRouter = Router();

dashboardRouter.get('/', requirePerm('dashboard.view'), async (req, res) => {
  const scope = await scopedSystemIds(req);
  const last = await one(`SELECT a.id, a.name, a.as_of_date, a.completed_at, a.summary, mv.version AS matrix_version
                            FROM audit_runs a LEFT JOIN matrix_versions mv ON mv.id = a.matrix_version_id
                           WHERE a.status = 'COMPLETED' ORDER BY a.as_of_date DESC, a.completed_at DESC LIMIT 1`);
  const trend = await q(`
    SELECT a.id, a.name, a.as_of_date,
           count(f.id) FILTER (WHERE f.severity = 'CRITICAL' AND f.outcome IN ('VIOLATION','EXCEPTION_EXPIRED'))::int AS critical,
           count(f.id) FILTER (WHERE f.severity = 'HIGH' AND f.outcome IN ('VIOLATION','EXCEPTION_EXPIRED'))::int AS high,
           count(f.id) FILTER (WHERE f.severity = 'MEDIUM' AND f.outcome IN ('VIOLATION','EXCEPTION_EXPIRED'))::int AS medium,
           count(f.id) FILTER (WHERE f.outcome = 'NEEDS_REVIEW')::int AS review
      FROM audit_runs a LEFT JOIN audit_findings f ON f.audit_id = a.id AND ($1::uuid[] IS NULL OR f.system_id = ANY($1))
     WHERE a.status = 'COMPLETED'
     GROUP BY a.id ORDER BY a.as_of_date DESC, a.completed_at DESC LIMIT 10`, [scope]);
  const lastScoped = last ? await one(`
    SELECT count(*) FILTER (WHERE severity = 'CRITICAL' AND outcome IN ('VIOLATION','EXCEPTION_EXPIRED'))::int AS critical,
           count(*) FILTER (WHERE severity = 'HIGH' AND outcome IN ('VIOLATION','EXCEPTION_EXPIRED'))::int AS high,
           count(*) FILTER (WHERE outcome = 'NEEDS_REVIEW')::int AS review,
           count(*) FILTER (WHERE finding_type LIKE 'SOD%')::int AS sod,
           count(*) FILTER (WHERE finding_type = 'TERMINATED_USER_ACCESS')::int AS terminated,
           count(*) FILTER (WHERE status = 'OPEN')::int AS open
      FROM audit_findings WHERE audit_id = $1 AND ($2::uuid[] IS NULL OR system_id = ANY($2))`, [last.id, scope]) : null;
  const exceptions = await one(`
    SELECT count(*) FILTER (WHERE status = 'APPROVED' AND valid_from <= CURRENT_DATE AND valid_to >= CURRENT_DATE)::int AS active,
           count(*) FILTER (WHERE status = 'APPROVED' AND valid_to >= CURRENT_DATE AND valid_to < CURRENT_DATE + 30)::int AS expiring,
           count(*) FILTER (WHERE status = 'APPROVED' AND valid_to < CURRENT_DATE)::int AS expired,
           count(*) FILTER (WHERE status = 'REVOKED')::int AS revoked
      FROM exceptions WHERE ($1::uuid[] IS NULL OR system_id = ANY($1))`, [scope]);
  const counts = await one(`SELECT (SELECT count(*) FROM systems WHERE is_active)::int AS systems, (SELECT count(*) FROM employees)::int AS employees,
                                   (SELECT count(*) FROM audit_runs)::int AS audits, (SELECT count(*) FROM sod_rules WHERE status = 'ACTIVE')::int AS sod_rules,
                                   (SELECT version FROM matrix_versions WHERE status = 'APPROVED' AND valid_from <= CURRENT_DATE AND (valid_to IS NULL OR valid_to >= CURRENT_DATE) ORDER BY valid_from DESC LIMIT 1) AS current_matrix`);
  res.json({ last, lastScoped, trend: trend.reverse(), exceptions, counts, scoped: Boolean(scope) });
});
