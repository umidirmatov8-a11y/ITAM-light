import { Alert, Button, Card, Col, Input, Modal, Row, Segmented, Select, Skeleton, Space, Statistic, Table, Tag } from 'antd';
import { CameraOutlined, ScanOutlined } from '@ant-design/icons';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post, put, type Paged } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import { DocumentsTable, GenerateDocumentButton } from '@/components/Documents';
import { PageHeader } from '@/components/PageHeader';
import { LookupSelect } from '@/components/Selects';
import { EnumTag } from '@/components/Tags';
import { INVENTORY_RESULTS } from '@/utils/enums';
import { fmtDateTime } from '@/utils/format';
import type { Campaign } from './InventoryPage';

interface Item { id: string; assetId: string; inventoryNumber: string; assetName: string; serialNumber?: string; expectedLocation?: string; expectedEmployee?: string; foundLocation?: string; result: string; checkedAt?: string; checkedByName?: string; comment?: string }

/** Camera QR scanner (html5-qrcode, loaded on demand). */
function CameraScanner({ onScan, onClose }: { onScan: (code: string) => void; onClose: () => void }) {
  const ref = useRef<any>(null);
  const { t } = useTranslation();
  const [error, setError] = useState<string>();
  useEffect(() => {
    let stopped = false;
    import('html5-qrcode').then(({ Html5Qrcode }) => {
      if (stopped) return;
      const scanner = new Html5Qrcode('itam-qr-reader');
      ref.current = scanner;
      let last = '';
      scanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: 240 }, (text) => {
        if (text !== last) { last = text; onScan(text); setTimeout(() => (last = ''), 2500); }
      }, () => undefined).catch((e: unknown) => setError(String(e)));
    });
    return () => { stopped = true; ref.current?.stop?.().catch(() => undefined); };
  }, [onScan]);
  return (
    <Modal open onCancel={onClose} footer={null} title={t('inventory.camera')} destroyOnHidden>
      {error && <Alert type="error" message={t('inventory.cameraError')} description={error} />}
      <div id="itam-qr-reader" style={{ width: '100%' }} />
    </Modal>
  );
}

export default function InventoryCard() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can } = useAuth();
  const notify = useNotify();
  const [code, setCode] = useState('');
  const [foundLocationId, setFoundLocationId] = useState<string>();
  const [result, setResult] = useState<string>();
  const [page, setPage] = useState(1);
  const [camera, setCamera] = useState(false);
  const [lastScan, setLastScan] = useState<Item>();
  const c = useQuery<Campaign>({ queryKey: ['inventory-campaign', id], queryFn: () => get(`/inventory/${id}`) });
  const items = useQuery<Paged<Item>>({ queryKey: ['inventory-items', id, result, page], queryFn: () => get(`/inventory/${id}/items`, { result, page, pageSize: 50 }), placeholderData: keepPreviousData });
  const invalidate = [['inventory-campaign', id], ['inventory-items', id]];
  const scan = useApiMutation((v: string) => post<Item>(`/inventory/${id}/scan`, { code: v, foundLocationId }), { invalidate, success: false, onSuccess: (r) => { setLastScan(r); setCode(''); } });
  const update = useApiMutation((v: { itemId: string; result: string }) => put(`/inventory/${id}/items/${v.itemId}`, { result: v.result }), { invalidate, success: false });
  const complete = useApiMutation(() => post(`/inventory/${id}/complete`), { invalidate });
  if (c.isLoading || !c.data) return <Skeleton active />;
  const camp = c.data;
  const active = camp.status === 'InProgress' && can('inventory.manage');
  return (
    <>
      <PageHeader crumbs={[{ title: t('menu.inventory'), to: '/inventory' }, { title: camp.number }]} title={`${camp.number} — ${camp.name}`} tags={<EnumTag group="inventoryStatus" value={camp.status} />}
        subtitle={[camp.regionName, camp.locationName].filter(Boolean).join(' · ')}
        extra={<>
          {active && <Button type="primary" onClick={() => Modal.confirm({ title: t('inventory.completeConfirm'), content: t('inventory.completeHint'), onOk: () => complete.mutateAsync(undefined) })}>{t('inventory.complete')}</Button>}
          <GenerateDocumentButton sourceType="InventoryCampaign" sourceId={camp.id} documentType="InventoryAct" />
        </>} />
      <Row gutter={12} style={{ marginBottom: 16 }}>
        {(['total', 'checked', 'found', 'misplaced', 'missing', 'unexpected'] as const).map((k) => (
          <Col xs={12} md={4} key={k}><Card size="small"><Statistic title={t(`inventory.${k}`)} value={camp[k]} /></Card></Col>
        ))}
      </Row>
      {active && (
        <Card title={<Space><ScanOutlined />{t('inventory.scan')}</Space>} style={{ marginBottom: 16 }}>
          <Space wrap>
            <Input.Search autoFocus enterButton={t('inventory.check')} value={code} onChange={(e) => setCode(e.target.value)} onSearch={(v) => v && scan.mutate(v)} style={{ width: 360 }} placeholder={t('inventory.scanHint')} loading={scan.isPending} />
            <LookupSelect lookup="locations" placeholder={t('inventory.foundLocation')} style={{ width: 260 }} value={foundLocationId} onChange={setFoundLocationId} />
            <Button icon={<CameraOutlined />} onClick={() => setCamera(true)}>{t('inventory.camera')}</Button>
          </Space>
          {lastScan && <Alert style={{ marginTop: 12 }} type={lastScan.result === 'Found' ? 'success' : 'warning'} showIcon
            message={<>{lastScan.inventoryNumber} — {lastScan.assetName}: <b>{t(`enums.inventoryResult.${lastScan.result}`)}</b></>} />}
        </Card>
      )}
      <Card>
        <Segmented style={{ marginBottom: 12 }} value={result ?? 'all'} onChange={(v) => { setResult(v === 'all' ? undefined : (v as string)); setPage(1); }}
          options={[{ value: 'all', label: t('common.all') }, ...INVENTORY_RESULTS.map((r) => ({ value: r, label: t(`enums.inventoryResult.${r}`) }))]} />
        <Table<Item> rowKey="id" size="small" loading={items.isFetching} dataSource={items.data?.items} scroll={{ x: 'max-content' }}
          pagination={{ current: page, pageSize: 50, total: items.data?.total, onChange: setPage, showSizeChanger: false }}
          columns={[
            { title: t('assets.inventoryNumber'), dataIndex: 'inventoryNumber', render: (v, r) => <Link className="itam-mono" to={`/assets/${r.assetId}`}>{v}</Link> },
            { title: t('assets.name'), dataIndex: 'assetName' },
            { title: t('assets.serialNumber'), dataIndex: 'serialNumber' },
            { title: t('inventory.expectedLocation'), dataIndex: 'expectedLocation' },
            { title: t('inventory.expectedEmployee'), dataIndex: 'expectedEmployee' },
            { title: t('inventory.foundLocation'), dataIndex: 'foundLocation' },
            { title: t('inventory.result'), dataIndex: 'result', render: (v, r) => active
              ? <Select size="small" style={{ width: 170 }} value={v} onChange={(x) => update.mutate({ itemId: r.id, result: x })} options={INVENTORY_RESULTS.map((x) => ({ value: x, label: t(`enums.inventoryResult.${x}`) }))} />
              : <Tag>{t(`enums.inventoryResult.${v}`)}</Tag> },
            { title: t('inventory.checkedAt'), render: (_, r) => r.checkedAt && <>{fmtDateTime(r.checkedAt)} <span className="itam-muted">{r.checkedByName}</span></> },
          ]} />
      </Card>
      <Card title={t('tabs.documents')} style={{ marginTop: 16 }}><DocumentsTable filter={{ sourceType: 'InventoryCampaign', sourceId: camp.id }} /></Card>
      {camera && <CameraScanner onClose={() => setCamera(false)} onScan={(v) => scan.mutateAsync(v).catch(notify.error)} />}
    </>
  );
}
