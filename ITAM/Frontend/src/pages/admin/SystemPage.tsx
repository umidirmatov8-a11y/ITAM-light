import { Card, Descriptions, Skeleton, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { get } from '@/api/client';
import { PageHeader } from '@/components/PageHeader';
import { fmtDateTime, fmtNumber, fmtSize } from '@/utils/format';

export default function SystemPage() {
  const { t } = useTranslation();
  const q = useQuery<any>({ queryKey: ['system'], queryFn: () => get('/admin/system') });
  if (q.isLoading || !q.data) return <Skeleton active />;
  const s = q.data;
  return (
    <>
      <PageHeader title={t('menu.system')} crumbs={[{ title: t('menu.admin') }, { title: t('menu.system') }]} />
      <Card>
        <Descriptions bordered column={1} size="small">
          <Descriptions.Item label={t('system.version')}>{s.version}</Descriptions.Item>
          <Descriptions.Item label={t('system.database')}>{s.database} · {s.databaseVersion} · {fmtSize(s.databaseSizeBytes)} {s.databaseReady ? <Tag color="green">OK</Tag> : <Tag color="red">!</Tag>}</Descriptions.Item>
          <Descriptions.Item label={t('system.dataRoot')}><span className="itam-mono">{s.dataRoot}</span></Descriptions.Item>
          <Descriptions.Item label={t('system.os')}>{s.osDescription}</Descriptions.Item>
          <Descriptions.Item label={t('system.framework')}>{s.framework}</Descriptions.Item>
          <Descriptions.Item label={t('system.serverTime')}>{fmtDateTime(s.serverTimeUtc)}</Descriptions.Item>
          <Descriptions.Item label={t('menu.users')}>{fmtNumber(s.users)}</Descriptions.Item>
          <Descriptions.Item label={t('menu.employees')}>{fmtNumber(s.employees)}</Descriptions.Item>
          <Descriptions.Item label={t('menu.assets')}>{fmtNumber(s.assets)}</Descriptions.Item>
          <Descriptions.Item label={t('menu.audit')}>{fmtNumber(s.auditRecords)}</Descriptions.Item>
          <Descriptions.Item label="API"><a href="/swagger" target="_blank" rel="noreferrer">/swagger</a></Descriptions.Item>
        </Descriptions>
      </Card>
    </>
  );
}
