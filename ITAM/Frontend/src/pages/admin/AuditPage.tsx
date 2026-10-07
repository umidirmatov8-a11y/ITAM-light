import { Card, DatePicker, Dropdown, Button, Input, Select, Space } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { download, get, type Paged } from '@/api/client';
import { useNotify } from '@/api/hooks';
import { AuditTable, type AuditRow } from '@/components/AuditTable';
import { PageHeader } from '@/components/PageHeader';
import { toApiDateTime } from '@/utils/format';

export default function AuditPage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const [params] = useSearchParams();
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<Record<string, unknown>>({ action: params.get('action') ?? undefined });
  const set = (k: string) => (v: unknown) => { setFilters((f) => ({ ...f, [k]: v || undefined })); setPage(1); };
  const actions = useQuery<string[]>({ queryKey: ['audit-actions'], queryFn: () => get('/audit/actions') });
  const q = useQuery<Paged<AuditRow>>({ queryKey: ['audit', filters, page], queryFn: () => get('/audit', { ...filters, page, pageSize: 50 }), placeholderData: keepPreviousData });
  return (
    <>
      <PageHeader title={t('menu.audit')} subtitle={t('audit.readonly')} crumbs={[{ title: t('menu.admin') }, { title: t('menu.audit') }]}
        extra={<Dropdown menu={{ items: ['xlsx', 'csv', 'pdf'].map((f) => ({ key: f, label: f.toUpperCase(), onClick: () => download('/audit/export', { ...filters, format: f }).catch(notify.error) })) }}>
          <Button icon={<DownloadOutlined />}>{t('common.export')}</Button></Dropdown>} />
      <Card>
        <Space wrap style={{ marginBottom: 12 }}>
          <Input.Search allowClear placeholder={t('common.search')} onSearch={set('search')} style={{ width: 260 }} />
          <Select allowClear showSearch placeholder={t('audit.action')} style={{ width: 260 }} value={filters.action as string} onChange={set('action')} options={(actions.data ?? []).map((a) => ({ value: a, label: a }))} />
          <Input allowClear placeholder="IP" style={{ width: 160 }} onChange={(e) => set('ipAddress')(e.target.value)} />
          <DatePicker.RangePicker showTime format="DD.MM.YYYY HH:mm" onChange={(r) => { setFilters((f) => ({ ...f, from: toApiDateTime(r?.[0]), to: toApiDateTime(r?.[1]) })); setPage(1); }} />
          <Select allowClear placeholder={t('audit.result')} style={{ width: 140 }} onChange={set('success')} options={[{ value: 'true', label: t('audit.success') }, { value: 'false', label: t('audit.failure') }]} />
        </Space>
        <AuditTable rows={q.data?.items} loading={q.isFetching} pagination={{ current: page, pageSize: 50, total: q.data?.total, onChange: setPage, showSizeChanger: false }} />
      </Card>
    </>
  );
}
