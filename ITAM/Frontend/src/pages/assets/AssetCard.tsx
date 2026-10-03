import { Alert, Button, Card, Col, DatePicker, Descriptions, Dropdown, Image, Modal, Row, Skeleton, Space, Table, Tabs, Tag, Tooltip, Typography } from 'antd';
import { EditOutlined, FieldTimeOutlined, MoreOutlined, PrinterOutlined, RollbackOutlined, SendOutlined, SwapOutlined, ToolOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, del, download, get } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { Asset, AssetEvent, BatchListItem, LicenseAssignment, RepairListItem, TimelineItem } from '@/api/types';
import { Attachments } from '@/components/Attachments';
import { AuditTable, type AuditRow } from '@/components/AuditTable';
import { CustomFieldsView } from '@/components/CustomFields';
import { DocumentsTable } from '@/components/Documents';
import { PageHeader } from '@/components/PageHeader';
import { BackdatedTag, EnumTag, StatusTag } from '@/components/Tags';
import { TimelineView } from '@/components/TimelineView';
import { fmtDate, fmtDateTime, fmtMoney, nowInTz, toApiDateTime } from '@/utils/format';
import { AssetForm } from './AssetForm';
import { RepairForm } from './RepairForm';

function useQrImage(id: string) {
  const [src, setSrc] = useState<string>();
  useEffect(() => {
    let url: string | undefined;
    api.get(`/assets/${id}/qr`, { responseType: 'blob' }).then((r) => { url = URL.createObjectURL(r.data); setSrc(url); }).catch(() => undefined);
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [id]);
  return src;
}

export default function AssetCard() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can } = useAuth();
  const navigate = useNavigate();
  const notify = useNotify();
  const [tab, setTab] = useState('overview');
  const [edit, setEdit] = useState(false);
  const [repair, setRepair] = useState(false);
  const [stateAt, setStateAt] = useState<string>();
  const qr = useQrImage(id!);
  const q = useQuery<Asset>({ queryKey: ['asset', id], queryFn: () => get(`/assets/${id}`) });
  const history = useQuery<AssetEvent[]>({ queryKey: ['asset-history', id], queryFn: () => get(`/assets/${id}/history`), enabled: tab === 'history' });
  const timeline = useQuery<TimelineItem[]>({ queryKey: ['asset-timeline', id], queryFn: () => get(`/assets/${id}/timeline`), enabled: tab === 'timeline' });
  const ops = useQuery<{ items: BatchListItem[] }>({ queryKey: ['asset-ops', id], queryFn: () => get(`/assets/${id}/operations`), enabled: tab === 'assignments' });
  const repairs = useQuery<RepairListItem[]>({ queryKey: ['asset-repairs', id], queryFn: () => get(`/assets/${id}/repairs`), enabled: tab === 'repairs' });
  const licenses = useQuery<LicenseAssignment[]>({ queryKey: ['asset-licenses', id], queryFn: () => get(`/assets/${id}/licenses`), enabled: tab === 'licenses' && can('licenses.view') });
  const audit = useQuery<AuditRow[]>({ queryKey: ['asset-audit', id], queryFn: () => get(`/assets/${id}/audit`), enabled: tab === 'audit' && can('audit.view') });
  const at = useQuery<any>({ queryKey: ['asset-at', id, stateAt], queryFn: () => get(`/assets/${id}/state-at`, { at: stateAt }), enabled: !!stateAt });
  const remove = useApiMutation(() => del(`/assets/${id}`), { onSuccess: () => navigate('/assets') });

  if (q.isLoading || !q.data) return <Skeleton active />;
  const a = q.data;
  const kind = a.statusKind;
  const terminal = ['Disposed', 'WrittenOff', 'Lost', 'Stolen', 'Archived'].includes(kind);

  const printQr = () => {
    const w = window.open('', '_blank', 'width=420,height=520');
    if (!w || !qr) return;
    w.document.write(`<html><head><title>${a.inventoryNumber}</title></head><body style="font-family:sans-serif;text-align:center">
      <img src="${qr}" style="width:260px"/><h2 style="margin:4px 0">${a.inventoryNumber}</h2><div>${a.name.replace(/</g, '&lt;')}</div>
      <div>${a.serialNumber ? 'S/N ' + a.serialNumber.replace(/</g, '&lt;') : ''}</div><script>window.onload=()=>{window.print();}</script></body></html>`);
    w.document.close();
  };

  return (
    <>
      <PageHeader
        crumbs={[{ title: t('menu.assets'), to: '/assets' }, { title: a.inventoryNumber }]}
        title={a.name}
        tags={<><StatusTag name={a.statusName} color={a.statusColor} />{a.openRepair && <Link to={`/repairs/${a.openRepair.id}`}><Tag color="orange">{a.openRepair.number}</Tag></Link>}</>}
        subtitle={<Space split="·"><span className="itam-mono">{a.inventoryNumber}</span>{a.typeName}{a.serialNumber && <span className="itam-mono">S/N {a.serialNumber}</span>}</Space>}
        extra={<>
          {can('assets.assign') && ['InStock', 'Reserved'].includes(kind) && <Button type="primary" icon={<SendOutlined />} onClick={() => navigate(`/operations/issue?assetIds=${id}`)}>{t('assets.actions.issue')}</Button>}
          {can('assets.return') && kind === 'Assigned' && <Button icon={<RollbackOutlined />} onClick={() => navigate(`/operations/return?employeeId=${a.employeeId}&assetIds=${id}`)}>{t('assets.actions.return')}</Button>}
          {can('assets.transfer') && !terminal && <Button icon={<SwapOutlined />} onClick={() => navigate(`/operations/transfer?assetIds=${id}`)}>{t('assets.actions.transfer')}</Button>}
          {can('assets.repair') && !terminal && kind !== 'InRepair' && <Button icon={<ToolOutlined />} onClick={() => setRepair(true)}>{t('assets.actions.repair')}</Button>}
          {can('assets.edit') && <Button icon={<EditOutlined />} onClick={() => setEdit(true)}>{t('common.edit')}</Button>}
          <Button icon={<PrinterOutlined />} onClick={printQr}>{t('assets.printQr')}</Button>
          <Dropdown menu={{ items: [
            can('assets.status') && { key: 'status', label: t('assets.actions.status'), onClick: () => navigate(`/operations/status?assetIds=${id}`) },
            { key: 'label', label: t('assets.printLabel'), onClick: () => download('/assets/labels', undefined, 'post', { assetIds: [id] }).catch(notify.error) },
            { key: 'qr', label: t('assets.downloadQr'), onClick: () => download(`/assets/${id}/qr`).catch(notify.error) },
            can('assets.delete') && { key: 'del', danger: true, label: t('common.delete'), onClick: () => Modal.confirm({ title: t('assets.deleteConfirm'), content: t('assets.deleteHint'), onOk: () => remove.mutateAsync(undefined) }) },
          ].filter(Boolean) as never }}>
            <Button icon={<MoreOutlined />} />
          </Dropdown>
        </>}
      />
      <Tabs activeKey={tab} onChange={setTab} items={[
        {
          key: 'overview', label: t('tabs.overview'), children: (
            <Row gutter={16}>
              <Col xs={24} xl={17}>
                <Card>
                  <div className="itam-asset-hero">
                    <Descriptions bordered size="small" column={{ xs: 1, sm: 1, md: 2, lg: 2, xl: 2, xxl: 3 }}>
                      <Descriptions.Item label={t('assets.inventoryNumber')}><span className="itam-mono">{a.inventoryNumber}</span></Descriptions.Item>
                      <Descriptions.Item label={t('assets.serialNumber')}><span className="itam-mono">{a.serialNumber}</span></Descriptions.Item>
                      <Descriptions.Item label={t('assets.type')}>{a.typeName}{a.categoryName && <span className="itam-muted"> / {a.categoryName}</span>}</Descriptions.Item>
                      <Descriptions.Item label={t('assets.model')}>{[a.manufacturerName, a.model].filter(Boolean).join(' ')}</Descriptions.Item>
                      <Descriptions.Item label={t('common.status')}><StatusTag name={a.statusName} color={a.statusColor} /></Descriptions.Item>
                      <Descriptions.Item label={t('assets.employee')}>{a.employeeId ? <Link to={`/employees/${a.employeeId}`}>{a.employeeName}</Link> : <span className="itam-muted">—</span>}</Descriptions.Item>
                      <Descriptions.Item label={t('common.department')}>{a.departmentName}</Descriptions.Item>
                      <Descriptions.Item label={t('common.region')}>{a.regionName}</Descriptions.Item>
                      <Descriptions.Item label={t('assets.location')}>{a.locationName}</Descriptions.Item>
                      <Descriptions.Item label={t('assets.responsible')}>{a.responsibleEmployeeId ? <Link to={`/employees/${a.responsibleEmployeeId}`}>{a.responsibleName}</Link> : <Tag color="gold">{t('assets.noResponsible')}</Tag>}</Descriptions.Item>
                      <Descriptions.Item label={t('assets.warranty')}>{a.warrantyExpiration ? <>{t('assets.until', { date: fmtDate(a.warrantyExpiration) })}</> : null}</Descriptions.Item>
                      <Descriptions.Item label={t('assets.condition')}><EnumTag group="condition" value={a.condition} /></Descriptions.Item>
                      {a.currentAssignment && <Descriptions.Item label={t('assets.assignedSince')}>
                        <Link to={`/operations/${a.currentAssignment.batchId}`}>{a.currentAssignment.batchNumber}</Link> · {fmtDateTime(a.currentAssignment.effectiveFrom)}
                        {a.currentAssignment.expectedReturnDate && <Tag color="gold" style={{ marginLeft: 6 }}>{t('assets.returnBy', { date: fmtDate(a.currentAssignment.expectedReturnDate) })}</Tag>}
                      </Descriptions.Item>}
                      {a.parentAssetId && <Descriptions.Item label={t('assets.parent')}><Link to={`/assets/${a.parentAssetId}`}>{a.parentAssetNumber}</Link></Descriptions.Item>}
                      <Descriptions.Item label="Hostname / IP / MAC"><span className="itam-mono">{[a.hostname, a.ipAddress, a.macAddress].filter(Boolean).join(' · ')}</span></Descriptions.Item>
                      <Descriptions.Item label={t('assets.lastInventory')}>{fmtDateTime(a.lastInventoryAt)}</Descriptions.Item>
                      <Descriptions.Item label={t('common.comment')} span={2}>{a.notes}</Descriptions.Item>
                    </Descriptions>
                  </div>
                  <CustomFieldsView entity="Asset" assetTypeId={a.assetTypeId} values={a.customFields} />
                  {a.components.length > 0 && (
                    <Card size="small" title={t('assets.components')} style={{ marginTop: 16 }}>
                      {a.components.map((c) => <Tag key={c.id}><Link to={`/assets/${c.id}`}>{c.inventoryNumber}</Link> {c.name}</Tag>)}
                    </Card>
                  )}
                </Card>
              </Col>
              <Col xs={24} xl={7}>
                <Space direction="vertical" style={{ width: '100%' }} size={16}>
                  <Card size="small" title="QR" style={{ textAlign: 'center' }}>
                    {qr && <Image src={qr} className="itam-qr" preview={false} />}
                    <div className="itam-mono" style={{ marginTop: 6 }}>{a.inventoryNumber}</div>
                    <img alt="barcode" style={{ maxWidth: '100%', marginTop: 8, background: '#fff' }} src={`/api/assets/${id}/barcode`} />
                  </Card>
                  <Card size="small" title={t('assets.finance')}>
                    <Descriptions size="small" column={1}>
                      <Descriptions.Item label={t('assets.purchaseDate')}>{fmtDate(a.purchaseDate)}</Descriptions.Item>
                      {a.purchasePrice != null && <Descriptions.Item label={t('assets.price')}>{fmtMoney(a.purchasePrice, a.currency)}</Descriptions.Item>}
                      <Descriptions.Item label={t('assets.supplier')}>{a.supplierName}</Descriptions.Item>
                      <Descriptions.Item label={t('assets.invoice')}>{a.invoiceNumber}</Descriptions.Item>
                      <Descriptions.Item label={t('assets.contract')}>{a.contractNumber}</Descriptions.Item>
                      {a.depreciation && <>
                        <Descriptions.Item label={t('assets.bookValue')}><b>{fmtMoney(a.depreciation.bookValue, a.currency)}</b></Descriptions.Item>
                        <Descriptions.Item label={t('assets.accumulated')}>{fmtMoney(a.depreciation.accumulated, a.currency)}</Descriptions.Item>
                        <Descriptions.Item label={t('assets.monthly')}>{fmtMoney(a.depreciation.monthlyAmount, a.currency)}</Descriptions.Item>
                        <Descriptions.Item label={t('assets.fullyDepreciated')}>{fmtDate(a.depreciation.fullyDepreciatedOn)}</Descriptions.Item>
                      </>}
                    </Descriptions>
                  </Card>
                  <Card size="small" title={<Space><FieldTimeOutlined />{t('assets.stateAt')}</Space>}>
                    <DatePicker showTime format="DD.MM.YYYY HH:mm" style={{ width: '100%' }} defaultValue={nowInTz()} onChange={(d) => setStateAt(toApiDateTime(d))} />
                    {at.data && (
                      <Descriptions size="small" column={1} style={{ marginTop: 8 }}>
                        <Descriptions.Item label={t('common.status')}>{at.data.statusName ?? t('assets.notRegistered')}</Descriptions.Item>
                        <Descriptions.Item label={t('assets.employee')}>{at.data.employeeName ?? '—'}</Descriptions.Item>
                        <Descriptions.Item label={t('assets.location')}>{at.data.locationName}</Descriptions.Item>
                        <Descriptions.Item label={t('common.region')}>{at.data.regionName}</Descriptions.Item>
                      </Descriptions>
                    )}
                  </Card>
                </Space>
              </Col>
            </Row>
          ),
        },
        { key: 'timeline', label: t('tabs.timeline'), children: <Card><TimelineView items={timeline.data} /></Card> },
        {
          key: 'history', label: t('tabs.history'), children: (
            <>
              <Alert type="info" showIcon message={t('assets.historyHint')} style={{ marginBottom: 12 }} />
              <Table<AssetEvent> rowKey="id" size="small" loading={history.isLoading} dataSource={history.data} pagination={{ pageSize: 50 }} scroll={{ x: 'max-content' }}
                rowClassName={(r) => (r.isCancelled ? 'itam-cancelled' : '')}
                columns={[
                  { title: t('operations.effectiveAt'), dataIndex: 'effectiveAt', render: (v, r) => <Space size={4}><span className="itam-mono">{fmtDateTime(v)}</span><BackdatedTag show={r.isBackdated} /></Space> },
                  { title: t('common.recordedAt'), dataIndex: 'recordedAt', render: (v) => <span className="itam-mono itam-muted">{fmtDateTime(v)}</span> },
                  { title: t('assets.event'), dataIndex: 'eventType', render: (v) => <Tag>{t(`enums.eventType.${v}`, { defaultValue: v })}</Tag> },
                  { title: t('common.description'), dataIndex: 'description', render: (v, r) => r.batchId ? <Link to={`/operations/${r.batchId}`}>{v}</Link> : v },
                  { title: t('assets.stateAfter'), render: (_, r) => r.affectsState && <Space size={2} wrap>{r.statusName && <Tag>{r.statusName}</Tag>}{r.employeeName}{r.locationName && <span className="itam-muted">{r.locationName}</span>}</Space> },
                  { title: t('common.recordedBy'), dataIndex: 'recordedByName' },
                  { title: t('common.cancelled'), dataIndex: 'cancelReason', render: (v, r) => r.isCancelled && <Tooltip title={v}><Tag>{t('common.cancelled')}</Tag></Tooltip> },
                ]} />
            </>
          ),
        },
        {
          key: 'assignments', label: t('tabs.operations'), children: (
            <Table<BatchListItem> rowKey="id" size="small" loading={ops.isLoading} dataSource={ops.data?.items} pagination={false}
              columns={[
                { title: t('operations.number'), dataIndex: 'number', render: (v, r) => <Link to={`/operations/${r.id}`} className={r.isCancelled ? 'itam-cancelled' : undefined}>{v}</Link> },
                { title: t('operations.type'), dataIndex: 'type', render: (v) => <EnumTag group="operation" value={v} /> },
                { title: t('operations.effectiveAt'), dataIndex: 'effectiveAt', render: (v, r) => <Space>{fmtDateTime(v)}<BackdatedTag show={r.isBackdated} /></Space> },
                { title: t('common.recordedAt'), dataIndex: 'recordedAt', render: fmtDateTime },
                { title: t('operations.employee'), dataIndex: 'employeeName' },
                { title: t('documents.employeeSignature'), dataIndex: 'employeeSignatureStatus', render: (v) => <EnumTag group="signature" value={v} /> },
              ]} />
          ),
        },
        {
          key: 'repairs', label: t('menu.repairs'), children: (
            <Table<RepairListItem> rowKey="id" size="small" loading={repairs.isLoading} dataSource={repairs.data} pagination={false}
              columns={[
                { title: t('repairs.number'), dataIndex: 'number', render: (v, r) => <Link to={`/repairs/${r.id}`}>{v}</Link> },
                { title: t('common.status'), dataIndex: 'statusName', render: (v, r) => <StatusTag name={v} color={r.statusColor} /> },
                { title: t('repairs.openedAt'), dataIndex: 'openedAt', render: fmtDateTime },
                { title: t('repairs.problem'), dataIndex: 'problem' },
                { title: t('repairs.serviceCenter'), dataIndex: 'serviceCenterName' },
                { title: t('repairs.cost'), dataIndex: 'cost', render: (v, r) => fmtMoney(v, r.currency) },
              ]} />
          ),
        },
        can('documents.view') && { key: 'documents', label: t('tabs.documents'), children: <DocumentsTable filter={{ assetId: id }} /> },
        can('licenses.view') && {
          key: 'licenses', label: t('menu.licenses'), children: (
            <Table<LicenseAssignment> rowKey="id" size="small" dataSource={licenses.data} pagination={false}
              columns={[
                { title: t('licenses.license'), dataIndex: 'licenseName', render: (v, r) => <Link to={`/licenses/${r.licenseId}`}>{v}</Link> },
                { title: t('licenses.software'), dataIndex: 'softwareName' },
                { title: t('licenses.employee'), dataIndex: 'employeeName' },
                { title: t('licenses.assignedAt'), dataIndex: 'assignedAt', render: fmtDateTime },
                { title: t('licenses.revokedAt'), dataIndex: 'revokedAt', render: fmtDateTime },
              ]} />
          ),
        },
        { key: 'files', label: t('tabs.attachments'), children: <Attachments entityType="Asset" entityId={a.id} /> },
        can('audit.view') && { key: 'audit', label: t('tabs.audit'), children: <AuditTable rows={audit.data} loading={audit.isLoading} /> },
      ].filter(Boolean) as never} />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('common.createdAt')}: {fmtDateTime(a.createdAt)} · {t('common.updatedAt')}: {fmtDateTime(a.updatedAt)}</Typography.Text>
      <AssetForm open={edit} asset={a} onClose={() => setEdit(false)} />
      <RepairForm open={repair} assetId={a.id} onClose={() => setRepair(false)} onSaved={(r) => navigate(`/repairs/${r.id}`)} />
    </>
  );
}
