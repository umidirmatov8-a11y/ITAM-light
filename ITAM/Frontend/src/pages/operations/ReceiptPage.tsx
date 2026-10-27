import { Alert, Button, Card, Col, DatePicker, Form, Input, InputNumber, Row } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post } from '@/api/client';
import { useApiMutation, useLookup } from '@/api/hooks';
import type { OperationResult, Warehouse } from '@/api/types';
import { DocumentOptions, EffectiveAtField, Half, OperationDone } from '@/components/OperationCommon';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, EnumSelect, LookupSelect } from '@/components/Selects';
import { CONDITIONS } from '@/utils/enums';
import { nowInTz, toApiDate, toApiDateTime } from '@/utils/format';

/** Serial numbers typed or pasted one per line (commas and semicolons are accepted too). */
const parseSerials = (text?: string) => (text ?? '').split(/[\n,;\t]+/).map((s) => s.trim()).filter(Boolean);

/** Receipt (приход) of new equipment into a warehouse — by default the shared warehouse. One asset is registered per unit. */
export default function ReceiptPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [form] = Form.useForm();
  const [result, setResult] = useState<OperationResult>();
  const warehouses = useQuery<Warehouse[]>({ queryKey: ['warehouses'], queryFn: () => get('/assets/warehouses') });
  const types = useLookup('asset-types');
  const typeId = Form.useWatch('assetTypeId', form);
  const model = Form.useWatch('model', form);
  const serialsText = Form.useWatch('serialsText', form) as string | undefined;
  const quantity = Form.useWatch('quantity', form) as number | undefined;
  const serials = parseSerials(serialsText);
  const type = types.data?.find((x) => x.id === typeId);
  const duplicates = serials.filter((s, i) => serials.findIndex((x) => x.toLowerCase() === s.toLowerCase()) !== i);

  useEffect(() => {
    if (!form.getFieldValue('locationId') && warehouses.data?.length) {
      const preferred = params.get('locationId') ?? warehouses.data.find((w) => w.isShared)?.id ?? warehouses.data[0].id;
      form.setFieldValue('locationId', preferred);
    }
  }, [warehouses.data, params, form]);

  const receive = useApiMutation((v: any) => post<OperationResult>('/operations/receipt', {
    ...v, serialsText: undefined, serialNumbers: parseSerials(v.serialsText), quantity: parseSerials(v.serialsText).length || v.quantity,
    effectiveAt: toApiDateTime(v.effectiveAt), purchaseDate: toApiDate(v.purchaseDate), warrantyExpiration: toApiDate(v.warrantyExpiration),
  }), { invalidate: [['assets'], ['warehouses'], ['warehouse-stock'], ['operations']], success: false, onSuccess: setResult });

  const autoName = type ? [type.name, model].filter(Boolean).join(' ') : '';
  return (
    <>
      <PageHeader title={t('warehouse.receiptTitle')} crumbs={[{ title: t('menu.warehouse'), to: '/warehouse' }, { title: t('warehouse.receiptTitle') }]} />
      <Card>
        {result ? (
          <>
            <OperationDone result={result} onAgain={() => { setResult(undefined); form.resetFields(); }} />
            <div style={{ textAlign: 'center' }}>
              <Button onClick={() => navigate(`/warehouse?id=${form.getFieldValue('locationId') ?? ''}`)}>{t('warehouse.openWarehouse')}</Button>
            </div>
          </>
        ) : (
          <Form form={form} layout="vertical" onFinish={(v) => receive.mutate(v)}
            initialValues={{ effectiveAt: nowInTz(), quantity: 1, condition: 'New', currency: 'UZS', generateDocument: true, assetTypeId: params.get('assetTypeId') ?? undefined }}>
            <Row gutter={16}>
              <Half>
                <Form.Item name="locationId" label={t('warehouse.warehouse')} rules={[{ required: true }]} extra={t('warehouse.warehouseHint')}>
                  <LookupSelect lookup="locations" filter={(l) => l.type === 'Warehouse'}
                    labelOf={(l) => `${(l.fullPath as string) || l.name}${l.isShared ? ` · ${t('warehouse.shared')}` : ''}`} allowClear={false} />
                </Form.Item>
              </Half>
              <Half><EffectiveAtField label={t('warehouse.receivedAt')} /></Half>
              <Half><Form.Item name="assetTypeId" label={t('assets.type')} rules={[{ required: true }]}><LookupSelect lookup="asset-types" /></Form.Item></Half>
              <Half><Form.Item name="manufacturerId" label={t('assets.manufacturer')}><LookupSelect lookup="manufacturers" /></Form.Item></Half>
              <Half><Form.Item name="model" label={t('assets.model')}><Input /></Form.Item></Half>
              <Half><Form.Item name="name" label={t('assets.name')} extra={t('warehouse.nameHint')}><Input placeholder={autoName} /></Form.Item></Half>
              <Half>
                <Form.Item name="serialsText" label={t('warehouse.serials')} extra={t('warehouse.serialsHint')}
                  rules={[{ required: !!type?.requireSerialNumber, message: t('warehouse.serialsRequired') }]}>
                  <Input.TextArea rows={5} className="itam-mono" placeholder={'SN001\nSN002\nSN003'} />
                </Form.Item>
                {duplicates.length > 0 && <Alert type="error" showIcon style={{ marginBottom: 16 }} message={t('warehouse.serialsDuplicate', { list: [...new Set(duplicates)].join(', ') })} />}
              </Half>
              <Half>
                <Form.Item name="quantity" label={t('warehouse.quantity')} extra={serials.length ? t('warehouse.quantityFromSerials', { count: serials.length }) : undefined}>
                  <InputNumber min={1} max={500} style={{ width: '100%' }} disabled={serials.length > 0} />
                </Form.Item>
                <Form.Item name="condition" label={t('assets.condition')}><EnumSelect group="condition" values={CONDITIONS} allowClear={false} /></Form.Item>
              </Half>
              <Half><Form.Item name="supplierId" label={t('assets.supplier')}><LookupSelect lookup="suppliers" /></Form.Item></Half>
              <Half><Form.Item name="invoiceNumber" label={t('warehouse.invoice')}><Input /></Form.Item></Half>
              <Half><Form.Item name="purchaseDate" label={t('assets.purchaseDate')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Half>
              <Half>
                <Row gutter={8}>
                  <Col span={16}><Form.Item name="purchasePrice" label={t('warehouse.unitPrice')}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
                  <Col span={8}><Form.Item name="currency" label={t('warehouse.currency')}><Input maxLength={8} /></Form.Item></Col>
                </Row>
              </Half>
              <Half><Form.Item name="warrantyExpiration" label={t('assets.warranty')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Half>
              <Half><Form.Item name="responsibleEmployeeId" label={t('assets.responsible')}><EmployeeSelect /></Form.Item></Half>
              <Col span={24}><Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
              <Col span={24}><DocumentOptions type="ReceiptAct" /></Col>
            </Row>
            <Button type="primary" htmlType="submit" size="large" loading={receive.isPending} disabled={duplicates.length > 0}>
              {t('warehouse.receiptSubmit', { count: serials.length || quantity || 1 })}
            </Button>
          </Form>
        )}
      </Card>
    </>
  );
}
