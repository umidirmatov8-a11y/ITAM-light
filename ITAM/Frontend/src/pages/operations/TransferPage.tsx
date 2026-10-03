import { Card, Checkbox, Col, Form, Input, Row, Button, Segmented } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { post } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import type { OperationResult } from '@/api/types';
import { AssetPicker } from '@/components/AssetPicker';
import { DocumentOptions, EffectiveAtField, Half, OperationDone, idsFromQuery } from '@/components/OperationCommon';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, LookupSelect } from '@/components/Selects';
import { nowInTz, toApiDateTime } from '@/utils/format';

export default function TransferPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [form] = Form.useForm();
  const [mode, setMode] = useState<'employee' | 'place'>('place');
  const [result, setResult] = useState<OperationResult>();
  const regionId = Form.useWatch('toRegionId', form);
  const transfer = useApiMutation((v: any) => post<OperationResult>('/operations/transfer', {
    ...v, effectiveAt: toApiDateTime(v.effectiveAt), toEmployeeId: mode === 'employee' ? v.toEmployeeId : undefined,
  }), { invalidate: [['assets'], ['asset'], ['operations']], success: false, onSuccess: setResult });
  return (
    <>
      <PageHeader title={t('operations.transferTitle')} crumbs={[{ title: t('menu.operations'), to: '/operations' }, { title: t('operations.transferTitle') }]} />
      <Card>
        {result ? <OperationDone result={result} onAgain={() => { setResult(undefined); form.resetFields(); }} /> : (
          <Form form={form} layout="vertical" onFinish={(v) => transfer.mutate(v)} initialValues={{ assetIds: idsFromQuery(params.get('assetIds')), effectiveAt: nowInTz(), generateDocument: false }}>
            <Row gutter={16}>
              <Col span={24}><Form.Item name="assetIds" label={t('operations.assets')} rules={[{ required: true, type: 'array', min: 1 }]}><AssetPicker /></Form.Item></Col>
              <Col span={24}>
                <Segmented value={mode} onChange={(v) => setMode(v as never)} style={{ marginBottom: 16 }}
                  options={[{ value: 'place', label: t('operations.toPlace') }, { value: 'employee', label: t('operations.toEmployee') }]} />
              </Col>
              {mode === 'employee' && <Half><Form.Item name="toEmployeeId" label={t('operations.newHolder')} rules={[{ required: true }]} extra={t('operations.toEmployeeHint')}><EmployeeSelect /></Form.Item></Half>}
              <Half><Form.Item name="toRegionId" label={t('operations.toRegion')}><LookupSelect lookup="regions" /></Form.Item></Half>
              <Half><Form.Item name="toLocationId" label={t('operations.toLocation')}><LookupSelect lookup="locations" filter={(l) => !regionId || l.regionId === regionId} /></Form.Item></Half>
              <Half><Form.Item name="toDepartmentId" label={t('operations.toDepartment')}><LookupSelect lookup="departments" /></Form.Item></Half>
              {mode === 'place' && <Half><Form.Item name="clearDepartment" valuePropName="checked" label=" "><Checkbox>{t('operations.clearDepartment')}</Checkbox></Form.Item></Half>}
              <Half><EffectiveAtField /></Half>
              <Half><Form.Item name="responsibleEmployeeId" label={t('common.responsible')}><EmployeeSelect /></Form.Item></Half>
              <Col span={24}><Form.Item name="reason" label={t('common.reason')}><Input /></Form.Item></Col>
              <Col span={24}><Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
              <Col span={24}><DocumentOptions type="EquipmentTransfer" /></Col>
            </Row>
            <Button type="primary" htmlType="submit" size="large" loading={transfer.isPending}>{t('operations.transferSubmit')}</Button>
          </Form>
        )}
      </Card>
    </>
  );
}
