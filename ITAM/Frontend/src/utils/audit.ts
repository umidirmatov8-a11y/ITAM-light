import type { TFunction } from 'i18next';

const VERBS = ['create', 'update', 'delete', 'archive', 'restore'];
const keyOf = (s: string) => s.replace(/[.-]/g, '_');

/**
 * Human-readable label for an audit action code. Explicit codes ("auth.login.failed") have their own
 * translation; automatic entity audit ("asset-assignment.update") is composed from entity + verb.
 */
export function auditActionLabel(t: TFunction, action: string): string {
  const explicit = t(`audit.actions.${keyOf(action)}`, { defaultValue: '' });
  if (explicit) return explicit;
  const dot = action.lastIndexOf('.');
  const entity = action.slice(0, dot);
  const verb = action.slice(dot + 1);
  if (dot > 0 && VERBS.includes(verb)) {
    return `${t(`audit.entities.${keyOf(entity)}`, { defaultValue: entity })}: ${t(`audit.verbs.${verb}`)}`;
  }
  return action;
}
