import { Button, Card, List, Segmented, Space, Tag } from 'antd';
import { CheckOutlined, ExclamationCircleOutlined, InfoCircleOutlined, WarningOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post, type Paged } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { NotificationItem } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { fmtDateTime } from '@/utils/format';

const ICONS = { Info: <InfoCircleOutlined style={{ color: '#2a78d6' }} />, Warning: <WarningOutlined style={{ color: '#eda100' }} />, Critical: <ExclamationCircleOutlined style={{ color: '#e34948' }} /> };

export default function NotificationsPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [filter, setFilter] = useState<'all' | 'unread'>('unread');
  const [page, setPage] = useState(1);
  const q = useQuery<Paged<NotificationItem>>({ queryKey: ['notifications', filter, page], queryFn: () => get('/notifications', { unreadOnly: filter === 'unread', page, pageSize: 30 }) });
  const markAll = useApiMutation(() => post('/notifications/read', { ids: null }), { invalidate: [['notifications'], ['notifications-unread']] });
  const mark = useApiMutation((id: string) => post('/notifications/read', { ids: [id] }), { invalidate: [['notifications'], ['notifications-unread']], success: false });
  const run = useApiMutation(() => post<{ created: number }>('/notifications/run'), { invalidate: [['notifications'], ['notifications-unread']] });
  return (
    <>
      <PageHeader title={t('notifications.title')} crumbs={[{ title: t('notifications.title') }]}
        extra={<>
          {can('settings.manage') && <Button onClick={() => run.mutate(undefined)} loading={run.isPending}>{t('notifications.runRules')}</Button>}
          <Button icon={<CheckOutlined />} onClick={() => markAll.mutate(undefined)}>{t('notifications.markAll')}</Button>
        </>} />
      <Card>
        <Segmented value={filter} onChange={(v) => { setFilter(v as 'all' | 'unread'); setPage(1); }} options={[{ value: 'unread', label: t('notifications.unread') }, { value: 'all', label: t('common.all') }]} style={{ marginBottom: 12 }} />
        <List
          loading={q.isLoading}
          dataSource={q.data?.items}
          pagination={{ current: page, pageSize: 30, total: q.data?.total, onChange: setPage }}
          renderItem={(n) => (
            <List.Item style={{ opacity: n.isRead ? 0.6 : 1 }} actions={[!n.isRead && <Button key="r" size="small" onClick={() => mark.mutate(n.id)}>{t('notifications.markRead')}</Button>].filter(Boolean)}>
              <List.Item.Meta
                avatar={ICONS[n.severity]}
                title={<Space>{n.link ? <Link to={n.link} onClick={() => !n.isRead && mark.mutate(n.id)}>{n.title}</Link> : n.title}<Tag>{t(`enums.severity.${n.severity}`)}</Tag></Space>}
                description={<>{n.message}<div className="itam-muted" style={{ fontSize: 12 }}>{fmtDateTime(n.createdAt)}</div></>}
              />
            </List.Item>
          )}
        />
      </Card>
    </>
  );
}
