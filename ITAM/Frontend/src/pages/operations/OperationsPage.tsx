import { Button, Checkbox, DatePicker, Dropdown, Space } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/app/auth';
import type { BatchListItem } from '@/api/types';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, EnumSelect } from '@/components/Selects';
import { BackdatedTag, EnumTag } from '@/components/Tags';
import { OPERATION_TYPES } from '@/utils/enums';
import { fmtDateTime, toApiDateTime } from '@/utils/format';

export default function OperationsPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const set = (k: string) => (v: unknown) => setFilters((f) => ({ ...f, [k]: v }));
  const columns: DataColumn<BatchListItem>[] = [
    { key: 'number', title: t('operations.number'), dataIndex: 'number', sorter: true, alwaysVisible: true, render: (v, r) => <Link to={`/operations/${r.id}`} className={r.isCancelled ? 'itam-cancelled' : undefined}>{v}</Link> },
    { key: 'type', title: t('operations.type'), dataIndex: 'type', render: (v) => <EnumTag group="operation" value={v} /> },
    { key: 'effectiveAt', title: t('operations.effectiveAt'), dataIndex: 'effectiveAt', sorter: true, render: (v, r) => <Space size={4}>{fmtDateTime(v)}<BackdatedTag show={r.isBackdated} /></Space> },
    { key: 'recordedAt', title: t('common.recordedAt'), dataIndex: 'recordedAt', sorter: true, render: fmtDateTime },
    { key: 'createdBy', title: t('common.recordedBy'), dataIndex: 'createdBy' },
    { key: 'employeeName', title: t('operations.employee'), dataIndex: 'employeeName' },
    { key: 'assetNumbers', title: t('operations.assets'), dataIndex: 'assetNumbers', render: (v, r) => <>{v}{r.assetCount > 5 && ` +${r.assetCount - 5}`}</> },
    { key: 'employeeSignatureStatus', title: t('documents.employeeSignature'), dataIndex: 'employeeSignatureStatus', render: (v) => <EnumTag group="signature" value={v} /> },
    { key: 'documentCount', title: t('tabs.documents'), dataIndex: 'documentCount' },
    { key: 'comment', title: t('common.comment'), dataIndex: 'comment', hiddenByDefault: true },
  ];
  return (
    <>
      <PageHeader title={t('menu.operations')} crumbs={[{ title: t('menu.operations') }]}
        extra={<Dropdown menu={{ items: [
          can('assets.assign') && { key: 'i', label: t('assets.actions.issue'), onClick: () => navigate('/operations/issue') },
          can('assets.return') && { key: 'r', label: t('assets.actions.return'), onClick: () => navigate('/operations/return') },
          can('assets.transfer') && { key: 't', label: t('assets.actions.transfer'), onClick: () => navigate('/operations/transfer') },
          can('assets.status') && { key: 's', label: t('assets.actions.status'), onClick: () => navigate('/operations/status') },
        ].filter(Boolean) as never }}><Button type="primary" icon={<PlusOutlined />}>{t('operations.new')}</Button></Dropdown>} />
      <DataTable<BatchListItem> id="operations" url="/operations" columns={columns} params={filters} defaultSort={{ field: 'effectiveAt', order: 'desc' }}
        filters={<>
          <EnumSelect group="operation" values={OPERATION_TYPES} placeholder={t('operations.type')} style={{ width: 170 }} onChange={set('type')} />
          <EmployeeSelect activeOnly={false} style={{ width: 240 }} onChange={set('employeeId')} />
          <DatePicker.RangePicker showTime format="DD.MM.YYYY" onChange={(r) => setFilters((f) => ({ ...f, from: toApiDateTime(r?.[0]), to: toApiDateTime(r?.[1]) }))} />
          <Checkbox onChange={(e) => set('backdated')(e.target.checked || undefined)}>{t('operations.onlyBackdated')}</Checkbox>
        </>} />
    </>
  );
}
