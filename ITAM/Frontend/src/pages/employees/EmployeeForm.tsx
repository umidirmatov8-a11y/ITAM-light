import { Alert, App, Checkbox, Col, DatePicker, Drawer, Form, Input, Radio, Row, Button, Space, Divider } from 'antd';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import { AssetPicker } from '@/components/AssetPicker';
import { DocumentOptions } from '@/components/OperationCommon';
import { useNavigate } from 'react-router-dom';
import type { Employee, OperationResult } from '@/api/types';
import { CustomFieldsFormItems } from '@/components/CustomFields';
import { EmployeeSelect, LookupSelect } from '@/components/Selects';
import { dayjs, toApiDate, toApiDateTime } from '@/utils/format';

export function EmployeeForm({ open, employee, onClose, onSaved }: { open: boolean; employee?: Employee; onClose: () => void; onSaved?: (e: Employee) => void }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { modal } = App.useApp();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const withAssets = Form.useWatch('issueAssets', form) as boolean | undefined;
  const regionId = Form.useWatch('regionId', form);
  const watched = Form.useWatch([], form);
  const orgChanged = !!employee && !!watched && (['departmentId', 'positionId', 'regionId', 'locationId', 'managerId'] as const).some((k) => (watched[k] ?? null) !== ((employee as any)[k] ?? null));

  const issueMode = Form.useWatch('issueMode', form) as 'act' | 'noAct' | undefined;
  const canDocs = can('documents.generate');
  useEffect(() => {
    if (withAssets && !form.getFieldValue('issueMode')) form.setFieldValue('issueMode', canDocs ? 'act' : 'noAct');
  }, [withAssets, form, canDocs]);
  useEffect(() => {
    if (issueMode) form.setFieldValue('generateDocument', issueMode === 'act');
  }, [issueMode, form]);

  useEffect(() => {
    if (!open) return;
    form.resetFields();
    if (employee) form.setFieldsValue({ ...employee, hireDate: employee.hireDate ? dayjs(employee.hireDate) : null, customFields: employee.customFields ?? {} });
  }, [open, employee, form]);

  const save = useApiMutation(
    (v: any) => {
      const { issueAssets, issueMode: mode, issueDate, assetIds, accessories, issueComment, generateDocument, templateId, ...rest } = v;
      const body = { ...rest, hireDate: toApiDate(v.hireDate), orgChangeEffectiveAt: toApiDateTime(v.orgChangeEffectiveAt), version: employee?.version };
      if (employee) return put<Employee>(`/employees/${employee.id}`, body);
      if (!issueAssets || !assetIds?.length) return post<Employee>('/employees', body);
      return post<{ employee: Employee; issue?: OperationResult; issueError?: string }>('/employees/with-assets', {
        employee: body, assetIds, accessories, comment: issueComment, generateDocument: mode === 'act' && !!generateDocument, templateId,
        effectiveAt: issueDate ? toApiDateTime(issueDate) : undefined,
      }).then((r) => {
        if (r.issueError) modal.warning({ title: t('employees.createdIssueFailed'), content: r.issueError, okText: t('employees.issueNow'), onOk: () => navigate(`/operations/issue?employeeId=${r.employee.id}`) });
        else if (r.issue) modal.success({
          title: t(r.issue.documentId ? 'employees.createdWithAssets' : 'employees.createdWithAssetsNoAct', { count: r.issue.assetCount, number: r.issue.number }),
          okText: t('employees.openOperation'), onOk: () => navigate(`/operations/${r.issue!.batchId}`),
        });
        return r.employee;
      });
    },
    { invalidate: [['employees'], ['employee', employee?.id], ['assets']], onSuccess: (e) => { onSaved?.(e); onClose(); } },
  );

  return (
    <Drawer open={open} onClose={onClose} width={720} title={employee ? t('employees.edit') : t('employees.new')} destroyOnHidden
      extra={<Space><Button onClick={onClose}>{t('common.cancel')}</Button><Button type="primary" loading={save.isPending} onClick={() => form.submit()}>{t('common.save')}</Button></Space>}>
      <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Row gutter={12}>
          <Col span={8}><Form.Item name="lastName" label={t('employees.lastName')} rules={[{ required: true, message: t('common.required') }]}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="firstName" label={t('employees.firstName')} rules={[{ required: true, message: t('common.required') }]}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="middleName" label={t('employees.middleName')}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="employeeNumber" label={t('employees.number')} extra={!employee && t('employees.numberAuto')}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="login" label={t('employees.login')}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="email" label="Email" rules={[{ type: 'email' }]}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="phone" label={t('employees.phone')}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="hireDate" label={t('employees.hireDate')}><DatePicker style={{ width: '100%' }} format="DD.MM.YYYY" /></Form.Item></Col>
          <Col span={8}><Form.Item name="statusId" label={t('common.status')}><LookupSelect lookup="employee-statuses" filter={(s) => s.kind !== 'Terminated'} /></Form.Item></Col>
        </Row>
        <Divider orientation="left" plain>{t('employees.orgPlacement')}</Divider>
        <Row gutter={12}>
          <Col span={12}><Form.Item name="regionId" label={t('common.region')} rules={[{ required: true, message: t('common.required') }]}><LookupSelect lookup="regions" /></Form.Item></Col>
          <Col span={12}><Form.Item name="departmentId" label={t('common.department')}><LookupSelect lookup="departments" filter={(d) => !regionId || !d.regionId || d.regionId === regionId} /></Form.Item></Col>
          <Col span={12}><Form.Item name="positionId" label={t('employees.position')}><LookupSelect lookup="positions" /></Form.Item></Col>
          <Col span={12}><Form.Item name="managerId" label={t('employees.manager')}><EmployeeSelect initialLabel={employee?.managerName} /></Form.Item></Col>
          <Col span={12}><Form.Item name="locationId" label={t('employees.office')}><LookupSelect lookup="locations" filter={(l) => (!regionId || l.regionId === regionId) && l.type !== 'Room'} /></Form.Item></Col>
          <Col span={12}><Form.Item name="roomId" label={t('employees.room')}><LookupSelect lookup="locations" filter={(l) => (!regionId || l.regionId === regionId) && l.type === 'Room'} /></Form.Item></Col>
        </Row>
        {orgChanged && (
          <>
            <Alert type="info" showIcon message={t('employees.orgChangeHint')} style={{ marginBottom: 12 }} />
            <Row gutter={12}>
              <Col span={12}><Form.Item name="orgChangeEffectiveAt" label={t('employees.orgChangeDate')}><DatePicker showTime style={{ width: '100%' }} format="DD.MM.YYYY HH:mm" /></Form.Item></Col>
              <Col span={12}><Form.Item name="orgChangeReason" label={t('common.reason')}><Input /></Form.Item></Col>
            </Row>
          </>
        )}
        <Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item>
        <CustomFieldsFormItems entity="Employee" />
        {!employee && <Form.Item name="startOnboarding" valuePropName="checked" initialValue><Checkbox>{t('employees.startOnboarding')}</Checkbox></Form.Item>}
        {!employee && can('assets.assign') && (
          <>
            <Divider orientation="left" plain>{t('employees.equipment')}</Divider>
            <Form.Item name="issueAssets" valuePropName="checked" extra={t('employees.issueAssetsHint')}><Checkbox>{t('employees.issueAssets')}</Checkbox></Form.Item>
            {withAssets && (
              <>
                <Form.Item name="assetIds" label={t('operations.assets')} rules={[{ required: true, type: 'array', min: 1, message: t('operations.noAssets') }]}>
                  <AssetPicker filters={{ assigned: false }} />
                </Form.Item>
                <Form.Item name="accessories" label={t('operations.accessories')}><Input placeholder={t('operations.accessoriesPlaceholder')} /></Form.Item>
                <Form.Item name="issueComment" label={t('employees.issueComment')}><Input /></Form.Item>
                <Form.Item name="issueMode" label={t('employees.issueMode')}>
                  <Radio.Group>
                    <Space direction="vertical">
                      {canDocs && <Radio value="act">{t('employees.issueWithAct')}</Radio>}
                      <Radio value="noAct">{t('employees.issueWithoutAct')}</Radio>
                    </Space>
                  </Radio.Group>
                </Form.Item>
                {issueMode === 'noAct' && (
                  <Form.Item name="issueDate" label={t('employees.issueDate')} extra={t('employees.issueDateHint')}>
                    <DatePicker showTime style={{ width: 260 }} format="DD.MM.YYYY HH:mm" />
                  </Form.Item>
                )}
                {issueMode === 'act' && <DocumentOptions type="EquipmentIssue" hideToggle />}
              </>
            )}
          </>
        )}
      </Form>
    </Drawer>
  );
}
