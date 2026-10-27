import { Button, Card, Col, Dropdown, Empty, Row, Select, Skeleton, Space, Statistic, Table, Tag, Typography } from 'antd';
import { DeleteOutlined, ImportOutlined, ShopOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get } from '@/api/client';
import { useAuth } from '@/app/auth';
import type { AssetListItem, Warehouse, WarehouseStockRow } from '@/api/types';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect, LookupSelect } from '@/components/Selects';
import { StatusTag } from '@/components/Tags';
import { ASSET_KINDS } from '@/utils/enums';
import { fmtDate, fmtMoney } from '@/utils/format';

/**
 * Equipment warehouse: the shared warehouse (visible to every region) and regional warehouses. Shows the stock by type and the
 * assets stored there; receipt (приход), issue, transfer and write-off start from here.
 */
export default function WarehousePage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<string[]>([]);
  const [filters, setFilters] = useState<Record<string, unknown>>({ statusKind: 'InStock' });
  const warehouses = useQuery<Warehouse[]>({ queryKey: ['warehouses'], queryFn: () => get('/assets/warehouses') });
  const current = useMemo(() => {
    const list = warehouses.data ?? [];
    return list.find((w) => w.id === params.get('id')) ?? list.find((w) => w.isShared) ?? list[0];
  }, [warehouses.data, params]);
  const stock = useQuery<WarehouseStockRow[]>({
    queryKey: ['warehouse-stock', current?.id], queryFn: () => get(`/assets/warehouses/${current!.id}/stock`), enabled: !!current,
  });
  const set = (k: string) => (v: unknown) => setFilters((f) => ({ ...f, [k]: v }));
  const go = (path: string) => navigate(`${path}?assetIds=${selected.join(',')}${current ? `&locationId=${current.id}` : ''}`);

  if (warehouses.isLoading) return <Skeleton active />;
  const totals = (stock.data ?? []).reduce((a, r) => ({ inStock: a.inStock + r.inStock, reserved: a.reserved + r.reserved, inRepair: a.inRepair + r.inRepair }),
    { inStock: 0, reserved: 0, inRepair: 0 });

  const columns: DataColumn<AssetListItem>[] = [
    { key: 'inventoryNumber', title: t('assets.inventoryNumber'), dataIndex: 'inventoryNumber', sorter: true, alwaysVisible: true, render: (v, r) => <Link className="itam-mono" to={`/assets/${r.id}`}>{v}</Link> },
    { key: 'name', title: t('assets.name'), dataIndex: 'name', sorter: true },
    { key: 'typeName', title: t('assets.type'), dataIndex: 'typeName', sorter: true },
    { key: 'model', title: t('assets.model'), dataIndex: 'model', sorter: true },
    { key: 'serialNumber', title: t('assets.serialNumber'), dataIndex: 'serialNumber', sorter: true, render: (v) => <span className="itam-mono">{v}</span> },
    { key: 'statusName', title: t('common.status'), dataIndex: 'statusName', sorter: true, render: (v, r) => <StatusTag name={v} color={r.statusColor} /> },
    { key: 'locationName', title: t('assets.location'), dataIndex: 'locationName', sorter: true, hiddenByDefault: true },
    { key: 'regionName', title: t('common.region'), dataIndex: 'regionName', sorter: true, hiddenByDefault: true },
    { key: 'purchaseDate', title: t('assets.purchaseDate'), dataIndex: 'purchaseDate', sorter: true, render: fmtDate },
    { key: 'purchasePrice', title: t('assets.price'), dataIndex: 'purchasePrice', sorter: true, render: (v, r) => fmtMoney(v, r.currency), hiddenByDefault: true },
    { key: 'createdAt', title: t('warehouse.registeredAt'), dataIndex: 'createdAt', sorter: true, render: fmtDate, hiddenByDefault: true },
  ];

  return (
    <>
      <PageHeader title={t('menu.warehouse')} crumbs={[{ title: t('menu.warehouse') }]}
        extra={<Space wrap>
          {can('assets.create') && <Button type="primary" icon={<ImportOutlined />} onClick={() => navigate(`/operations/receipt${current ? `?locationId=${current.id}` : ''}`)}>{t('warehouse.receipt')}</Button>}
          {can('assets.status') && <Button danger icon={<DeleteOutlined />} onClick={() => navigate(`/operations/write-off${current ? `?locationId=${current.id}` : ''}`)}>{t('warehouse.writeOff')}</Button>}
        </Space>} />
      {!current ? <Card><Empty description={t('warehouse.noWarehouses')} /></Card> : (
        <>
          <Card style={{ marginBottom: 16 }}>
            <Row gutter={[16, 16]} align="middle">
              <Col xs={24} lg={10}>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Typography.Text type="secondary">{t('warehouse.warehouse')}</Typography.Text>
                  <Select style={{ width: '100%' }} value={current.id} onChange={(id) => { setSelected([]); setParams({ id }); }}
                    options={(warehouses.data ?? []).map((w) => ({
                      value: w.id,
                      label: <Space size={6}><ShopOutlined />{w.fullPath}{w.isShared && <Tag color="blue">{t('warehouse.shared')}</Tag>}<span className="itam-muted">· {w.inStock}</span></Space>,
                    }))} />
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {current.isShared ? t('warehouse.sharedHint') : t('warehouse.regionalHint', { region: current.regionName })}
                  </Typography.Text>
                </Space>
              </Col>
              <Col xs={8} lg={4}><Statistic title={t('warehouse.inStock')} value={totals.inStock} /></Col>
              <Col xs={8} lg={4}><Statistic title={t('warehouse.reserved')} value={totals.reserved} /></Col>
              <Col xs={8} lg={4}><Statistic title={t('warehouse.inRepair')} value={totals.inRepair} /></Col>
            </Row>
          </Card>
          <Row gutter={16}>
            <Col xs={24} xxl={6} style={{ marginBottom: 16 }}>
              <Card title={t('warehouse.byType')} size="small">
                <Table<WarehouseStockRow> rowKey="assetTypeId" size="small" pagination={false} loading={stock.isLoading} dataSource={stock.data}
                  locale={{ emptyText: t('warehouse.empty') }}
                  onRow={(r) => ({ onClick: () => setFilters((f) => ({ ...f, assetTypeId: f.assetTypeId === r.assetTypeId ? undefined : r.assetTypeId })), style: { cursor: 'pointer' } })}
                  rowClassName={(r) => (filters.assetTypeId === r.assetTypeId ? 'ant-table-row-selected' : '')}
                  columns={[
                    { title: t('assets.type'), dataIndex: 'typeName' },
                    { title: t('warehouse.inStock'), dataIndex: 'inStock', align: 'right' },
                    { title: t('warehouse.reservedShort'), dataIndex: 'reserved', align: 'right', render: (v: number) => v || '' },
                    { title: t('warehouse.inRepairShort'), dataIndex: 'inRepair', align: 'right', render: (v: number) => v || '' },
                  ]} />
              </Card>
            </Col>
            <Col xs={24} xxl={18}>
              <DataTable<AssetListItem> key={current.id} id="warehouse-assets" url="/assets" columns={columns} params={{ ...filters, locationId: current.id }}
                searchPlaceholder={t('assets.searchHint')} defaultSort={{ field: 'inventoryNumber', order: 'asc' }}
                rowSelection={{ selectedRowKeys: selected, onChange: (k) => setSelected(k as string[]), preserveSelectedRowKeys: true }}
                filters={<>
                  <EnumSelect group="assetKind" values={ASSET_KINDS} placeholder={t('common.status')} style={{ width: 160 }} value={filters.statusKind as string} onChange={set('statusKind')} />
                  <LookupSelect lookup="asset-types" placeholder={t('assets.type')} style={{ width: 170 }} value={filters.assetTypeId as string} onChange={set('assetTypeId')} />
                </>}
                toolbar={selected.length > 0 && (
                  <Dropdown menu={{ items: [
                    can('assets.assign') && { key: 'issue', label: t('assets.actions.issue'), onClick: () => go('/operations/issue') },
                    can('assets.transfer') && { key: 'transfer', label: t('assets.actions.transfer'), onClick: () => go('/operations/transfer') },
                    can('assets.status') && { key: 'status', label: t('assets.actions.status'), onClick: () => go('/operations/status') },
                    can('assets.status') && { key: 'writeoff', danger: true, label: t('warehouse.writeOff'), onClick: () => go('/operations/write-off') },
                  ].filter(Boolean) as never }}>
                    <Button>{t('bulk.actions', { count: selected.length })}</Button>
                  </Dropdown>
                )}
                onRow={(r) => ({ onDoubleClick: () => navigate(`/assets/${r.id}`) })} />
            </Col>
          </Row>
        </>
      )}
    </>
  );
}
