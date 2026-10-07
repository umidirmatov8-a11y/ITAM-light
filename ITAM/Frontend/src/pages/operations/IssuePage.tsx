import { Card, Checkbox, Col, DatePicker, Form, Input, Row, Button } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { post } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { OperationResult } from '@/api/types';
import { AssetPicker } from '@/components/AssetPicker';
import { DocumentOptions, EffectiveAtField, Half, OperationDone, idsFromQuery } from '@/components/OperationCommon';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, EnumSelect, LookupSelect } from '@/components/Selects';
import { CONDITIONS } from '@/utils/enums';
import { nowInTz, toApiDate, toApiDateTime } from '@/utils/format';

export default function IssuePage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [params] = useSearchParams();
  const [form] = Form.useForm();
  const [result, setResult] = useState<OperationResult>();
  const historical = Form.useWatch('historical', form);
  const issue = useApiMutation((v: any) => post<OperationResult>('/operations/issue', {
    ...v, effectiveAt: toApiDateTime(v.effectiveAt), expectedReturnDate: toApiDate(v.expectedReturnDate), returnedAt: v.historical ? toApiDateTime(v.returnedAt) : undefined,
  }), { invalidate: [['assets'], ['asset'], ['employees'], ['operations']], success: false, onSuccess: setResult });

  return (
    <>
      <PageHeader title={t('operations.issueTitle')} crumbs={[{ title: t('menu.operations'), to: '/operations' }, { title: t('operations.issueTitle') }]} />
      <Card>
        {result ? <OperationDone result={result} onAgain={() => { setResult(undefined); form.resetFields(); }} /> : (
          <Form form={form} layout="vertical" onFinish={(v) => issue.mutate(v)}
            initialValues={{ employeeId: params.get('employeeId') ?? undefined, assetIds: idsFromQuery(params.get('assetIds')), effectiveAt: nowInTz(), condition: 'Good', generateDocument: true }}>
            <Row gutter={16}>
              <Half><Form.Item name="employeeId" label={t('operations.employee')} rules={[{ required: true }]}><EmployeeSelect /></Form.Item></Half>
              <Half><EffectiveAtField /></Half>
              <Col span={24}><Form.Item name="assetIds" label={t('operations.assets')} rules={[{ required: true, type: 'array', min: 1 }]}><AssetPicker /></Form.Item></Col>
              <Half><Form.Item name="locationId" label={t('operations.location')} extra={t('operations.locationHint')}><LookupSelect lookup="locations" /></Form.Item></Half>
              <Half><Form.Item name="responsibleEmployeeId" label={t('common.responsible')}><EmployeeSelect /></Form.Item></Half>
              <Half><Form.Item name="condition" label={t('assets.condition')}><EnumSelect group="condition" values={CONDITIONS} allowClear={false} /></Form.Item></Half>
              <Half><Form.Item name="expectedReturnDate" label={t('operations.expectedReturn')} extra={t('operations.expectedReturnHint')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Half>
              <Col span={24}><Form.Item name="accessories" label={t('operations.accessories')}><Input placeholder={t('operations.accessoriesPlaceholder')} /></Form.Item></Col>
              <Col span={24}><Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
              {can('assets.backdate') && (
                <Col span={24}>
                  <Form.Item name="historical" valuePropName="checked" extra={t('operations.historicalHint')}><Checkbox>{t('operations.historical')}</Checkbox></Form.Item>
                  {historical && <Form.Item name="returnedAt" label={t('operations.returnedAt')} rules={[{ required: true }]}><DatePicker showTime format="DD.MM.YYYY HH:mm" /></Form.Item>}
                </Col>
              )}
              <Col span={24}><DocumentOptions type="EquipmentIssue" /></Col>
            </Row>
            <Button type="primary" htmlType="submit" size="large" loading={issue.isPending}>{t('operations.issueSubmit')}</Button>
          </Form>
        )}
      </Card>
    </>
  );
}
