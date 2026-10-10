import { Alert, Button, Card, Col, Form, Input, InputNumber, Modal, Popconfirm, Row, Segmented, Space, Statistic, Switch, Table, Tabs, Tag, Tooltip, Typography } from 'antd';
import { CopyOutlined, DownloadOutlined, ReloadOutlined, WarningOutlined } from '@ant-design/icons';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { download, get, post, put, type Paged } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { LookupSelect } from '@/components/Selects';
import { fmtDateTime, fromNow } from '@/utils/format';
import type { AgentDeviceListItem, AgentSettings, AgentStatus, AgentSummary, SoftwareSummary } from './types';

const statusColor: Record<AgentStatus, string> = { New: 'gold', Linked: 'green', Ignored: 'default' };

export function AgentStatusTag({ status }: { status: AgentStatus }) {
  const { t } = useTranslation();
  return <Tag color={statusColor[status]} style={{ marginInlineEnd: 0 }}>{t(`agents.status.${status}`)}</Tag>;
}

export function LastSeen({ at, stale }: { at?: string; stale: boolean }) {
  const { t } = useTranslation();
  if (!at) return <Tag>{t('agents.never')}</Tag>;
  return (
    <Tooltip title={fmtDateTime(at)}>
      <span style={stale ? { color: '#e34948' } : undefined}>{stale && <WarningOutlined />} {fromNow(at)}</span>
    </Tooltip>
  );
}

function Devices() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [status, setStatus] = useState<string>(params.get('status') ?? 'all');
  const columns: DataColumn<AgentDeviceListItem>[] = [
    { key: 'hostname', title: t('agents.hostname'), dataIndex: 'hostname', sorter: true, alwaysVisible: true,
      render: (v, r) => <Link to={`/agents/${r.id}`}><b>{v}</b></Link> },
    { key: 'status', title: t('common.status'), dataIndex: 'status', sorter: true, render: (v) => <AgentStatusTag status={v} /> },
    { key: 'asset', title: t('agents.asset'), render: (_, r) => r.assetId ? <Link className="itam-mono" to={`/assets/${r.assetId}`}>{r.assetNumber}</Link> : '' },
    { key: 'currentUser', title: t('agents.currentUser'), dataIndex: 'currentUser', sorter: true,
      render: (v, r) => r.currentEmployeeId ? <Link to={`/employees/${r.currentEmployeeId}`}>{r.currentEmployeeName}</Link> : v },
    { key: 'model', title: t('assets.model'), dataIndex: 'model', sorter: true, render: (v, r) => [r.manufacturer, v].filter(Boolean).join(' ') },
    { key: 'serialNumber', title: t('assets.serialNumber'), dataIndex: 'serialNumber', render: (v) => <span className="itam-mono">{v}</span> },
    { key: 'formFactor', title: t('agents.formFactor'), dataIndex: 'formFactor', hiddenByDefault: true, render: (v) => v && t(`agents.ff.${v}`, { defaultValue: v }) },
    { key: 'osName', title: t('agents.os'), dataIndex: 'osName', sorter: true },
    { key: 'ipAddress', title: 'IP', dataIndex: 'ipAddress', render: (v) => <span className="itam-mono">{v}</span> },
    { key: 'softwareCount', title: t('agents.programs'), dataIndex: 'softwareCount', hiddenByDefault: true },
    { key: 'agentVersion', title: t('agents.agentVersion'), dataIndex: 'agentVersion', hiddenByDefault: true },
    { key: 'registeredAt', title: t('agents.registeredAt'), dataIndex: 'registeredAt', sorter: true, hiddenByDefault: true, render: fmtDateTime },
    { key: 'lastSeenAt', title: t('agents.lastSeen'), dataIndex: 'lastSeenAt', sorter: true, render: (v, r) => <LastSeen at={v} stale={r.isStale} /> },
  ];
  const filter = status === 'stale' ? { stale: true } : status === 'all' ? {} : { status };
  return (
    <DataTable<AgentDeviceListItem> id="agents" url="/agents" columns={columns} params={filter} defaultSort={{ field: 'hostname', order: 'asc' }}
      searchPlaceholder={t('agents.searchHint')}
      filters={<Segmented value={status} onChange={(v) => setStatus(v as string)} options={[
        { value: 'all', label: t('common.all') }, { value: 'New', label: t('agents.status.New') }, { value: 'Linked', label: t('agents.status.Linked') },
        { value: 'Ignored', label: t('agents.status.Ignored') }, { value: 'stale', label: t('agents.stale') }]} />} />
  );
}

function SoftwareTab() {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string>();
  const q = useQuery<Paged<SoftwareSummary>>({ queryKey: ['agent-software', search, page], queryFn: () => get('/agents/software', { search, page, pageSize: 50 }), placeholderData: keepPreviousData });
  const devices = useQuery<any[]>({ queryKey: ['agent-software-devices', selected], queryFn: () => get('/agents/software/devices', { name: selected }), enabled: !!selected });
  return (
    <Card>
      <Input.Search allowClear placeholder={t('agents.softwareSearch')} style={{ width: 360, marginBottom: 12 }} onSearch={(v) => { setSearch(v); setPage(1); }} />
      <Table<SoftwareSummary> rowKey="name" size="small" loading={q.isFetching} dataSource={q.data?.items}
        pagination={{ current: page, pageSize: 50, total: q.data?.total, onChange: setPage, showSizeChanger: false, showTotal: (n) => t('common.total', { count: n }) }}
        columns={[
          { title: t('common.name'), dataIndex: 'name', render: (v) => <a onClick={() => setSelected(v)}>{v}</a> },
          { title: t('agents.publisher'), dataIndex: 'publisher' },
          { title: t('agents.installs'), dataIndex: 'devices', width: 120 },
          { title: t('agents.versions'), dataIndex: 'versions', width: 100 },
          { title: t('agents.latestVersion'), dataIndex: 'latestVersion' },
        ]} />
      <Modal open={!!selected} title={selected} footer={null} width={860} onCancel={() => setSelected(undefined)}>
        <Table rowKey="deviceId" size="small" loading={devices.isLoading} dataSource={devices.data} pagination={{ pageSize: 20 }}
          columns={[
            { title: t('agents.hostname'), dataIndex: 'hostname', render: (v, r) => <Link to={`/agents/${r.deviceId}`}>{v}</Link> },
            { title: t('agents.version'), dataIndex: 'version' },
            { title: t('agents.currentUser'), dataIndex: 'currentUser' },
            { title: t('agents.asset'), dataIndex: 'assetNumber', render: (v, r) => r.assetId && <Link to={`/assets/${r.assetId}`}>{v}</Link> },
            { title: t('agents.lastSeen'), dataIndex: 'lastSeenAt', render: fmtDateTime },
          ]} />
      </Modal>
    </Card>
  );
}

function Copyable({ text, mono = true }: { text: string; mono?: boolean }) {
  const notify = useNotify();
  const { t } = useTranslation();
  return (
    <Space.Compact style={{ width: '100%' }}>
      <Input readOnly value={text} className={mono ? 'itam-mono' : undefined} />
      <Button icon={<CopyOutlined />} onClick={() => navigator.clipboard?.writeText(text).then(() => notify.success(t('agents.copied')))} />
    </Space.Compact>
  );
}

function InstallTab() {
  const { t } = useTranslation();
  const notify = useNotify();
  const [form] = Form.useForm<AgentSettings>();
  const regionId = Form.useWatch('defaultRegionId', form);
  const s = useQuery<AgentSettings>({ queryKey: ['agent-settings'], queryFn: () => get('/agents/settings') });
  useEffect(() => { if (s.data) form.setFieldsValue(s.data); }, [s.data, form]);
  const save = useApiMutation((v: AgentSettings) => put('/agents/settings', v), { invalidate: [['agent-settings']] });
  const regenerate = useApiMutation(() => post('/agents/settings/regenerate-key'), { invalidate: [['agent-settings']] });
  const server = (s.data?.serverUrl || window.location.origin).replace(/\/$/, '');
  const key = s.data?.enrollmentKey ?? '';
  const oneLiner = `powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path $env:TEMP 'itam-agent'; iwr -UseBasicParsing '${server}/api/agent/package' -OutFile ($p+'.zip'); Expand-Archive -Force ($p+'.zip') $p; & (Join-Path $p 'install.cmd') -ServerUrl '${server}' -EnrollmentKey '${key}'"`;
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={14}>
        <Card title={t('agents.install.manualTitle')}>
          <Typography.Paragraph>{t('agents.install.manualText')}</Typography.Paragraph>
          <Space wrap style={{ marginBottom: 16 }}>
            <Button type="primary" icon={<DownloadOutlined />} onClick={() => download('/agents/package').catch(notify.error)}>{t('agents.install.download')}</Button>
          </Space>
          <ol className="itam-steps">
            <li>{t('agents.install.manual1')}</li>
            <li>{t('agents.install.manual2')}</li>
            <li>{t('agents.install.manual3')}</li>
          </ol>
          <Typography.Paragraph strong style={{ marginTop: 16 }}>{t('agents.install.oneLiner')}</Typography.Paragraph>
          <Copyable text={oneLiner} />
          <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>{t('agents.install.oneLinerHint')}</Typography.Paragraph>
        </Card>
        <Card title={t('agents.install.gpoTitle')} style={{ marginTop: 16 }}>
          <ol className="itam-steps">
            <li>{t('agents.install.gpo1')} <a href="/api/agent/package">{t('agents.install.gpoPackage')}</a></li>
            <li>{t('agents.install.gpo2')}</li>
            <li>{t('agents.install.gpo3')}<br /><Typography.Text code>{t('agents.install.gpoPath')}</Typography.Text></li>
            <li>{t('agents.install.gpo4')}<br /><Typography.Text code>\\domain\NETLOGON\ITAM-Agent\install.cmd</Typography.Text></li>
            <li>{t('agents.install.gpo5')}</li>
          </ol>
          <Alert type="info" showIcon message={t('agents.install.gpoNote')} />
        </Card>
      </Col>
      <Col xs={24} xl={10}>
        <Card title={t('agents.install.connection')}>
          <Form layout="vertical">
            <Form.Item label={t('agents.install.serverUrl')} extra={t('agents.install.serverUrlHint')}><Copyable text={server} /></Form.Item>
            <Form.Item label={t('agents.install.key')} extra={t('agents.install.keyHint')}>
              <Copyable text={key} />
              <Popconfirm title={t('agents.install.regenerateConfirm')} description={t('agents.install.regenerateHint')} onConfirm={() => regenerate.mutate(undefined)}>
                <Button icon={<ReloadOutlined />} style={{ marginTop: 8 }} loading={regenerate.isPending}>{t('agents.install.regenerate')}</Button>
              </Popconfirm>
            </Form.Item>
          </Form>
        </Card>
        <Card title={t('agents.install.settings')} style={{ marginTop: 16 }}>
          <Form form={form} layout="vertical" onFinish={(v) => save.mutate({ ...s.data!, ...v })}>
            <Form.Item name="autoCreateAssets" label={t('agents.install.autoCreate')} valuePropName="checked" extra={t('agents.install.autoCreateHint')}><Switch /></Form.Item>
            <Form.Item name="defaultRegionId" label={t('agents.install.defaultRegion')}><LookupSelect lookup="regions" /></Form.Item>
            <Form.Item name="defaultLocationId" label={t('agents.install.defaultLocation')}>
              <LookupSelect lookup="locations" filter={(l) => !regionId || l.regionId === regionId} />
            </Form.Item>
            <Form.Item name="updateAssetFields" label={t('agents.install.updateFields')} valuePropName="checked" extra={t('agents.install.updateFieldsHint')}><Switch /></Form.Item>
            <Row gutter={12}>
              <Col span={12}><Form.Item name="inventoryIntervalHours" label={t('agents.install.interval')}><InputNumber min={1} max={168} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={12}><Form.Item name="staleAfterDays" label={t('agents.install.staleDays')}><InputNumber min={1} max={365} style={{ width: '100%' }} /></Form.Item></Col>
            </Row>
            <Button type="primary" htmlType="submit" loading={save.isPending}>{t('common.save')}</Button>
          </Form>
        </Card>
      </Col>
    </Row>
  );
}

export default function AgentsPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'devices';
  const summary = useQuery<AgentSummary>({ queryKey: ['agent-summary'], queryFn: () => get('/agents/summary') });
  const s = summary.data;
  return (
    <>
      <PageHeader title={t('menu.agents')} subtitle={t('agents.hint')} crumbs={[{ title: t('menu.agents') }]} />
      {s && (
        <Row gutter={12} style={{ marginBottom: 16 }}>
          {([['total', s.total], ['linked', s.linked], ['new', s.new], ['stale', s.stale], ['reportedToday', s.reportedToday]] as const).map(([k, v]) => (
            <Col xs={12} md={4} key={k}><Card size="small"><Statistic title={t(`agents.summary.${k}`)} value={v} valueStyle={k === 'stale' && v > 0 ? { color: '#e34948' } : undefined} /></Card></Col>
          ))}
        </Row>
      )}
      {s && s.total === 0 && can('agents.manage') && tab !== 'install' && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t('agents.empty')} action={<Button onClick={() => setParams({ tab: 'install' })}>{t('agents.tabs.install')}</Button>} />
      )}
      <Tabs activeKey={tab} onChange={(k) => setParams({ tab: k })} destroyOnHidden items={[
        { key: 'devices', label: t('agents.tabs.devices'), children: <Devices /> },
        { key: 'software', label: t('agents.tabs.software'), children: <SoftwareTab /> },
        ...(can('agents.manage') ? [{ key: 'install', label: t('agents.tabs.install'), children: <InstallTab /> }] : []),
      ]} />
    </>
  );
}
