import { Checkbox, DatePicker, Descriptions, Form, Input, InputNumber, Select, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import { useCustomFields } from '@/api/hooks';
import type { CustomFieldDef, CustomFieldEntity } from '@/api/types';
import { dayjs, fmtDate, fmtDateTime, fmtNumber } from '@/utils/format';

/** Renders admin-defined custom fields inside an antd Form (values under "customFields"). */
export function CustomFieldsFormItems({ entity, assetTypeId }: { entity: CustomFieldEntity; assetTypeId?: string }) {
  const { t } = useTranslation();
  const q = useCustomFields(entity, assetTypeId);
  const defs = (q.data ?? []).filter((d) => !d.assetTypeId || d.assetTypeId === assetTypeId);
  if (defs.length === 0) return null;
  return (
    <>
      {defs.map((d) => (
        <Form.Item
          key={d.id}
          name={['customFields', d.key]}
          label={d.label}
          tooltip={d.helpText}
          rules={[{ required: d.isRequired, message: t('common.required') }]}
          valuePropName={d.dataType === 'Boolean' ? 'checked' : 'value'}
          getValueProps={d.dataType === 'Date' || d.dataType === 'DateTime' ? (v) => ({ value: v ? dayjs(v) : null }) : undefined}
          normalize={d.dataType === 'Date' ? (v) => (v ? dayjs(v).format('YYYY-MM-DD') : null) : d.dataType === 'DateTime' ? (v) => (v ? dayjs(v).toISOString() : null) : undefined}
        >
          {renderInput(d)}
        </Form.Item>
      ))}
    </>
  );
}

function renderInput(d: CustomFieldDef) {
  switch (d.dataType) {
    case 'Number':
    case 'Currency':
      return <InputNumber style={{ width: '100%' }} />;
    case 'Date':
      return <DatePicker style={{ width: '100%' }} format="DD.MM.YYYY" />;
    case 'DateTime':
      return <DatePicker showTime style={{ width: '100%' }} format="DD.MM.YYYY HH:mm" />;
    case 'Boolean':
      return <Checkbox />;
    case 'Dropdown':
      return <Select allowClear options={d.options.map((o) => ({ value: o, label: o }))} />;
    case 'MultiSelect':
      return <Select mode="multiple" allowClear options={d.options.map((o) => ({ value: o, label: o }))} />;
    case 'LongText':
      return <Input.TextArea rows={3} />;
    default:
      return <Input />;
  }
}

export function CustomFieldsView({ entity, assetTypeId, values }: { entity: CustomFieldEntity; assetTypeId?: string; values?: Record<string, unknown> | null }) {
  const { t } = useTranslation();
  const q = useCustomFields(entity, assetTypeId);
  const defs = (q.data ?? []).filter((d) => !d.assetTypeId || d.assetTypeId === assetTypeId);
  if (defs.length === 0) return null;
  const show = (d: CustomFieldDef) => {
    const v = values?.[d.key];
    if (v === undefined || v === null || v === '') return <span className="itam-muted">—</span>;
    switch (d.dataType) {
      case 'Boolean': return v ? t('common.yes') : t('common.no');
      case 'Date': return fmtDate(String(v));
      case 'DateTime': return fmtDateTime(String(v));
      case 'Number': case 'Currency': return fmtNumber(Number(v));
      case 'MultiSelect': return (v as string[]).map((x) => <Tag key={x}>{x}</Tag>);
      case 'Url': return <a href={String(v)} target="_blank" rel="noreferrer noopener">{String(v)}</a>;
      default: return String(v);
    }
  };
  return (
    <Descriptions size="small" column={{ xs: 1, sm: 1, md: 2 }} bordered title={t('common.customFields')} style={{ marginTop: 16 }}>
      {defs.map((d) => (
        <Descriptions.Item key={d.id} label={d.label}>{show(d)}</Descriptions.Item>
      ))}
    </Descriptions>
  );
}
