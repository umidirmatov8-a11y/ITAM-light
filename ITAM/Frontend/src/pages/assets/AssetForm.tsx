import { Button, Col, DatePicker, Divider, Drawer, Form, Input, InputNumber, Row, Select, Space } from 'antd';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { Asset } from '@/api/types';
import { CustomFieldsFormItems } from '@/components/CustomFields';
import { AssetSelect, EmployeeSelect, EnumSelect, LookupSelect } from '@/components/Selects';
import { CONDITIONS, DEPRECIATION_METHODS } from '@/utils/enums';
import { dayjs, defaultCurrency, toApiDate, toApiDateTime } from '@/utils/format';

export function AssetForm({ open, asset, onClose, onSaved }: { open: boolean; asset?: Asset; onClose: () => void; onSaved?: (a: Asset) => void }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [form] = Form.useForm();
  const typeId = Form.useWatch('assetTypeId', form);
  const regionId = Form.useWatch('regionId', form);
  const finance = can('assets.finance.view');

  useEffect(() => {
    if (!open) return;
    form.resetFields();
    if (asset)
      form.setFieldsValue({
        ...asset,
        purchaseDate: asset.purchaseDate ? dayjs(asset.purchaseDate) : null,
        warrantyExpiration: asset.warrantyExpiration ? dayjs(asset.warrantyExpiration) : null,
        customFields: asset.customFields ?? {},
      });
    else form.setFieldsValue({ currency: defaultCurrency(), condition: 'New', depreciationMethod: 'StraightLine' });
  }, [open, asset, form]);

  const save = useApiMutation(
    (v: any) => {
      const body = { ...v, purchaseDate: toApiDate(v.purchaseDate), warrantyExpiration: toApiDate(v.warrantyExpiration), registeredAt: toApiDateTime(v.registeredAt), version: asset?.version };
      return asset ? put<Asset>(`/assets/${asset.id}`, body) : post<Asset>('/assets', body);
    },
    { invalidate: [['assets'], ['asset', asset?.id]], onSuccess: (a) => { onSaved?.(a); onClose(); } },
  );

  return (
    <Drawer open={open} onClose={onClose} width={760} title={asset ? `${t('assets.edit')} ${asset.inventoryNumber}` : t('assets.new')} destroyOnHidden
      extra={<Space><Button onClick={onClose}>{t('common.cancel')}</Button><Button type="primary" loading={save.isPending} onClick={() => form.submit()}>{t('common.save')}</Button></Space>}>
      <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Row gutter={12}>
          <Col span={12}><Form.Item name="assetTypeId" label={t('assets.type')} rules={[{ required: true, message: t('common.required') }]}><LookupSelect lookup="asset-types" /></Form.Item></Col>
          <Col span={12}><Form.Item name="inventoryNumber" label={t('assets.inventoryNumber')} extra={!asset && t('assets.inventoryAuto')}><Input className="itam-mono" /></Form.Item></Col>
          <Col span={24}><Form.Item name="name" label={t('assets.name')} rules={[{ required: true, message: t('common.required') }]}><Input placeholder="Lenovo ThinkPad T14" /></Form.Item></Col>
          <Col span={8}><Form.Item name="manufacturerId" label={t('assets.manufacturer')}><LookupSelect lookup="manufacturers" /></Form.Item></Col>
          <Col span={8}><Form.Item name="model" label={t('assets.model')}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="serialNumber" label={t('assets.serialNumber')}><Input className="itam-mono" /></Form.Item></Col>
        </Row>
        {!asset && (
          <>
            <Divider orientation="left" plain>{t('assets.initialPlacement')}</Divider>
            <Row gutter={12}>
              <Col span={12}><Form.Item name="regionId" label={t('common.region')} rules={[{ required: true, message: t('common.required') }]}><LookupSelect lookup="regions" /></Form.Item></Col>
              <Col span={12}><Form.Item name="locationId" label={t('assets.location')}><LookupSelect lookup="locations" filter={(l) => !regionId || l.regionId === regionId} /></Form.Item></Col>
              <Col span={12}><Form.Item name="departmentId" label={t('common.department')}><LookupSelect lookup="departments" /></Form.Item></Col>
              <Col span={12}><Form.Item name="statusId" label={t('assets.initialStatus')}><LookupSelect lookup="asset-statuses" filter={(s) => ['InStock', 'Ordered', 'Reserved'].includes(s.kind)} /></Form.Item></Col>
              <Col span={12}><Form.Item name="registeredAt" label={t('assets.registeredAt')} extra={t('assets.registeredAtHint')}><DatePicker showTime format="DD.MM.YYYY HH:mm" style={{ width: '100%' }} /></Form.Item></Col>
            </Row>
          </>
        )}
        <Divider orientation="left" plain>{t('assets.accounting')}</Divider>
        <Row gutter={12}>
          <Col span={12}><Form.Item name="responsibleEmployeeId" label={t('assets.responsible')}><EmployeeSelect initialLabel={asset?.responsibleName} /></Form.Item></Col>
          <Col span={12}><Form.Item name="parentAssetId" label={t('assets.parent')}><AssetSelect /></Form.Item></Col>
          <Col span={8}><Form.Item name="purchaseDate" label={t('assets.purchaseDate')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Col>
          {finance && <Col span={8}><Form.Item name="purchasePrice" label={t('assets.price')}><InputNumber style={{ width: '100%' }} min={0} /></Form.Item></Col>}
          <Col span={8}><Form.Item name="currency" label={t('assets.currency')}><Select options={['UZS', 'USD', 'EUR', 'RUB'].map((c) => ({ value: c, label: c }))} /></Form.Item></Col>
          <Col span={8}><Form.Item name="supplierId" label={t('assets.supplier')}><LookupSelect lookup="suppliers" /></Form.Item></Col>
          <Col span={8}><Form.Item name="invoiceNumber" label={t('assets.invoice')}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="warrantyExpiration" label={t('assets.warranty')}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={8}><Form.Item name="depreciationMethod" label={t('assets.depreciationMethod')}><EnumSelect group="depreciation" values={DEPRECIATION_METHODS} allowClear={false} /></Form.Item></Col>
          <Col span={8}><Form.Item name="usefulLifeMonths" label={t('assets.usefulLife')}><InputNumber min={1} max={600} style={{ width: '100%' }} /></Form.Item></Col>
          {finance && <Col span={8}><Form.Item name="salvageValue" label={t('assets.salvage')}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>}
        </Row>
        <Divider orientation="left" plain>{t('assets.technical')}</Divider>
        <Row gutter={12}>
          <Col span={8}><Form.Item name="hostname" label="Hostname"><Input className="itam-mono" /></Form.Item></Col>
          <Col span={8}><Form.Item name="ipAddress" label="IP"><Input className="itam-mono" /></Form.Item></Col>
          <Col span={8}><Form.Item name="macAddress" label="MAC"><Input className="itam-mono" /></Form.Item></Col>
          <Col span={8}><Form.Item name="condition" label={t('assets.condition')}><EnumSelect group="condition" values={CONDITIONS} allowClear={false} /></Form.Item></Col>
          <Col span={24}><Form.Item name="notes" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
        </Row>
        <CustomFieldsFormItems entity="Asset" assetTypeId={typeId} />
      </Form>
    </Drawer>
  );
}
