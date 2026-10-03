import { Button, Col, DatePicker, Form, Input, InputNumber, Modal, Popconfirm, Row, Select, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { del, post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { Can, useAuth } from '@/app/auth';
import { Attachments } from '@/components/Attachments';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect, LookupSelect } from '@/components/Selects';
import { CONTRACT_TYPES } from '@/utils/enums';
import { dayjs, defaultCurrency, fmtDate, fmtMoney, toApiDate } from '@/utils/format';

interface Contract { id: string; number: string; title: string; type: string; supplierId?: string; supplierName?: string; startDate?: string; endDate?: string; amount?: number; currency?: string; notes?: string; regionId?: string; regionName?: string; assetCount: number; licenseCount: number; isActive: boolean; daysLeft?: number }

export default function ContractsPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [editing, setEditing] = useState<Contract | null>();
  const [files, setFiles] = useState<Contract>();
  const [form] = Form.useForm();
  const save = useApiMutation((v: any) => {
    const body = { ...v, startDate: toApiDate(v.startDate), endDate: toApiDate(v.endDate) };
    return editing ? put(`/contracts/${editing.id}`, body) : post('/contracts', body);
  }, { invalidate: [['contracts']], onSuccess: () => setEditing(undefined) });
  const remove = useApiMutation((id: string) => del(`/contracts/${id}`), { invalidate: [['contracts']] });
  const columns: DataColumn<Contract>[] = [
    { key: 'number', title: t('contracts.number'), dataIndex: 'number', sorter: true, alwaysVisible: true },
    { key: 'title', title: t('common.name'), dataIndex: 'title', sorter: true },
    { key: 'type', title: t('operations.type'), dataIndex: 'type', render: (v) => t(`enums.contractType.${v}`) },
    { key: 'supplierName', title: t('assets.supplier'), dataIndex: 'supplierName' },
    { key: 'startDate', title: t('contracts.start'), dataIndex: 'startDate', sorter: true, render: fmtDate },
    { key: 'endDate', title: t('contracts.end'), dataIndex: 'endDate', sorter: true, render: (v, r) => <>{fmtDate(v)} {!r.isActive ? <Tag>{t('contracts.expired')}</Tag> : r.daysLeft !== undefined && r.daysLeft !== null && r.daysLeft <= 30 ? <Tag color="gold">{r.daysLeft}</Tag> : null}</> },
    { key: 'amount', title: t('contracts.amount'), dataIndex: 'amount', sorter: true, render: (v, r) => fmtMoney(v, r.currency) },
    { key: 'links', title: t('contracts.links'), render: (_, r) => `${r.assetCount} / ${r.licenseCount}` },
    { key: 'a', title: '', alwaysVisible: true, render: (_, r) => <Space>
      <Button size="small" onClick={() => setFiles(r)}>{t('tabs.attachments')}</Button>
      {can('contracts.manage') && <Button size="small" onClick={() => { setEditing(r); form.setFieldsValue({ ...r, startDate: r.startDate ? dayjs(r.startDate) : null, endDate: r.endDate ? dayjs(r.endDate) : null }); }}>{t('common.edit')}</Button>}
      {can('contracts.manage') && <Popconfirm title={t('common.confirmDelete')} onConfirm={() => remove.mutate(r.id)}><Button size="small" danger>{t('common.delete')}</Button></Popconfirm>}
    </Space> },
  ];
  return (
    <>
      <PageHeader title={t('menu.contracts')} crumbs={[{ title: t('menu.contracts') }]}
        extra={<Can perm="contracts.manage"><Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); form.setFieldsValue({ type: 'Purchase', currency: defaultCurrency() }); }}>{t('contracts.new')}</Button></Can>} />
      <DataTable<Contract> id="contracts" url="/contracts" columns={columns} />
      <Modal open={editing !== undefined} title={editing?.number ?? t('contracts.new')} onCancel={() => setEditing(undefined)} onOk={() => form.submit()} confirmLoading={save.isPending} width={680} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Row gutter={12}>
            <Col span={8}><Form.Item name="number" label={t('contracts.number')} rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={16}><Form.Item name="title" label={t('common.name')} rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="type" label={t('operations.type')}><EnumSelect group="contractType" values={CONTRACT_TYPES} allowClear={false} /></Form.Item></Col>
            <Col span={12}><Form.Item name="supplierId" label={t('assets.supplier')}><LookupSelect lookup="suppliers" /></Form.Item></Col>
            <Col span={12}><Form.Item name="startDate" label={t('contracts.start')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={12}><Form.Item name="endDate" label={t('contracts.end')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={12}><Form.Item name="amount" label={t('contracts.amount')}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={4}><Form.Item name="currency" label={t('assets.currency')}><Select options={['UZS', 'USD', 'EUR', 'RUB'].map((c) => ({ value: c, label: c }))} /></Form.Item></Col>
            <Col span={8}><Form.Item name="regionId" label={t('common.region')}><LookupSelect lookup="regions" /></Form.Item></Col>
            <Col span={24}><Form.Item name="notes" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
      <Modal open={!!files} title={files?.number} footer={null} onCancel={() => setFiles(undefined)} width={720}>{files && <Attachments entityType="Contract" entityId={files.id} />}</Modal>
    </>
  );
}
