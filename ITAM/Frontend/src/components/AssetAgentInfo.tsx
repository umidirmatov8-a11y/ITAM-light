import { Card, Descriptions } from 'antd';
import { DesktopOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { get } from '@/api/client';
import { useAuth } from '@/app/auth';
import { LastSeen } from '@/pages/agents/AgentsPage';
import { UserMismatchAlert } from '@/pages/agents/AgentCard';
import { ramGb, type AgentDevice } from '@/pages/agents/types';

const useAgentDevice = (assetId: string) =>
  useQuery<AgentDevice | null>({ queryKey: ['agent-by-asset', assetId], queryFn: async () => (await get<AgentDevice | ''>(`/agents/by-asset/${assetId}`)) || null });

/** Warning on the asset card when the computer is used by someone other than its holder. */
export function AssetAgentAlert({ assetId }: { assetId: string }) {
  const q = useAgentDevice(assetId);
  return q.data ? <UserMismatchAlert d={q.data} /> : null;
}

/** "Agent data" card on the asset page: live hardware facts reported by the computer itself. */
export function AssetAgentCard({ assetId }: { assetId: string }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const q = useAgentDevice(assetId);
  const d = q.data;
  if (!d) return null;
  return (
    <Card size="small" title={<><DesktopOutlined /> {t('agents.cardTitle')}</>}
      extra={can('agents.view') && <Link to={`/agents/${d.id}`}>{t('agents.details')}</Link>}>
      <Descriptions size="small" column={1}>
        <Descriptions.Item label={t('agents.hostname')}><b>{d.hostname}</b></Descriptions.Item>
        <Descriptions.Item label={t('agents.currentUser')}>
          {d.currentEmployeeId ? <Link to={`/employees/${d.currentEmployeeId}`}>{d.currentEmployeeName}</Link> : d.currentUser}
        </Descriptions.Item>
        <Descriptions.Item label={t('agents.os')}>{d.osName} {d.osVersion}</Descriptions.Item>
        <Descriptions.Item label={t('agents.cpu')}>{d.cpu}</Descriptions.Item>
        <Descriptions.Item label={t('agents.ram')}>{ramGb(d.ramMb, t('agents.gb'))}</Descriptions.Item>
        <Descriptions.Item label="IP"><span className="itam-mono">{d.ipAddress}</span></Descriptions.Item>
        <Descriptions.Item label={t('agents.lastSeen')}><LastSeen at={d.lastSeenAt} stale={d.isStale} /></Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
