import { Button, Card, Col, DatePicker, Form, Input, InputNumber, Modal, Row, Table, Tabs, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post, type Paged } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { Can } from '@/app/auth';
import { PageHeader } from '@/components/PageHeader';
import { AssetSelect, EmployeeSelect, EnumSelect, LookupSelect } from '@/components/Selects';
import { DictionaryTable } from '@/pages/admin/DictionariesPage';
import { STOCK_MOVEMENT_TYPES } from '@/utils/enums';
import { fmtDateTime, fmtNumber, toApiDateTime } from '@/utils/format';

export default function StockPage() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const type = Form.useWatch('type', form);
  const summary = useQuery<any[]>({ queryKey: ['stock-summary'], queryFn: () => get('/stock/summary') });
  const balances = useQuery<any[]>({ queryKey: ['stock-balances'], queryFn: () => get('/stock/balances') });
  const moves = useQuery<Paged<any>>({ queryKey: ['stock-moves'], queryFn: () => get('/stock/movements', { pageSize: 200 }) });
  const move = useApiMutation((v: any) => post('/stock/movements', { ...v, effectiveAt: toApiDateTime(v.effectiveAt) }), {
    invalidate: [['stock-summary'], ['stock-balances'], ['stock-moves']], onSuccess: () => setOpen(false),
  });
  return (
    <>
      <PageHeader title={t('menu.stock')} subtitle={t('stock.hint')} crumbs={[{ title: t('menu.stock') }]}
        extra={<Can perm="stock.manage"><Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); form.setFieldsValue({ type: 'Receipt' }); setOpen(true); }}>{t('stock.movement')}</Button></Can>} />
      <Tabs items={[
        { key: 's', label: t('stock.summary'), children: (
          <Card><Table rowKey="id" size="small" loading={summary.isLoading} dataSource={summary.data} pagination={false}
            columns={[
              { title: t('common.name'), dataIndex: 'name' }, { title: 'SKU', dataIndex: 'sku' }, { title: t('stock.category'), dataIndex: 'category' },
              { title: t('stock.total'), render: (_, r) => <>{fmtNumber(r.total)} {r.unit} {r.isLow && <Tag color="red">{t('stock.low')}</Tag>}</> },
              { title: t('stock.min'), dataIndex: 'minQuantity', render: fmtNumber },
            ]} /></Card>
        ) },
        { key: 'b', label: t('stock.balances'), children: (
          <Card><Table rowKey={(r) => r.stockItemId + r.locationId} size="small" dataSource={balances.data} pagination={false}
            columns={[{ title: t('common.name'), dataIndex: 'itemName' }, { title: t('stock.warehouse'), dataIndex: 'locationName' }, { title: t('stock.quantity'), render: (_, r) => `${fmtNumber(r.quantity)} ${r.unit}` }]} /></Card>
        ) },
        { key: 'm', label: t('stock.movements'), children: (
          <Card><Table rowKey="id" size="small" dataSource={moves.data?.items} pagination={{ pageSize: 50 }} scroll={{ x: 'max-content' }}
            columns={[
              { title: t('operations.effectiveAt'), dataIndex: 'effectiveAt', render: fmtDateTime }, { title: t('common.name'), dataIndex: 'itemName' },
              { title: t('operations.type'), dataIndex: 'type', render: (v) => <Tag>{t(`enums.stockMovement.${v}`)}</Tag> }, { title: t('stock.quantity'), dataIndex: 'quantity', render: fmtNumber },
              { title: t('operations.from'), dataIndex: 'fromLocation' }, { title: t('operations.to'), dataIndex: 'toLocation' }, { title: t('access.employee'), dataIndex: 'employeeName' },
              { title: t('assets.inventoryNumber'), dataIndex: 'assetNumber' }, { title: t('stock.document'), dataIndex: 'documentNumber' }, { title: t('common.comment'), dataIndex: 'comment' },
            ]} /></Card>
        ) },
        { key: 'i', label: t('stock.items'), children: <DictionaryTable lookupKey="stock-items" /> },
      ]} />
      <Modal open={open} title={t('stock.movement')} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={move.isPending} width={640}>
        <Form form={form} layout="vertical" onFinish={(v) => move.mutate(v)}>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="type" label={t('operations.type')}><EnumSelect group="stockMovement" values={STOCK_MOVEMENT_TYPES} allowClear={false} /></Form.Item></Col>
            <Col span={12}><Form.Item name="stockItemId" label={t('common.name')} rules={[{ required: true }]}><LookupSelect lookup="stock-items" /></Form.Item></Col>
            <Col span={12}><Form.Item name="quantity" label={type === 'Adjustment' ? t('stock.counted') : t('stock.quantity')} rules={[{ required: true }]}><InputNumber min={0.001} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={12}><Form.Item name="effectiveAt" label={t('operations.effectiveAt')}><DatePicker showTime format="DD.MM.YYYY HH:mm" style={{ width: '100%' }} /></Form.Item></Col>
            {type !== 'Receipt' && <Col span={12}><Form.Item name="fromLocationId" label={t('stock.fromWarehouse')}><LookupSelect lookup="locations" /></Form.Item></Col>}
            {['Receipt', 'Transfer'].includes(type) && <Col span={12}><Form.Item name="toLocationId" label={t('stock.toWarehouse')}><LookupSelect lookup="locations" /></Form.Item></Col>}
            {['Issue', 'UsedInRepair'].includes(type) && <Col span={12}><Form.Item name="employeeId" label={t('access.employee')}><EmployeeSelect /></Form.Item></Col>}
            {['Issue', 'UsedInRepair'].includes(type) && <Col span={12}><Form.Item name="assetId" label={t('repairs.asset')}><AssetSelect /></Form.Item></Col>}
            <Col span={12}><Form.Item name="documentNumber" label={t('stock.document')}><Input /></Form.Item></Col>
            <Col span={24}><Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
    </>
  );
}
