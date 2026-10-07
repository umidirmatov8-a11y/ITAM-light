import { Col, DatePicker, Form, Input, InputNumber, Modal, Row, Select } from 'antd';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import type { License } from '@/api/types';
import { CustomFieldsFormItems } from '@/components/CustomFields';
import { EnumSelect, LookupSelect } from '@/components/Selects';
import { LICENSE_MODELS } from '@/utils/enums';
import { dayjs, defaultCurrency, toApiDate } from '@/utils/format';

export function LicenseForm({ open, license, onClose, onSaved }: { open: boolean; license?: License; onClose: () => void; onSaved?: (l: License) => void }) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  useEffect(() => {
    if (!open) return;
    form.resetFields();
    const d = (v?: string) => (v ? dayjs(v) : null);
    if (license) form.setFieldsValue({ ...license, licenseKey: undefined, purchaseDate: d(license.purchaseDate), expirationDate: d(license.expirationDate), renewalDate: d(license.renewalDate) });
    else form.setFieldsValue({ seats: 1, model: 'PerUser', currency: defaultCurrency() });
  }, [open, license, form]);
  const save = useApiMutation((v: any) => {
    const body = { ...v, purchaseDate: toApiDate(v.purchaseDate), expirationDate: toApiDate(v.expirationDate), renewalDate: toApiDate(v.renewalDate), version: license?.version };
    return license ? put<License>(`/licenses/${license.id}`, body) : post<License>('/licenses', body);
  }, { invalidate: [['licenses'], ['license', license?.id]], onSuccess: (l) => { onSaved?.(l); onClose(); } });
  return (
    <Modal open={open} onCancel={onClose} onOk={() => form.submit()} confirmLoading={save.isPending} width={760} title={license ? t('licenses.edit') : t('licenses.new')} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Row gutter={12}>
          <Col span={24}><Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}><Input /></Form.Item></Col>
          <Col span={12}><Form.Item name="softwareId" label={t('licenses.software')}><LookupSelect lookup="software" /></Form.Item></Col>
          <Col span={12}><Form.Item name="licenseTypeId" label={t('licenses.type')}><LookupSelect lookup="license-types" onChange={() => undefined} /></Form.Item></Col>
          <Col span={8}><Form.Item name="model" label={t('licenses.model')} rules={[{ required: true }]}><EnumSelect group="licenseModel" values={LICENSE_MODELS} allowClear={false} /></Form.Item></Col>
          <Col span={8}><Form.Item name="seats" label={t('licenses.seats')} rules={[{ required: true }]}><InputNumber min={1} style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={8}><Form.Item name="regionId" label={t('common.region')}><LookupSelect lookup="regions" /></Form.Item></Col>
          <Col span={12}><Form.Item name="vendorId" label={t('licenses.vendor')}><LookupSelect lookup="suppliers" /></Form.Item></Col>
          <Col span={12}><Form.Item name="supplierId" label={t('assets.supplier')}><LookupSelect lookup="suppliers" /></Form.Item></Col>
          <Col span={24}><Form.Item name="licenseKey" label={t('licenses.key')} extra={license ? t('licenses.keyKeep') : t('licenses.keyHint')}><Input.Password autoComplete="off" /></Form.Item></Col>
          <Col span={8}><Form.Item name="purchaseDate" label={t('assets.purchaseDate')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={8}><Form.Item name="expirationDate" label={t('licenses.expiration')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={8}><Form.Item name="renewalDate" label={t('licenses.renewal')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={8}><Form.Item name="cost" label={t('assets.price')}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={4}><Form.Item name="currency" label={t('assets.currency')}><Select options={['UZS', 'USD', 'EUR', 'RUB'].map((c) => ({ value: c, label: c }))} /></Form.Item></Col>
          <Col span={12}><Form.Item name="contractNumber" label={t('licenses.contract')}><Input /></Form.Item></Col>
          <Col span={24}><Form.Item name="notes" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
        </Row>
        <CustomFieldsFormItems entity="License" />
      </Form>
    </Modal>
  );
}
