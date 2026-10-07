import { Button, Table } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useQueries } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { get } from '@/api/client';
import type { Asset } from '@/api/types';
import { AssetSelect } from './Selects';
import { StatusTag } from './Tags';

/** Multi-asset picker for acts: search & add, table of selected assets with current status/holder. */
export function AssetPicker({ value = [], onChange, filters }: { value?: string[]; onChange?: (v: string[]) => void; filters?: Record<string, unknown> }) {
  const { t } = useTranslation();
  const results = useQueries({ queries: value.map((id) => ({ queryKey: ['asset', id], queryFn: () => get<Asset>(`/assets/${id}`) })) });
  const rows = results.map((r, i) => r.data ?? ({ id: value[i], inventoryNumber: '…', name: '' } as Asset));
  return (
    <>
      <AssetSelect filters={filters} value={null} style={{ width: '100%', marginBottom: 8 }} onChange={(id: string) => id && !value.includes(id) && onChange?.([...value, id])} />
      <Table<Asset> rowKey="id" size="small" pagination={false} dataSource={rows} locale={{ emptyText: t('operations.noAssets') }}
        columns={[
          { title: t('assets.inventoryNumber'), dataIndex: 'inventoryNumber', render: (v) => <span className="itam-mono">{v}</span> },
          { title: t('assets.name'), dataIndex: 'name' },
          { title: t('assets.serialNumber'), dataIndex: 'serialNumber' },
          { title: t('common.status'), dataIndex: 'statusName', render: (v, r) => <StatusTag name={v} color={r.statusColor} /> },
          { title: t('assets.employee'), dataIndex: 'employeeName' },
          { title: t('assets.location'), dataIndex: 'locationName' },
          { key: 'x', width: 48, render: (_, r) => <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => onChange?.(value.filter((v) => v !== r.id))} /> },
        ]} />
    </>
  );
}
