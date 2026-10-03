import { Button, Checkbox, DatePicker, Dropdown, Form, Input, Modal } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { download, post } from '@/api/client';
import { useApiMutation, useCustomFields, useNotify } from '@/api/hooks';
import { Can, useAuth } from '@/app/auth';
import type { AssetListItem } from '@/api/types';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, EnumSelect, LookupSelect } from '@/components/Selects';
import { StatusTag } from '@/components/Tags';
import { ASSET_KINDS } from '@/utils/enums';
import { fmtDate, fmtMoney, toApiDate, toApiDateTime } from '@/utils/format';
import { AssetForm } from './AssetForm';

export default function AssetsPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const notify = useNotify();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState<Record<string, unknown>>({
    statusKind: params.get('statusKind') ?? undefined, noResponsible: params.get('noResponsible') ?? undefined, employeeId: params.get('employeeId') ?? undefined,
  });
  const [selected, setSelected] = useState<string[]>([]);
  const [bulkStatus, setBulkStatus] = useState(false);
  const [bulkEdit, setBulkEdit] = useState(false);
  const [statusForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const cfs = useCustomFields('Asset');
  const set = (k: string) => (v: unknown) => setFilters((f) => ({ ...f, [k]: v }));

  const statusMutation = useApiMutation((v: any) => post('/operations/status', { assetIds: selected, toStatusId: v.toStatusId, reason: v.reason, effectiveAt: toApiDateTime(v.effectiveAt) }), {
    invalidate: [['assets']], onSuccess: () => { setBulkStatus(false); setSelected([]); },
  });
  const editMutation = useApiMutation((v: any) => post('/assets/bulk-edit', {
    assetIds: selected, setResponsible: v.setResponsible, responsibleEmployeeId: v.responsibleEmployeeId, setWarranty: v.setWarranty,
    warrantyExpiration: toApiDate(v.warrantyExpiration), setSupplier: v.setSupplier, supplierId: v.supplierId,
  }), { invalidate: [['assets']], onSuccess: () => { setBulkEdit(false); setSelected([]); } });

  const columns: DataColumn<AssetListItem>[] = [
    { key: 'inventoryNumber', title: t('assets.inventoryNumber'), dataIndex: 'inventoryNumber', sorter: true, alwaysVisible: true, render: (v, r) => <Link className="itam-mono" to={`/assets/${r.id}`}>{v}</Link> },
    { key: 'name', title: t('assets.name'), dataIndex: 'name', sorter: true },
    { key: 'typeName', title: t('assets.type'), dataIndex: 'typeName', sorter: true },
    { key: 'manufacturerName', title: t('assets.manufacturer'), dataIndex: 'manufacturerName', sorter: true, hiddenByDefault: true },
    { key: 'model', title: t('assets.model'), dataIndex: 'model', sorter: true, hiddenByDefault: true },
    { key: 'serialNumber', title: t('assets.serialNumber'), dataIndex: 'serialNumber', sorter: true, render: (v) => <span className="itam-mono">{v}</span> },
    { key: 'statusName', title: t('common.status'), dataIndex: 'statusName', sorter: true, render: (v, r) => <StatusTag name={v} color={r.statusColor} /> },
    { key: 'employeeName', title: t('assets.employee'), dataIndex: 'employeeName', sorter: true, render: (v, r) => r.employeeId && <Link to={`/employees/${r.employeeId}`}>{v}</Link> },
    { key: 'departmentName', title: t('common.department'), dataIndex: 'departmentName', sorter: true, hiddenByDefault: true },
    { key: 'regionName', title: t('common.region'), dataIndex: 'regionName', sorter: true },
    { key: 'locationName', title: t('assets.location'), dataIndex: 'locationName', sorter: true, hiddenByDefault: true },
    { key: 'responsibleName', title: t('assets.responsible'), dataIndex: 'responsibleName', hiddenByDefault: true },
    { key: 'purchaseDate', title: t('assets.purchaseDate'), dataIndex: 'purchaseDate', sorter: true, render: fmtDate, hiddenByDefault: true },
    { key: 'purchasePrice', title: t('assets.price'), dataIndex: 'purchasePrice', sorter: true, render: (v, r) => fmtMoney(v, r.currency), hiddenByDefault: true },
    { key: 'warrantyExpiration', title: t('assets.warranty'), dataIndex: 'warrantyExpiration', sorter: true, render: fmtDate, hiddenByDefault: true },
    { key: 'hostname', title: 'Hostname', dataIndex: 'hostname', hiddenByDefault: true },
    { key: 'ipAddress', title: 'IP', dataIndex: 'ipAddress', hiddenByDefault: true },
    ...(cfs.data ?? []).filter((d) => d.showInList || !d.assetTypeId).map((d) => ({
      key: `cf_${d.key}`, title: d.label, hiddenByDefault: true, render: (_: unknown, r: AssetListItem) => {
        const v = r.customFields?.[d.key];
        return Array.isArray(v) ? v.join(', ') : v === undefined || v === null ? '' : String(v);
      },
    })),
  ];

  return (
    <>
      <PageHeader title={t('menu.assets')} crumbs={[{ title: t('menu.assets') }]}
        extra={<Can perm="assets.create"><Button type="primary" icon={<PlusOutlined />} onClick={() => setParams({ new: '1' })}>{t('assets.new')}</Button></Can>} />
      <DataTable<AssetListItem>
        id="assets" url="/assets" exportUrl="/assets/export" columns={columns} params={filters} searchPlaceholder={t('assets.searchHint')}
        rowSelection={{ selectedRowKeys: selected, onChange: (k) => setSelected(k as string[]), preserveSelectedRowKeys: true }}
        filters={<>
          <LookupSelect lookup="asset-types" placeholder={t('assets.type')} style={{ width: 170 }} onChange={set('assetTypeId')} />
          <EnumSelect group="assetKind" values={ASSET_KINDS} placeholder={t('common.status')} style={{ width: 150 }} value={filters.statusKind as string} onChange={set('statusKind')} />
          <LookupSelect lookup="regions" placeholder={t('common.region')} style={{ width: 150 }} onChange={set('regionId')} />
          <LookupSelect lookup="departments" placeholder={t('common.department')} style={{ width: 180 }} onChange={set('departmentId')} />
          <LookupSelect lookup="locations" placeholder={t('assets.location')} style={{ width: 200 }} onChange={set('locationId')} />
          <LookupSelect lookup="manufacturers" placeholder={t('assets.manufacturer')} style={{ width: 150 }} onChange={set('manufacturerId')} />
          <DatePicker.RangePicker placeholder={[t('assets.purchaseFrom'), t('assets.purchaseTo')]} format="DD.MM.YYYY" onChange={(r) => setFilters((f) => ({ ...f, purchaseFrom: toApiDate(r?.[0]), purchaseTo: toApiDate(r?.[1]) }))} />
          <Checkbox onChange={(e) => set('warrantyExpired')(e.target.checked || undefined)}>{t('assets.warrantyExpired')}</Checkbox>
          <Checkbox checked={!!filters.noResponsible} onChange={(e) => set('noResponsible')(e.target.checked || undefined)}>{t('assets.noResponsible')}</Checkbox>
        </>}
        toolbar={selected.length > 0 && (
          <Dropdown menu={{ items: [
            { key: 'labels', label: t('assets.printLabels'), onClick: () => download('/assets/labels', undefined, 'post', { assetIds: selected }).catch(notify.error) },
            can('assets.assign') && { key: 'issue', label: t('assets.actions.issue'), onClick: () => navigate(`/operations/issue?assetIds=${selected.join(',')}`) },
            can('assets.transfer') && { key: 'transfer', label: t('assets.actions.transfer'), onClick: () => navigate(`/operations/transfer?assetIds=${selected.join(',')}`) },
            can('assets.status') && { key: 'status', label: t('bulk.changeStatus'), onClick: () => setBulkStatus(true) },
            can('assets.bulk') && { key: 'edit', label: t('bulk.edit'), onClick: () => setBulkEdit(true) },
          ].filter(Boolean) as never }}>
            <Button>{t('bulk.actions', { count: selected.length })}</Button>
          </Dropdown>
        )}
        onRow={(r) => ({ onDoubleClick: () => navigate(`/assets/${r.id}`) })}
      />
      <AssetForm open={params.get('new') === '1'} onClose={() => setParams({})} onSaved={(a) => navigate(`/assets/${a.id}`)} />
      <Modal open={bulkStatus} title={t('bulk.changeStatus')} onCancel={() => setBulkStatus(false)} onOk={() => statusForm.submit()} confirmLoading={statusMutation.isPending}>
        <Form form={statusForm} layout="vertical" onFinish={(v) => statusMutation.mutate(v)}>
          <Form.Item name="toStatusId" label={t('common.status')} rules={[{ required: true }]}><LookupSelect lookup="asset-statuses" filter={(s) => !['Assigned', 'InRepair'].includes(s.kind)} /></Form.Item>
          <Form.Item name="effectiveAt" label={t('operations.effectiveAt')}><DatePicker showTime format="DD.MM.YYYY HH:mm" /></Form.Item>
          <Form.Item name="reason" label={t('common.reason')}><Input /></Form.Item>
        </Form>
      </Modal>
      <Modal open={bulkEdit} title={t('bulk.edit')} onCancel={() => setBulkEdit(false)} onOk={() => editForm.submit()} confirmLoading={editMutation.isPending}>
        <Form form={editForm} layout="vertical" onFinish={(v) => editMutation.mutate(v)}>
          <Form.Item name="setResponsible" valuePropName="checked"><Checkbox>{t('assets.responsible')}</Checkbox></Form.Item>
          <Form.Item name="responsibleEmployeeId"><EmployeeSelect /></Form.Item>
          <Form.Item name="setWarranty" valuePropName="checked"><Checkbox>{t('assets.warranty')}</Checkbox></Form.Item>
          <Form.Item name="warrantyExpiration"><DatePicker format="DD.MM.YYYY" /></Form.Item>
          <Form.Item name="setSupplier" valuePropName="checked"><Checkbox>{t('assets.supplier')}</Checkbox></Form.Item>
          <Form.Item name="supplierId"><LookupSelect lookup="suppliers" /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
