import { Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import type { SignatureStatus } from '@/api/types';

export function StatusTag({ name, color }: { name?: string; color?: string }) {
  if (!name) return null;
  return <Tag color={color || 'default'} style={{ marginInlineEnd: 0 }}>{name}</Tag>;
}

const kindColors: Record<string, string> = {
  Ordered: 'purple', InStock: 'cyan', Assigned: 'blue', Reserved: 'gold', InRepair: 'orange', Lost: 'red', Stolen: 'volcano',
  Disposed: 'default', WrittenOff: 'default', Archived: 'default', Active: 'green', Leave: 'blue', Suspended: 'gold', Terminated: 'red',
  Requested: 'gold', Revoked: 'default', InProgress: 'processing', Completed: 'green', Cancelled: 'default', Pending: 'gold', Signed: 'green',
  Refused: 'red', NotRequired: 'default', Issue: 'blue', Return: 'orange', Transfer: 'purple', StatusChange: 'magenta', Repair: 'volcano',
};

/** Tag for an enum value with translated label (enums.<group>.<value>). */
export function EnumTag({ group, value }: { group: string; value?: string | null }) {
  const { t } = useTranslation();
  if (!value) return null;
  return <Tag color={kindColors[value] ?? 'default'} style={{ marginInlineEnd: 0 }}>{t(`enums.${group}.${value}`, { defaultValue: value })}</Tag>;
}

export function BackdatedTag({ show }: { show?: boolean }) {
  const { t } = useTranslation();
  if (!show) return null;
  return (
    <Tooltip title={t('common.backdatedHint')}>
      <Tag color="orange">{t('common.backdated')}</Tag>
    </Tooltip>
  );
}

export function SignatureTag({ status }: { status?: SignatureStatus }) {
  return <EnumTag group="signature" value={status} />;
}
