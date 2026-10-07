import { Button, Card, Descriptions, Result, Spin, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { get, ApiError } from '@/api/client';

interface PublicAsset { id: string; inventoryNumber: string; name?: string; model?: string; status?: string; statusColor?: string; location?: string; organizationName: string }

/** Limited QR view: no personal data, no license keys. Full card requires login. */
export default function PublicAssetPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const q = useQuery<PublicAsset>({ queryKey: ['public-asset', id], queryFn: () => get(`/public/assets/${id}`), retry: false });
  const login = <Button type="primary" href={`/login?next=${encodeURIComponent(`/assets/${id}`)}`}>{t('public.loginForDetails')}</Button>;
  if (q.isLoading) return <Spin style={{ display: 'block', marginTop: 80 }} />;
  if (q.error) return <Result status="warning" title={(q.error as ApiError).message} extra={login} />;
  const a = q.data!;
  return (
    <div className="itam-public">
      <Card title={a.organizationName}>
        <Typography.Title level={3} className="itam-mono">{a.inventoryNumber}</Typography.Title>
        <Descriptions column={1} bordered size="small">
          {a.name && <Descriptions.Item label={t('assets.name')}>{a.name}</Descriptions.Item>}
          {a.model && <Descriptions.Item label={t('assets.model')}>{a.model}</Descriptions.Item>}
          {a.status && <Descriptions.Item label={t('common.status')}><Tag color={a.statusColor}>{a.status}</Tag></Descriptions.Item>}
          {a.location && <Descriptions.Item label={t('assets.location')}>{a.location}</Descriptions.Item>}
          <Descriptions.Item label="ID"><span className="itam-mono">{a.id}</span></Descriptions.Item>
        </Descriptions>
        <div style={{ marginTop: 16 }}>{login}</div>
      </Card>
    </div>
  );
}
