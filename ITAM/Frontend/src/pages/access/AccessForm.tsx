import { DatePicker, Form, Input, Modal, Select } from 'antd';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import type { AccessItem } from '@/api/types';
import { CustomFieldsFormItems } from '@/components/CustomFields';
import { EmployeeSelect, LookupSelect } from '@/components/Selects';
import { ACCESS_STATUSES } from '@/utils/enums';
import { dayjs, parseDateTime, toApiDate, toApiDateTime } from '@/utils/format';

export function AccessForm({ open, employeeId, access, onClose, invalidate }: { open: boolean; employeeId?: string; access?: AccessItem; onClose: () => void; invalidate: unknown[][] }) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const systemId = Form.useWatch('accessSystemId', form);
  useEffect(() => {
    if (!open) return;
    form.resetFields();
    if (access) form.setFieldsValue({ ...access, grantedAt: parseDateTime(access.grantedAt), reviewDueDate: access.reviewDueDate ? dayjs(access.reviewDueDate) : null });
    else form.setFieldsValue({ employeeId, status: 'Active', grantedAt: dayjs() });
  }, [open, access, employeeId, form]);
  const save = useApiMutation((v: any) => {
    const body = { ...v, grantedAt: toApiDateTime(v.grantedAt), reviewDueDate: toApiDate(v.reviewDueDate) };
    return access ? put(`/access/${access.id}`, body) : post('/access', body);
  }, { invalidate: [...invalidate, ['access']] as never, onSuccess: onClose });
  return (
    <Modal open={open} onCancel={onClose} onOk={() => form.submit()} confirmLoading={save.isPending} title={access ? t('access.edit') : t('access.grant')} width={640} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Form.Item name="employeeId" label={t('access.employee')} rules={[{ required: true }]}><EmployeeSelect disabled={!!employeeId || !!access} initialLabel={access?.employeeName} /></Form.Item>
        <Form.Item name="accessSystemId" label={t('access.system')} rules={[{ required: true }]}><LookupSelect lookup="access-systems" /></Form.Item>
        <Form.Item name="accessLevelId" label={t('access.level')}><LookupSelect lookup="access-levels" filter={(l) => !l.accessSystemId || l.accessSystemId === systemId} /></Form.Item>
        <Form.Item name="username" label={t('access.username')}><Input /></Form.Item>
        <Form.Item name="role" label={t('access.role')}><Input /></Form.Item>
        <Form.Item name="grantedAt" label={t('access.grantedAt')}><DatePicker showTime format="DD.MM.YYYY HH:mm" /></Form.Item>
        <Form.Item name="status" label={t('common.status')}><Select options={ACCESS_STATUSES.filter((s) => s !== 'Revoked').map((s) => ({ value: s, label: t(`enums.accessStatus.${s}`) }))} /></Form.Item>
        <Form.Item name="responsibleEmployeeId" label={t('common.responsible')}><EmployeeSelect initialLabel={access?.responsibleName} /></Form.Item>
        <Form.Item name="requestReference" label={t('access.request')}><Input /></Form.Item>
        <Form.Item name="reviewDueDate" label={t('access.reviewDue')}><DatePicker format="DD.MM.YYYY" /></Form.Item>
        <Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item>
        <CustomFieldsFormItems entity="Access" />
      </Form>
    </Modal>
  );
}
