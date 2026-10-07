import { Table, Tag, Typography, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { auditActionLabel } from '@/utils/audit';
import { fmtDateTime } from '@/utils/format';

export interface AuditRow { id: number; timestamp: string; userName?: string; ipAddress?: string; action: string; entityType?: string; entityName?: string; oldValues?: unknown; newValues?: unknown; comment?: string; success: boolean }

const show = (v: unknown) => (v == null ? '' : typeof v === 'object' ? Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k}: ${typeof x === 'object' ? JSON.stringify(x) : String(x)}`).join('; ') : String(v));

export function AuditTable({ rows, loading, pagination }: { rows?: AuditRow[]; loading?: boolean; pagination?: object | false }) {
  const { t } = useTranslation();
  return (
    <Table<AuditRow> rowKey="id" size="small" loading={loading} dataSource={rows} pagination={pagination ?? { pageSize: 20 }} scroll={{ x: 'max-content' }}
      columns={[
        { title: t('audit.time'), dataIndex: 'timestamp', render: (v) => <span className="itam-mono">{fmtDateTime(v)}</span> },
        { title: t('audit.user'), dataIndex: 'userName' },
        { title: 'IP', dataIndex: 'ipAddress' },
        { title: t('audit.action'), dataIndex: 'action', render: (v, r) => <Tooltip title={v}><Tag color={r.success ? 'blue' : 'red'}>{auditActionLabel(t, v)}</Tag></Tooltip> },
        { title: t('audit.object'), render: (_, r) => <>{r.entityType && <Tag>{r.entityType}</Tag>}{r.entityName}</> },
        { title: t('audit.old'), dataIndex: 'oldValues', render: (v) => <Typography.Text type="secondary" style={{ maxWidth: 320, display: 'inline-block' }} ellipsis={{ tooltip: show(v) }}>{show(v)}</Typography.Text> },
        { title: t('audit.new'), dataIndex: 'newValues', render: (v) => <Typography.Text style={{ maxWidth: 320, display: 'inline-block' }} ellipsis={{ tooltip: show(v) }}>{show(v)}</Typography.Text> },
        { title: t('common.comment'), dataIndex: 'comment' },
      ]} />
  );
}
