import { Checkbox, Col, DatePicker, Form, Input, InputNumber, Modal, Row } from 'antd';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import type { Repair } from '@/api/types';
import { CustomFieldsFormItems } from '@/components/CustomFields';
import { AssetSelect, LookupSelect } from '@/components/Selects';
import { dayjs, defaultCurrency, nowInTz, parseDateTime, toApiDate, toApiDateTime } from '@/utils/format';

export function RepairForm({ open, assetId, repair, onClose, onSaved }: { open: boolean; assetId?: string; repair?: Repair; onClose: () => void; onSaved?: (r: Repair) => void }) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  useEffect(() => {
    if (!open) return;
    form.resetFields();
    if (repair) form.setFieldsValue({ ...repair, openedAt: parseDateTime(repair.openedAt), sentAt: parseDateTime(repair.sentAt), expectedReturnDate: repair.expectedReturnDate ? dayjs(repair.expectedReturnDate) : null });
    else form.setFieldsValue({ assetId, openedAt: nowInTz(), currency: defaultCurrency() });
  }, [open, repair, assetId, form]);
  const save = useApiMutation((v: any) => {
    const body = { ...v, assetId: repair?.assetId ?? v.assetId, openedAt: toApiDateTime(v.openedAt), sentAt: toApiDateTime(v.sentAt), expectedReturnDate: toApiDate(v.expectedReturnDate), version: repair?.version };
    return repair ? put<Repair>(`/repairs/${repair.id}`, body) : post<Repair>('/repairs', body);
  }, { invalidate: [['repairs'], ['repair', repair?.id], ['asset', assetId ?? repair?.assetId]], onSuccess: (r) => { onSaved?.(r); onClose(); } });
  return (
    <Modal open={open} onCancel={onClose} onOk={() => form.submit()} confirmLoading={save.isPending} width={760} title={repair ? `${t('repairs.edit')} ${repair.number}` : t('repairs.new')} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Row gutter={12}>
          {!repair && <Col span={24}><Form.Item name="assetId" label={t('repairs.asset')} rules={[{ required: true }]}><AssetSelect disabled={!!assetId} /></Form.Item></Col>}
          {!repair && <Col span={12}><Form.Item name="openedAt" label={t('repairs.openedAt')} extra={t('operations.backdateHint')}><DatePicker showTime format="DD.MM.YYYY HH:mm" style={{ width: '100%' }} /></Form.Item></Col>}
          <Col span={12}><Form.Item name="serviceCenterId" label={t('repairs.serviceCenter')}><LookupSelect lookup="suppliers" /></Form.Item></Col>
          <Col span={24}><Form.Item name="problem" label={t('repairs.problem')} rules={[{ required: true }]}><Input.TextArea rows={2} /></Form.Item></Col>
          <Col span={12}><Form.Item name="diagnosis" label={t('repairs.diagnosis')}><Input.TextArea rows={2} /></Form.Item></Col>
          <Col span={12}><Form.Item name="repairDescription" label={t('repairs.description')}><Input.TextArea rows={2} /></Form.Item></Col>
          <Col span={12}><Form.Item name="parts" label={t('repairs.parts')}><Input.TextArea rows={2} /></Form.Item></Col>
          <Col span={12}><Form.Item name="technician" label={t('repairs.technician')}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="sentAt" label={t('repairs.sentAt')}><DatePicker showTime format="DD.MM.YYYY HH:mm" style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={8}><Form.Item name="expectedReturnDate" label={t('repairs.expectedReturn')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={5}><Form.Item name="cost" label={t('repairs.cost')}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={3}><Form.Item name="currency" label=" "><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="isWarranty" valuePropName="checked"><Checkbox>{t('repairs.warranty')}</Checkbox></Form.Item></Col>
          <Col span={24}><Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
        </Row>
        <CustomFieldsFormItems entity="Repair" />
      </Form>
    </Modal>
  );
}
