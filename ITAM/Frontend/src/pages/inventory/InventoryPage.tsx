import { Button, Form, Input, Modal, Progress } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { post } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { Can } from '@/app/auth';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { LookupSelect } from '@/components/Selects';
import { EnumTag } from '@/components/Tags';
import { fmtDateTime } from '@/utils/format';

export interface Campaign { id: string; number: string; name: string; regionName?: string; locationName?: string; status: string; startedAt?: string; completedAt?: string; total: number; checked: number; found: number; missing: number; misplaced: number; unexpected: number }

export default function InventoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const regionId = Form.useWatch('regionId', form);
  const create = useApiMutation((v: any) => post<Campaign>('/inventory', v), { invalidate: [['inventory']], onSuccess: (c) => navigate(`/inventory/${c.id}`) });
  const columns: DataColumn<Campaign>[] = [
    { key: 'number', title: t('inventory.number'), dataIndex: 'number', alwaysVisible: true, render: (v, r) => <Link to={`/inventory/${r.id}`}>{v}</Link> },
    { key: 'name', title: t('common.name'), dataIndex: 'name' },
    { key: 'regionName', title: t('common.region'), dataIndex: 'regionName' },
    { key: 'locationName', title: t('assets.location'), dataIndex: 'locationName' },
    { key: 'status', title: t('common.status'), dataIndex: 'status', render: (v) => <EnumTag group="inventoryStatus" value={v} /> },
    { key: 'progress', title: t('checklists.progress'), render: (_, r) => <Progress size="small" style={{ width: 140 }} percent={r.total ? Math.round((r.checked / r.total) * 100) : 0} /> },
    { key: 'found', title: t('inventory.found'), dataIndex: 'found' },
    { key: 'missing', title: t('inventory.missing'), dataIndex: 'missing' },
    { key: 'startedAt', title: t('checklists.startedAt'), dataIndex: 'startedAt', render: fmtDateTime },
    { key: 'completedAt', title: t('checklists.completedAt'), dataIndex: 'completedAt', render: fmtDateTime },
  ];
  return (
    <>
      <PageHeader title={t('menu.inventory')} subtitle={t('inventory.hint')} crumbs={[{ title: t('menu.inventory') }]}
        extra={<Can perm="inventory.manage"><Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setOpen(true); }}>{t('inventory.new')}</Button></Can>} />
      <DataTable<Campaign> id="inventory" url="/inventory" columns={columns} />
      <Modal open={open} title={t('inventory.new')} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={create.isPending}>
        <Form form={form} layout="vertical" onFinish={(v) => create.mutate(v)}>
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}><Input placeholder={t('inventory.namePlaceholder')} /></Form.Item>
          <Form.Item name="regionId" label={t('common.region')}><LookupSelect lookup="regions" /></Form.Item>
          <Form.Item name="locationId" label={t('assets.location')} extra={t('inventory.locationHint')}><LookupSelect lookup="locations" filter={(l) => !regionId || l.regionId === regionId} /></Form.Item>
          <Form.Item name="departmentId" label={t('common.department')}><LookupSelect lookup="departments" /></Form.Item>
          <Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
