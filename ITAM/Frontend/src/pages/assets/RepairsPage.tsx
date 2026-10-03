import { Button, Checkbox, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Can } from '@/app/auth';
import type { RepairListItem } from '@/api/types';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect, LookupSelect } from '@/components/Selects';
import { StatusTag } from '@/components/Tags';
import { REPAIR_STAGES } from '@/utils/enums';
import { fmtDate, fmtDateTime, fmtMoney } from '@/utils/format';
import { RepairForm } from './RepairForm';

export default function RepairsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState<Record<string, unknown>>({ openOnly: params.get('openOnly') ?? undefined });
  const set = (k: string) => (v: unknown) => setFilters((f) => ({ ...f, [k]: v }));
  const columns: DataColumn<RepairListItem>[] = [
    { key: 'number', title: t('repairs.number'), dataIndex: 'number', sorter: true, alwaysVisible: true, render: (v, r) => <Link to={`/repairs/${r.id}`}>{v}</Link> },
    { key: 'inventoryNumber', title: t('assets.inventoryNumber'), dataIndex: 'inventoryNumber', sorter: true, render: (v, r) => <Link className="itam-mono" to={`/assets/${r.assetId}`}>{v}</Link> },
    { key: 'assetName', title: t('assets.name'), dataIndex: 'assetName' },
    { key: 'statusName', title: t('common.status'), dataIndex: 'statusName', sorter: true, render: (v, r) => <Space><StatusTag name={v} color={r.statusColor} />{r.isOverdue && <Tag color="red">{t('repairs.overdue')}</Tag>}</Space> },
    { key: 'openedAt', title: t('repairs.openedAt'), dataIndex: 'openedAt', sorter: true, render: fmtDateTime },
    { key: 'problem', title: t('repairs.problem'), dataIndex: 'problem', ellipsis: true },
    { key: 'serviceCenterName', title: t('repairs.serviceCenter'), dataIndex: 'serviceCenterName' },
    { key: 'expectedReturnDate', title: t('repairs.expectedReturn'), dataIndex: 'expectedReturnDate', sorter: true, render: fmtDate },
    { key: 'actualReturnAt', title: t('repairs.returnedAt'), dataIndex: 'actualReturnAt', render: fmtDateTime, hiddenByDefault: true },
    { key: 'cost', title: t('repairs.cost'), dataIndex: 'cost', sorter: true, render: (v, r) => fmtMoney(v, r.currency) },
    { key: 'isWarranty', title: t('repairs.warranty'), dataIndex: 'isWarranty', render: (v) => (v ? t('common.yes') : ''), hiddenByDefault: true },
    { key: 'regionName', title: t('common.region'), dataIndex: 'regionName', hiddenByDefault: true },
  ];
  return (
    <>
      <PageHeader title={t('menu.repairs')} crumbs={[{ title: t('menu.repairs') }]}
        extra={<Can perm="assets.repair"><Button type="primary" icon={<PlusOutlined />} onClick={() => setParams({ new: '1' })}>{t('repairs.new')}</Button></Can>} />
      <DataTable<RepairListItem> id="repairs" url="/repairs" exportUrl="/repairs/export" columns={columns} params={filters}
        filters={<>
          <EnumSelect group="repairStage" values={REPAIR_STAGES} placeholder={t('repairs.stage')} style={{ width: 170 }} onChange={set('stage')} />
          <LookupSelect lookup="suppliers" placeholder={t('repairs.serviceCenter')} style={{ width: 200 }} onChange={set('serviceCenterId')} />
          <LookupSelect lookup="regions" placeholder={t('common.region')} style={{ width: 150 }} onChange={set('regionId')} />
          <Checkbox checked={!!filters.openOnly} onChange={(e) => set('openOnly')(e.target.checked || undefined)}>{t('repairs.openOnly')}</Checkbox>
          <Checkbox onChange={(e) => set('overdue')(e.target.checked || undefined)}>{t('repairs.overdue')}</Checkbox>
        </>}
        onRow={(r) => ({ onDoubleClick: () => navigate(`/repairs/${r.id}`) })} />
      <RepairForm open={params.get('new') === '1'} onClose={() => setParams({})} onSaved={(r) => navigate(`/repairs/${r.id}`)} />
    </>
  );
}
