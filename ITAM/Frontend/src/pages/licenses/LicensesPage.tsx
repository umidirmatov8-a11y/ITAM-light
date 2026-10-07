import { Button, Card, Checkbox, Col, Progress, Row, Space, Statistic, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get } from '@/api/client';
import { Can } from '@/app/auth';
import type { LicenseListItem } from '@/api/types';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect, LookupSelect } from '@/components/Selects';
import { EnumTag } from '@/components/Tags';
import { LICENSE_MODELS } from '@/utils/enums';
import { fmtDate, fmtMoney } from '@/utils/format';
import { LicenseForm } from './LicenseForm';

export function ExpiryTag({ days, expired }: { days?: number; expired?: boolean }) {
  const { t } = useTranslation();
  if (days === undefined || days === null) return null;
  if (expired) return <Tag color="red">{t('licenses.expired')}</Tag>;
  if (days <= 30) return <Tag color="gold">{t('licenses.expiresIn', { count: days })}</Tag>;
  return null;
}

export default function LicensesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [open, setOpen] = useState(false);
  const [filters, setFilters] = useState<Record<string, unknown>>({ expired: params.get('expired') ?? undefined, expiringInDays: params.get('expiringInDays') ?? undefined });
  const set = (k: string) => (v: unknown) => setFilters((f) => ({ ...f, [k]: v }));
  const summary = useQuery<{ licenses: number; totalSeats: number; usedSeats: number; availableSeats: number; expiredSeats: number; expiringSoon: number; overAllocated: number }>({
    queryKey: ['licenses', 'summary'], queryFn: () => get('/licenses/summary'),
  });
  const columns: DataColumn<LicenseListItem>[] = [
    { key: 'name', title: t('common.name'), dataIndex: 'name', sorter: true, alwaysVisible: true, render: (v, r) => <Space><Link to={`/licenses/${r.id}`}>{v}</Link><ExpiryTag days={r.daysToExpiry} expired={r.isExpired} /></Space> },
    { key: 'softwareName', title: t('licenses.software'), dataIndex: 'softwareName', sorter: true },
    { key: 'vendorName', title: t('licenses.vendor'), dataIndex: 'vendorName' },
    { key: 'model', title: t('licenses.model'), dataIndex: 'model', render: (v) => <EnumTag group="licenseModel" value={v} /> },
    { key: 'seats', title: t('licenses.usage'), dataIndex: 'seats', sorter: true, render: (_, r) => (
      <Space><Progress percent={r.seats ? Math.round((r.usedSeats / r.seats) * 100) : 0} size="small" style={{ width: 90 }} status={r.usedSeats > r.seats ? 'exception' : 'normal'} showInfo={false} />{r.usedSeats}/{r.seats}</Space>
    ) },
    { key: 'availableSeats', title: t('licenses.available'), dataIndex: 'availableSeats' },
    { key: 'expirationDate', title: t('licenses.expiration'), dataIndex: 'expirationDate', sorter: true, render: fmtDate },
    { key: 'purchaseDate', title: t('assets.purchaseDate'), dataIndex: 'purchaseDate', render: fmtDate, hiddenByDefault: true },
    { key: 'cost', title: t('assets.price'), dataIndex: 'cost', sorter: true, render: (v, r) => fmtMoney(v, r.currency), hiddenByDefault: true },
    { key: 'regionName', title: t('common.region'), dataIndex: 'regionName', hiddenByDefault: true },
  ];
  const s = summary.data;
  return (
    <>
      <PageHeader title={t('menu.licenses')} crumbs={[{ title: t('menu.licenses') }]}
        extra={<Can perm="licenses.manage"><Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>{t('licenses.new')}</Button></Can>} />
      {s && (
        <Row gutter={12} style={{ marginBottom: 16 }}>
          {[['totalSeats', s.totalSeats], ['usedSeats', s.usedSeats], ['availableSeats', s.availableSeats], ['expiredSeats', s.expiredSeats], ['expiringSoon', s.expiringSoon], ['overAllocated', s.overAllocated]].map(([k, v]) => (
            <Col xs={12} md={4} key={k as string}><Card size="small"><Statistic title={t(`licenses.summary.${k}`)} value={v as number} /></Card></Col>
          ))}
        </Row>
      )}
      <DataTable<LicenseListItem> id="licenses" url="/licenses" exportUrl="/licenses/export" columns={columns} params={filters}
        filters={<>
          <LookupSelect lookup="software" placeholder={t('licenses.software')} style={{ width: 200 }} onChange={set('softwareId')} />
          <EnumSelect group="licenseModel" values={LICENSE_MODELS} placeholder={t('licenses.model')} style={{ width: 160 }} onChange={set('model')} />
          <Checkbox checked={!!filters.expired} onChange={(e) => set('expired')(e.target.checked || undefined)}>{t('licenses.expired')}</Checkbox>
          <Checkbox checked={!!filters.expiringInDays} onChange={(e) => set('expiringInDays')(e.target.checked ? 30 : undefined)}>{t('licenses.expiring30')}</Checkbox>
          <Checkbox onChange={(e) => set('overAllocated')(e.target.checked || undefined)}>{t('licenses.overAllocated')}</Checkbox>
        </>}
        onRow={(r) => ({ onDoubleClick: () => navigate(`/licenses/${r.id}`) })} />
      <LicenseForm open={open} onClose={() => setOpen(false)} onSaved={(l) => navigate(`/licenses/${l.id}`)} />
    </>
  );
}
