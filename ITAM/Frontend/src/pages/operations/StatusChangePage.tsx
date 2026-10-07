import { Card, Col, DatePicker, Form, Input, Row, Button, Alert } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { post } from '@/api/client';
import { useApiMutation, useLookup } from '@/api/hooks';
import type { OperationResult } from '@/api/types';
import { AssetPicker } from '@/components/AssetPicker';
import { DocumentOptions, EffectiveAtField, Half, OperationDone, idsFromQuery } from '@/components/OperationCommon';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, LookupSelect } from '@/components/Selects';
import { nowInTz, toApiDate, toApiDateTime } from '@/utils/format';

export default function StatusChangePage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [form] = Form.useForm();
  const [result, setResult] = useState<OperationResult>();
  const statuses = useLookup('asset-statuses');
  const statusId = Form.useWatch('toStatusId', form);
  const kind = statuses.data?.find((s) => s.id === statusId)?.kind as string | undefined;
  const change = useApiMutation((v: any) => post<OperationResult>('/operations/status', { ...v, effectiveAt: toApiDateTime(v.effectiveAt), reservedUntil: toApiDate(v.reservedUntil) }), {
    invalidate: [['assets'], ['asset'], ['operations']], success: false, onSuccess: setResult,
  });
  return (
    <>
      <PageHeader title={t('operations.statusTitle')} crumbs={[{ title: t('menu.operations'), to: '/operations' }, { title: t('operations.statusTitle') }]} />
      <Card>
        {result ? <OperationDone result={result} onAgain={() => { setResult(undefined); form.resetFields(); }} /> : (
          <Form form={form} layout="vertical" onFinish={(v) => change.mutate(v)} initialValues={{ assetIds: idsFromQuery(params.get('assetIds')), effectiveAt: nowInTz() }}>
            <Row gutter={16}>
              <Col span={24}><Form.Item name="assetIds" label={t('operations.assets')} rules={[{ required: true, type: 'array', min: 1 }]}><AssetPicker /></Form.Item></Col>
              <Half><Form.Item name="toStatusId" label={t('operations.newStatus')} rules={[{ required: true }]}><LookupSelect lookup="asset-statuses" filter={(s) => !['Assigned', 'InRepair'].includes(s.kind)} /></Form.Item></Half>
              <Half><EffectiveAtField /></Half>
              {kind && ['Disposed', 'WrittenOff'].includes(kind) && <Col span={24}><Alert type="warning" showIcon style={{ marginBottom: 16 }} message={t('operations.writeOffWarning')} /></Col>}
              {kind === 'Reserved' && <>
                <Half><Form.Item name="reservedForEmployeeId" label={t('operations.reservedFor')}><EmployeeSelect /></Form.Item></Half>
                <Half><Form.Item name="reservedUntil" label={t('operations.reservedUntil')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Half>
              </>}
              {kind && ['Disposed', 'WrittenOff'].includes(kind) && <Half><Form.Item name="disposalMethod" label={t('operations.disposalMethod')}><Input /></Form.Item></Half>}
              <Col span={24}><Form.Item name="reason" label={t('common.reason')} rules={[{ required: kind ? ['Disposed', 'WrittenOff', 'Lost', 'Stolen'].includes(kind) : false }]}><Input /></Form.Item></Col>
              <Col span={24}><Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
              <Col span={24}><DocumentOptions type={kind && ['Disposed', 'WrittenOff'].includes(kind) ? 'WriteOffAct' : 'Other'} /></Col>
            </Row>
            <Button type="primary" htmlType="submit" size="large" loading={change.isPending}>{t('operations.statusSubmit')}</Button>
          </Form>
        )}
      </Card>
    </>
  );
}
