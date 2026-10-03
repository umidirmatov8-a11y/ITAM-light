import { Button, Checkbox, Input, Modal, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { post } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { Can, useAuth } from '@/app/auth';
import type { AccessItem } from '@/api/types';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect, LookupSelect } from '@/components/Selects';
import { EnumTag } from '@/components/Tags';
import { ACCESS_STATUSES } from '@/utils/enums';
import { fmtDate, fmtDateTime } from '@/utils/format';
import { AccessForm } from './AccessForm';

export default function AccessPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [params] = useSearchParams();
  const [filters, setFilters] = useState<Record<string, unknown>>({ orphanedOnly: params.get('orphanedOnly') ?? undefined, reviewOverdue: params.get('reviewOverdue') ?? undefined });
  const [edit, setEdit] = useState<AccessItem | null>();
  const [revoke, setRevoke] = useState<AccessItem>();
  const [reason, setReason] = useState('');
  const set = (k: string) => (v: unknown) => setFilters((f) => ({ ...f, [k]: v }));
  const revokeMutation = useApiMutation(() => post(`/access/${revoke!.id}/revoke`, { reason }), { invalidate: [['access']], onSuccess: () => { setRevoke(undefined); setReason(''); } });
  const review = useApiMutation((id: string) => post(`/access/${id}/review`, {}), { invalidate: [['access']] });

  const columns: DataColumn<AccessItem>[] = [
    { key: 'employeeName', title: t('access.employee'), dataIndex: 'employeeName', sorter: true, render: (v, r) => <Space><Link to={`/employees/${r.employeeId}`}>{v}</Link>{r.employeeTerminated && <Tag color="red">{t('access.terminated')}</Tag>}</Space> },
    { key: 'departmentName', title: t('common.department'), dataIndex: 'departmentName' },
    { key: 'systemName', title: t('access.system'), dataIndex: 'systemName', sorter: true },
    { key: 'username', title: t('access.username'), dataIndex: 'username' },
    { key: 'levelName', title: t('access.level'), dataIndex: 'levelName' },
    { key: 'role', title: t('access.role'), dataIndex: 'role', hiddenByDefault: true },
    { key: 'status', title: t('common.status'), dataIndex: 'status', sorter: true, render: (v) => <EnumTag group="accessStatus" value={v} /> },
    { key: 'grantedAt', title: t('access.grantedAt'), dataIndex: 'grantedAt', sorter: true, render: fmtDateTime },
    { key: 'revokedAt', title: t('access.revokedAt'), dataIndex: 'revokedAt', render: fmtDateTime, hiddenByDefault: true },
    { key: 'reviewDueDate', title: t('access.reviewDue'), dataIndex: 'reviewDueDate', sorter: true, render: fmtDate },
    { key: 'requestReference', title: t('access.request'), dataIndex: 'requestReference', hiddenByDefault: true },
    {
      key: 'actions', alwaysVisible: true, title: '', render: (_, r) => can('access.manage') && r.status !== 'Revoked' && (
        <Space>
          <Button size="small" onClick={() => setEdit(r)}>{t('common.edit')}</Button>
          <Button size="small" onClick={() => review.mutate(r.id)}>{t('access.reviewed')}</Button>
          <Button size="small" danger onClick={() => setRevoke(r)}>{t('access.revoke')}</Button>
        </Space>
      ),
    },
  ];
  return (
    <>
      <PageHeader title={t('menu.access')} crumbs={[{ title: t('menu.access') }]}
        extra={<Can perm="access.manage"><Button type="primary" icon={<PlusOutlined />} onClick={() => setEdit(null)}>{t('access.grant')}</Button></Can>} />
      <DataTable<AccessItem> id="access" url="/access" exportUrl="/access/export" columns={columns} params={filters}
        filters={<>
          <LookupSelect lookup="access-systems" placeholder={t('access.system')} style={{ width: 200 }} onChange={set('accessSystemId')} />
          <LookupSelect lookup="regions" placeholder={t('common.region')} style={{ width: 160 }} onChange={set('regionId')} />
          <EnumSelect group="accessStatus" values={ACCESS_STATUSES} placeholder={t('common.status')} style={{ width: 150 }} onChange={set('status')} />
          <Checkbox checked={filters.reviewOverdue === 'true' || filters.reviewOverdue === true} onChange={(e) => set('reviewOverdue')(e.target.checked || undefined)}>{t('access.reviewOverdue')}</Checkbox>
          <Checkbox checked={filters.orphanedOnly === 'true' || filters.orphanedOnly === true} onChange={(e) => set('orphanedOnly')(e.target.checked || undefined)}>{t('access.orphaned')}</Checkbox>
        </>} />
      <AccessForm open={edit !== undefined} access={edit ?? undefined} onClose={() => setEdit(undefined)} invalidate={[['access']]} />
      <Modal open={!!revoke} title={t('access.revoke')} onCancel={() => setRevoke(undefined)} onOk={() => revokeMutation.mutate(undefined)} okButtonProps={{ danger: true }}>
        <p>{revoke?.employeeName}: {revoke?.systemName}</p>
        <Input.TextArea rows={2} placeholder={t('common.reason')} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </>
  );
}
