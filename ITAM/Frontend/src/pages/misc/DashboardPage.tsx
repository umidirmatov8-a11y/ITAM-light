import { Card, Col, List, Row, Select, Skeleton, Space, Table, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { auditActionLabel } from '@/utils/audit';
import { get } from '@/api/client';
import { useAuth } from '@/app/auth';
import { BarChartCard, type Point } from '@/components/Charts';
import { PageHeader } from '@/components/PageHeader';
import { BackdatedTag, EnumTag } from '@/components/Tags';
import { fmtDate, fmtDateTime, fmtMoney, fmtNumber } from '@/utils/format';

interface Dashboard {
  kpis: Record<string, number>;
  charts: Record<string, Point[]>;
  recentOperations: { id: string; number: string; type: string; effectiveAt: string; employeeName?: string; assetCount: number; isBackdated: boolean }[];
  expiring: { kind: string; id: string; title: string; date: string; daysLeft: number; link: string }[];
  recentAudit: { timestamp: string; userName?: string; action: string; entityName?: string }[];
  sections: string[];
}

const KPI_LINKS: Record<string, string> = {
  totalEmployees: '/employees', employeesWithoutEquipment: '/employees?hasAssets=false', terminatedWithEquipment: '/offboarding',
  totalAssets: '/assets', availableAssets: '/assets?statusKind=InStock', assignedAssets: '/assets?statusKind=Assigned', assetsInRepair: '/repairs?openOnly=true',
  lostAssets: '/assets?statusKind=Lost', reservedAssets: '/assets?statusKind=Reserved', assetsWithoutResponsible: '/assets?noResponsible=true',
  warrantyExpiringSoon: '/reports', expiredLicenses: '/licenses?expired=true', licensesExpiringSoon: '/licenses?expiringInDays=30',
  openRepairs: '/repairs?openOnly=true', activeAccesses: '/access', orphanedAccesses: '/access?orphanedOnly=true', pendingSignatures: '/documents?signatureStatus=Pending',
  openOnboarding: '/onboarding', openOffboarding: '/offboarding', failedLogins24h: '/admin/audit?action=auth.login.failed',
};

const ALERT_KPIS = new Set(['lostAssets', 'expiredLicenses', 'terminatedWithEquipment', 'orphanedAccesses', 'failedLogins24h']);

export default function DashboardPage() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const navigate = useNavigate();
  const [regionId, setRegionId] = useState<string>();
  const q = useQuery<Dashboard>({ queryKey: ['dashboard', regionId], queryFn: () => get('/dashboard', { regionId }) });
  const d = q.data;

  const kpi = (key: string) => {
    if (d?.kpis[key] === undefined) return null;
    const value = d.kpis[key];
    const alert = ALERT_KPIS.has(key) && value > 0;
    return (
      <Col xs={12} sm={8} md={6} xl={4} key={key}>
        <Card className="itam-kpi" hoverable onClick={() => KPI_LINKS[key] && navigate(KPI_LINKS[key])}>
          <div className="itam-kpi-value" style={alert ? { color: '#e34948' } : undefined}>{key === 'totalAssetValue' ? fmtMoney(value) : fmtNumber(value)}</div>
          <div className="itam-kpi-label">{t(`dashboard.kpi.${key}`)}</div>
        </Card>
      </Col>
    );
  };

  const chart = (key: string, horizontal = false, useItemColors = false) =>
    d?.charts[key] && (
      <Col xs={24} lg={12} key={key}>
        <Card title={t(`dashboard.chart.${key}`)} size="small">
          <BarChartCard data={d.charts[key]} horizontal={horizontal} useItemColors={useItemColors} />
        </Card>
      </Col>
    );

  return (
    <>
      <PageHeader
        title={t('dashboard.title')}
        subtitle={t('dashboard.welcome', { name: me?.displayName })}
        extra={me && me.regions.length > 1 && (
          <Select allowClear placeholder={t('dashboard.allRegions')} style={{ width: 220 }} value={regionId} onChange={setRegionId}
            options={me.regions.map((r) => ({ value: r.id, label: r.name }))} />
        )}
      />
      {q.isLoading ? <Skeleton active /> : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Row gutter={[12, 12]}>
            {['totalEmployees', 'totalAssets', 'availableAssets', 'assignedAssets', 'assetsInRepair', 'lostAssets', 'reservedAssets', 'totalAssetValue',
              'expiredLicenses', 'licensesExpiringSoon', 'employeesWithoutEquipment', 'assetsWithoutResponsible', 'terminatedWithEquipment', 'openRepairs',
              'warrantyExpiringSoon', 'activeAccesses', 'orphanedAccesses', 'pendingSignatures', 'openOnboarding', 'openOffboarding', 'failedLogins24h'].map(kpi)}
          </Row>
          <Row gutter={[16, 16]}>
            {chart('assetsByType', true)}
            {chart('assetsByStatus', true, true)}
            {chart('assetsByRegion')}
            {chart('assetsByDepartment', true)}
            {chart('repairsByMonth')}
            {chart('acquisitionByYear')}
          </Row>
          <Row gutter={[16, 16]}>
            {d?.sections.includes('assets') && (
              <Col xs={24} xl={12}>
                <Card title={t('dashboard.recentOperations')} size="small" extra={<Link to="/operations">{t('common.all')}</Link>}>
                  <Table size="small" rowKey="id" pagination={false} dataSource={d.recentOperations}
                    columns={[
                      { title: t('operations.number'), dataIndex: 'number', render: (v, r) => <Link to={`/operations/${r.id}`}>{v}</Link> },
                      { title: t('operations.type'), dataIndex: 'type', render: (v) => <EnumTag group="operation" value={v} /> },
                      { title: t('operations.effectiveAt'), dataIndex: 'effectiveAt', render: (v, r) => <Space size={4}>{fmtDateTime(v)}<BackdatedTag show={r.isBackdated} /></Space> },
                      { title: t('operations.employee'), dataIndex: 'employeeName' },
                      { title: t('operations.assets'), dataIndex: 'assetCount' },
                    ]} />
                </Card>
              </Col>
            )}
            {d && d.expiring.length > 0 && (
              <Col xs={24} xl={12}>
                <Card title={t('dashboard.expiring')} size="small">
                  <List size="small" dataSource={d.expiring} renderItem={(i) => (
                    <List.Item extra={<Tag color={i.daysLeft <= 7 ? 'red' : 'gold'}>{t('dashboard.daysLeft', { count: i.daysLeft })}</Tag>}>
                      <Space><Tag>{t(`dashboard.expiringKind.${i.kind}`)}</Tag><Link to={i.link}>{i.title}</Link><span className="itam-muted">{fmtDate(i.date)}</span></Space>
                    </List.Item>
                  )} />
                </Card>
              </Col>
            )}
            {d?.sections.includes('audit') && (
              <Col xs={24} xl={12}>
                <Card title={t('dashboard.recentAudit')} size="small" extra={<Link to="/admin/audit">{t('common.all')}</Link>}>
                  <List size="small" dataSource={d.recentAudit} renderItem={(a) => (
                    <List.Item>
                      <Typography.Text className="itam-mono" type="secondary">{fmtDateTime(a.timestamp)}</Typography.Text>&nbsp;
                      <b>{a.userName}</b>&nbsp;<Tag>{auditActionLabel(t, a.action)}</Tag>{a.entityName}
                    </List.Item>
                  )} />
                </Card>
              </Col>
            )}
          </Row>
        </Space>
      )}
    </>
  );
}
