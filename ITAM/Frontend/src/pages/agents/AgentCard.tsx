import { Alert, Button, Card, Col, Descriptions, Form, Input, Modal, Popconfirm, Row, Skeleton, Space, Table, Tabs, Typography } from 'antd';
import { DeleteOutlined, DisconnectOutlined, LinkOutlined, PlusOutlined, StopOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { del, get, post } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import { PageHeader } from '@/components/PageHeader';
import { AssetSelect, LookupSelect } from '@/components/Selects';
import { fmtDate, fmtDateTime } from '@/utils/format';
import { AgentStatusTag, LastSeen } from './AgentsPage';
import { ramGb, type AgentDevice, type DiscoveredSoftware } from './types';

/** Warning when the person working on the computer is not the one the asset is issued to (or the asset is not issued). */
export function UserMismatchAlert({ d }: { d: AgentDevice }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  if (!d.assetId || !d.currentEmployeeId) return null;
  if (d.userMismatch) {
    return (
      <Alert type="warning" showIcon style={{ marginBottom: 16 }}
        message={t('agents.mismatch', { user: d.currentEmployeeName, holder: d.assetEmployeeName })}
        action={can('assets.transfer') && <Link to={`/operations/transfer?assetIds=${d.assetId}`}><Button size="small">{t('assets.actions.transfer')}</Button></Link>} />
    );
  }
  if (!d.assetEmployeeId) {
    return (
      <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t('agents.notIssued', { user: d.currentEmployeeName })}
        action={can('assets.assign') && <Link to={`/operations/issue?assetIds=${d.assetId}&employeeId=${d.currentEmployeeId}`}><Button size="small">{t('assets.actions.issue')}</Button></Link>} />
    );
  }
  return null;
}

export function HardwareDescriptions({ d, column = 2 }: { d: AgentDevice; column?: number }) {
  const { t } = useTranslation();
  return (
    <Descriptions bordered size="small" column={{ xs: 1, sm: 1, md: column, lg: column, xl: column, xxl: column }}>
      <Descriptions.Item label={t('agents.hostname')}><b>{d.hostname}</b>{d.domain && <span className="itam-muted"> · {d.domain}</span>}</Descriptions.Item>
      <Descriptions.Item label={t('agents.currentUser')}>
        {d.currentEmployeeId ? <Link to={`/employees/${d.currentEmployeeId}`}>{d.currentEmployeeName}</Link> : null} <span className="itam-muted">{d.currentUser}</span>
      </Descriptions.Item>
      <Descriptions.Item label={t('assets.model')}>{[d.manufacturer, d.model].filter(Boolean).join(' ')}</Descriptions.Item>
      <Descriptions.Item label={t('assets.serialNumber')}><span className="itam-mono">{d.serialNumber}</span></Descriptions.Item>
      <Descriptions.Item label={t('agents.cpu')}>{d.cpu}{d.cpuCores ? ` (${d.cpuCores} ${t('agents.cores')})` : ''}</Descriptions.Item>
      <Descriptions.Item label={t('agents.ram')}>{ramGb(d.ramMb, t('agents.gb'))}</Descriptions.Item>
      <Descriptions.Item label={t('agents.os')}>{d.osName} {d.osVersion} <span className="itam-muted">{d.osBuild} {d.osArchitecture}</span></Descriptions.Item>
      <Descriptions.Item label={t('agents.storage')}>{d.storageGb ? `${d.storageGb} ${t('agents.gb')}` : ''}</Descriptions.Item>
      <Descriptions.Item label="IP / MAC"><span className="itam-mono">{d.ipAddress} {d.macAddress && `· ${d.macAddress}`}</span></Descriptions.Item>
      <Descriptions.Item label={t('agents.antivirus')}>{d.antivirus}</Descriptions.Item>
      <Descriptions.Item label={t('agents.formFactor')}>{d.formFactor && t(`agents.ff.${d.formFactor}`, { defaultValue: d.formFactor })}</Descriptions.Item>
      <Descriptions.Item label={t('agents.lastSeen')}><LastSeen at={d.lastSeenAt} stale={d.isStale} /></Descriptions.Item>
    </Descriptions>
  );
}

export default function AgentCard() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [linking, setLinking] = useState(false);
  const [creating, setCreating] = useState(false);
  const [swSearch, setSwSearch] = useState('');
  const [linkForm] = Form.useForm();
  const [createForm] = Form.useForm();
  const createRegion = Form.useWatch('regionId', createForm);
  const q = useQuery<AgentDevice>({ queryKey: ['agent', id], queryFn: () => get(`/agents/${id}`) });
  const sw = useQuery<DiscoveredSoftware[]>({ queryKey: ['agent-sw', id], queryFn: () => get(`/agents/${id}/software`) });
  const invalidate = [['agent', id], ['agents'], ['agent-summary']];
  const link = useApiMutation((v: { assetId: string }) => post(`/agents/${id}/link`, v), { invalidate, onSuccess: () => setLinking(false) });
  const unlink = useApiMutation(() => post(`/agents/${id}/unlink`), { invalidate });
  const create = useApiMutation((v: any) => post(`/agents/${id}/create-asset`, v), { invalidate, onSuccess: () => setCreating(false) });
  const ignore = useApiMutation((ignored: boolean) => post(`/agents/${id}/ignore?ignored=${ignored}`), { invalidate });
  const remove = useApiMutation(() => del(`/agents/${id}`), { invalidate: [['agents'], ['agent-summary']], onSuccess: () => navigate('/agents') });
  const software = useMemo(() => {
    const s = swSearch.trim().toLowerCase();
    return (sw.data ?? []).filter((x) => !s || x.name.toLowerCase().includes(s) || (x.publisher ?? '').toLowerCase().includes(s));
  }, [sw.data, swSearch]);

  if (q.isLoading || !q.data) return <Skeleton active />;
  const d = q.data;
  const manage = can('agents.manage');
  const data = d.data ?? {};
  return (
    <>
      <PageHeader crumbs={[{ title: t('menu.agents'), to: '/agents' }, { title: d.hostname }]} title={d.hostname} tags={<AgentStatusTag status={d.status} />}
        subtitle={[d.manufacturer, d.model, d.osName].filter(Boolean).join(' · ')}
        extra={manage && <>
          {!d.assetId && <Button icon={<LinkOutlined />} onClick={() => { linkForm.resetFields(); setLinking(true); }}>{t('agents.link')}</Button>}
          {!d.assetId && can('assets.create') && <Button type="primary" icon={<PlusOutlined />} onClick={() => { createForm.resetFields(); setCreating(true); }}>{t('agents.createAsset')}</Button>}
          {d.assetId && <Popconfirm title={t('agents.unlinkConfirm')} onConfirm={() => unlink.mutate(undefined)}><Button icon={<DisconnectOutlined />}>{t('agents.unlink')}</Button></Popconfirm>}
          {!d.assetId && d.status !== 'Ignored' && <Button icon={<StopOutlined />} onClick={() => ignore.mutate(true)}>{t('agents.ignore')}</Button>}
          {d.status === 'Ignored' && <Button onClick={() => ignore.mutate(false)}>{t('agents.unignore')}</Button>}
          <Popconfirm title={t('agents.deleteConfirm')} description={t('agents.deleteHint')} onConfirm={() => remove.mutate(undefined)}>
            <Button danger icon={<DeleteOutlined />}>{t('common.delete')}</Button>
          </Popconfirm>
        </>} />
      {d.comment && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message={t('agents.linkProblem')} description={d.comment} />}
      {d.assetId
        ? <Alert type="success" showIcon style={{ marginBottom: 16 }} message={<>{t('agents.linkedTo')} <Link to={`/assets/${d.assetId}`}><b>{d.assetNumber}</b> {d.assetName}</Link>
            {d.assetEmployeeName && <> · {t('agents.issuedTo')} <Link to={`/employees/${d.assetEmployeeId}`}>{d.assetEmployeeName}</Link></>}</>} />
        : d.status === 'New' && <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t('agents.newHint')} />}
      <UserMismatchAlert d={d} />
      <Tabs items={[
        { key: 'hw', label: t('agents.tabs.hardware'), children: (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card><HardwareDescriptions d={d} /></Card>
            <Row gutter={16}>
              <Col xs={24} xl={12}>
                <Card size="small" title={t('agents.disks')}>
                  <Table size="small" pagination={false} rowKey={(_, i) => String(i)} dataSource={data.disks ?? []}
                    columns={[{ title: t('assets.model'), dataIndex: 'model' }, { title: t('agents.type'), dataIndex: 'mediaType' },
                      { title: t('agents.size'), dataIndex: 'sizeGb', render: (v) => v && `${v} ${t('agents.gb')}` }, { title: t('assets.serialNumber'), dataIndex: 'serialNumber' }]} />
                  <Table size="small" pagination={false} style={{ marginTop: 12 }} rowKey={(_, i) => String(i)} dataSource={data.volumes ?? []}
                    columns={[{ title: t('agents.volume'), dataIndex: 'drive' }, { title: t('agents.size'), dataIndex: 'sizeGb', render: (v) => `${v} ${t('agents.gb')}` },
                      { title: t('agents.free'), dataIndex: 'freeGb', render: (v, r: any) => <span style={r.sizeGb && v / r.sizeGb < 0.1 ? { color: '#e34948' } : undefined}>{v} {t('agents.gb')}</span> },
                      { title: 'FS', dataIndex: 'fileSystem' }]} />
                </Card>
              </Col>
              <Col xs={24} xl={12}>
                <Card size="small" title={t('agents.network')}>
                  <Table size="small" pagination={false} rowKey={(_, i) => String(i)} dataSource={data.network ?? []}
                    columns={[{ title: t('agents.adapter'), dataIndex: 'name' }, { title: 'MAC', dataIndex: 'macAddress', render: (v) => <span className="itam-mono">{v}</span> },
                      { title: 'IP', dataIndex: 'ip', render: (v: string[]) => <span className="itam-mono">{(v ?? []).join(', ')}</span> }, { title: 'DHCP', dataIndex: 'dhcp', render: (v) => (v ? t('common.yes') : t('common.no')) }]} />
                </Card>
                <Card size="small" title={t('agents.peripherals')} style={{ marginTop: 16 }}>
                  <Descriptions size="small" column={1}>
                    <Descriptions.Item label={t('agents.monitors')}>
                      <Space direction="vertical" size={0}>{(data.monitors ?? []).map((m, i) => <span key={i}>{[m.manufacturer, m.model].filter(Boolean).join(' ')} <span className="itam-muted itam-mono">{m.serialNumber}</span></span>)}</Space>
                    </Descriptions.Item>
                    <Descriptions.Item label={t('agents.gpu')}>{(data.gpus ?? []).join(', ')}</Descriptions.Item>
                    <Descriptions.Item label={t('agents.printers')}>{(data.printers ?? []).join(', ')}</Descriptions.Item>
                  </Descriptions>
                </Card>
              </Col>
            </Row>
            <Card size="small" title={t('agents.system')}>
              <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }}>
                <Descriptions.Item label={t('agents.osInstalled')}>{fmtDate(d.osInstallDate)}</Descriptions.Item>
                <Descriptions.Item label={t('agents.lastBoot')}>{fmtDateTime(d.lastBootAt)}</Descriptions.Item>
                <Descriptions.Item label="BIOS">{d.biosVersion}</Descriptions.Item>
                <Descriptions.Item label="UUID"><span className="itam-mono">{d.hardwareUuid}</span></Descriptions.Item>
                <Descriptions.Item label={t('agents.agentVersion')}>{d.agentVersion}</Descriptions.Item>
                <Descriptions.Item label={t('agents.registeredAt')}>{fmtDateTime(d.registeredAt)}</Descriptions.Item>
                <Descriptions.Item label={t('agents.lastIp')}><span className="itam-mono">{d.lastIp}</span></Descriptions.Item>
              </Descriptions>
            </Card>
          </Space>
        ) },
        { key: 'sw', label: `${t('agents.tabs.software')} (${d.softwareCount})`, children: (
          <Card>
            <Input.Search allowClear placeholder={t('agents.softwareSearch')} style={{ width: 320, marginBottom: 12 }} onChange={(e) => setSwSearch(e.target.value)} />
            <Table<DiscoveredSoftware> rowKey="id" size="small" loading={sw.isLoading} dataSource={software} pagination={{ pageSize: 50, showSizeChanger: false }}
              columns={[
                { title: t('common.name'), dataIndex: 'name', sorter: (a, b) => a.name.localeCompare(b.name), defaultSortOrder: 'ascend' },
                { title: t('agents.version'), dataIndex: 'version' },
                { title: t('agents.publisher'), dataIndex: 'publisher', sorter: (a, b) => (a.publisher ?? '').localeCompare(b.publisher ?? '') },
                { title: t('agents.installedAt'), dataIndex: 'installDate', render: fmtDate },
              ]} />
          </Card>
        ) },
      ]} />
      <Modal open={linking} title={t('agents.link')} onCancel={() => setLinking(false)} onOk={() => linkForm.submit()} confirmLoading={link.isPending}>
        <Typography.Paragraph type="secondary">{t('agents.linkHint')}</Typography.Paragraph>
        <Form form={linkForm} layout="vertical" onFinish={(v) => link.mutate(v)}>
          <Form.Item name="assetId" label={t('agents.asset')} rules={[{ required: true }]}><AssetSelect /></Form.Item>
        </Form>
      </Modal>
      <Modal open={creating} title={t('agents.createAsset')} onCancel={() => setCreating(false)} onOk={() => createForm.submit()} confirmLoading={create.isPending}>
        <Typography.Paragraph type="secondary">{t('agents.createHint')}</Typography.Paragraph>
        <Form form={createForm} layout="vertical" onFinish={(v) => create.mutate(v)}>
          <Form.Item name="assetTypeId" label={t('assets.type')} extra={t('agents.typeAuto')}><LookupSelect lookup="asset-types" /></Form.Item>
          <Form.Item name="regionId" label={t('common.region')} rules={[{ required: true }]}><LookupSelect lookup="regions" /></Form.Item>
          <Form.Item name="locationId" label={t('assets.location')}><LookupSelect lookup="locations" filter={(l) => !createRegion || l.regionId === createRegion} /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
