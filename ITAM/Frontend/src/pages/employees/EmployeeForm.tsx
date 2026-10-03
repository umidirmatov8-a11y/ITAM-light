import { Alert, Checkbox, Col, DatePicker, Drawer, Form, Input, Row, Button, Space, Divider } from 'antd';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import type { Employee } from '@/api/types';
import { CustomFieldsFormItems } from '@/components/CustomFields';
import { EmployeeSelect, LookupSelect } from '@/components/Selects';
import { dayjs, toApiDate, toApiDateTime } from '@/utils/format';

export function EmployeeForm({ open, employee, onClose, onSaved }: { open: boolean; employee?: Employee; onClose: () => void; onSaved?: (e: Employee) => void }) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const regionId = Form.useWatch('regionId', form);
  const watched = Form.useWatch([], form);
  const orgChanged = !!employee && !!watched && (['departmentId', 'positionId', 'regionId', 'locationId', 'managerId'] as const).some((k) => (watched[k] ?? null) !== ((employee as any)[k] ?? null));

  useEffect(() => {
    if (!open) return;
    form.resetFields();
    if (employee) form.setFieldsValue({ ...employee, hireDate: employee.hireDate ? dayjs(employee.hireDate) : null, customFields: employee.customFields ?? {} });
  }, [open, employee, form]);

  const save = useApiMutation(
    (v: any) => {
      const body = { ...v, hireDate: toApiDate(v.hireDate), orgChangeEffectiveAt: toApiDateTime(v.orgChangeEffectiveAt), version: employee?.version };
      return employee ? put<Employee>(`/employees/${employee.id}`, body) : post<Employee>('/employees', body);
    },
    { invalidate: [['employees'], ['employee', employee?.id]], onSuccess: (e) => { onSaved?.(e); onClose(); } },
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
      </Form>
    </Drawer>
  );
}
