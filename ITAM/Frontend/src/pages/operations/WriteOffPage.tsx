import { Alert, Button, Card, Col, Form, Input, Row } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { post } from '@/api/client';
import { useApiMutation, useLookup } from '@/api/hooks';
import type { OperationResult } from '@/api/types';
import { AssetPicker } from '@/components/AssetPicker';
import { DocumentOptions, EffectiveAtField, Half, OperationDone, idsFromQuery } from '@/components/OperationCommon';
import { PageHeader } from '@/components/PageHeader';
import { LookupSelect } from '@/components/Selects';
import { nowInTz, toApiDateTime } from '@/utils/format';

const WRITE_OFF_KINDS = ['WrittenOff', 'Disposed'];

/** Write-off (списание) of equipment, typically from a warehouse: status «written off» / «disposed» with an act. */
export default function WriteOffPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [form] = Form.useForm();
  const [result, setResult] = useState<OperationResult>();
  const statuses = useLookup('asset-statuses');
  const locationId = params.get('locationId') ?? undefined;

  useEffect(() => {
    const items = (statuses.data ?? []).filter((s) => s.kind === 'WrittenOff');
    const preferred = items.find((s) => s.isDefaultForKind) ?? items[0];
    if (preferred && !form.getFieldValue('toStatusId')) form.setFieldValue('toStatusId', preferred.id);
  }, [statuses.data, form]);

  const writeOff = useApiMutation((v: any) => post<OperationResult>('/operations/status', { ...v, effectiveAt: toApiDateTime(v.effectiveAt) }), {
    invalidate: [['assets'], ['asset'], ['operations'], ['warehouses'], ['warehouse-stock']], success: false, onSuccess: setResult,
  });
  return (
    <>
      <PageHeader title={t('warehouse.writeOffTitle')} crumbs={[{ title: t('menu.operations'), to: '/operations' }, { title: t('warehouse.writeOffTitle') }]} />
      <Card>
        {result ? <OperationDone result={result} onAgain={() => { setResult(undefined); form.resetFields(); }} /> : (
          <Form form={form} layout="vertical" onFinish={(v) => writeOff.mutate(v)}
            initialValues={{ assetIds: idsFromQuery(params.get('assetIds')), effectiveAt: nowInTz(), generateDocument: true }}>
            <Row gutter={16}>
              <Col span={24}>
                <Form.Item name="assetIds" label={t('operations.assets')} rules={[{ required: true, type: 'array', min: 1 }]} extra={locationId ? t('warehouse.pickFromWarehouse') : undefined}>
                  <AssetPicker filters={locationId ? { locationId } : undefined} />
                </Form.Item>
              </Col>
              <Col span={24}><Alert type="warning" showIcon style={{ marginBottom: 16 }} message={t('operations.writeOffWarning')} /></Col>
              <Half><Form.Item name="toStatusId" label={t('operations.newStatus')} rules={[{ required: true }]}><LookupSelect lookup="asset-statuses" filter={(s) => WRITE_OFF_KINDS.includes(s.kind)} allowClear={false} /></Form.Item></Half>
              <Half><EffectiveAtField /></Half>
              <Col span={24}><Form.Item name="reason" label={t('warehouse.writeOffReason')} rules={[{ required: true }]}><Input placeholder={t('warehouse.writeOffReasonPlaceholder')} /></Form.Item></Col>
              <Half><Form.Item name="disposalMethod" label={t('operations.disposalMethod')}><Input placeholder={t('warehouse.disposalPlaceholder')} /></Form.Item></Half>
              <Col span={24}><Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
              <Col span={24}><DocumentOptions type="WriteOffAct" /></Col>
            </Row>
            <Button type="primary" danger htmlType="submit" size="large" loading={writeOff.isPending}>{t('warehouse.writeOffSubmit')}</Button>
          </Form>
        )}
      </Card>
    </>
  );
}
