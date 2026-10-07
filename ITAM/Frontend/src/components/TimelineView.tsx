import { Empty, Space, Tag, Timeline, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TimelineItem } from '@/api/types';
import { fmtDateTime } from '@/utils/format';

/** Timeline built from historical events: business date first, recording date and author as metadata. */
export function TimelineView({ items }: { items?: TimelineItem[] }) {
  const { t } = useTranslation();
  if (!items || items.length === 0) return <Empty description={t('common.noHistory')} />;
  return (
    <Timeline
      mode="left"
      items={items.map((i, idx) => ({
        key: idx,
        color: i.isCancelled ? 'gray' : i.color ?? 'blue',
        label: <span className="itam-mono">{fmtDateTime(i.date)}</span>,
        children: (
          <div className={i.isCancelled ? 'itam-cancelled' : undefined}>
            <Space wrap size={4}>
              <Typography.Text strong>{i.link ? <Link to={i.link}>{i.title}</Link> : i.title}</Typography.Text>
              {i.isBackdated && <Tag color="orange">{t('common.backdated')}</Tag>}
              {i.isCancelled && <Tag>{t('common.cancelled')}</Tag>}
            </Space>
            {i.description && <div>{i.description}</div>}
            {(i.recordedAt || i.user) && (
              <div className="itam-muted" style={{ fontSize: 12 }}>
                {i.recordedAt && t('common.recordedAt', { date: fmtDateTime(i.recordedAt) })} {i.user && `· ${i.user}`}
              </div>
            )}
          </div>
        ),
      }))}
    />
  );
}
