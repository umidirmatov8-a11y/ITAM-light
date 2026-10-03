import { Button, Card, Checkbox, Col, Form, Input, InputNumber, Modal, Row, Space, Table, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import type { CustomFieldDef } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect, LookupSelect } from '@/components/Selects';
import { CUSTOM_FIELD_ENTITIES, CUSTOM_FIELD_TYPES } from '@/utils/enums';

export default function CustomFieldsPage() {
  const { t } = useTranslation();
  const [entity, setEntity] = useState<string>();
  const [editing, setEditing] = useState<CustomFieldDef | null>();
  const [form] = Form.useForm();
  const type = Form.useWatch('dataType', form);
  const ent = Form.useWatch('entityType', form);
  const q = useQuery<CustomFieldDef[]>({ queryKey: ['cf-admin', entity], queryFn: () => get('/custom-fields', { entity, includeArchived: true }) });
  const save = useApiMutation((v: any) => {
    const body = { ...v, options: typeof v.options === 'string' ? v.options.split('\n').map((s: string) => s.trim()).filter(Boolean) : v.options };
    return editing ? put(`/custom-fields/${editing.id}`, body) : post('/custom-fields', body);
  }, { invalidate: [['cf-admin'], ['custom-fields']], onSuccess: () => setEditing(undefined) });
  const archive = useApiMutation((r: CustomFieldDef) => post(`/custom-fields/${r.id}/archive?archived=${!r.isArchived}`), { invalidate: [['cf-admin'], ['custom-fields']] });
  return (
    <>
      <PageHeader title={t('menu.customFields')} crumbs={[{ title: t('menu.admin') }, { title: t('menu.customFields') }]}
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); form.setFieldsValue({ entityType: entity ?? 'Asset', dataType: 'Text' }); }}>{t('common.add')}</Button>} />
      <Card>
        <Space style={{ marginBottom: 12 }}><EnumSelect group="cfEntity" values={CUSTOM_FIELD_ENTITIES} placeholder={t('customFields.entity')} style={{ width: 200 }} onChange={setEntity} /></Space>
        <Table<CustomFieldDef> rowKey="id" size="small" loading={q.isLoading} dataSource={q.data} pagination={false} rowClassName={(r) => (r.isArchived ? 'itam-cancelled' : '')}
          columns={[
            { title: t('customFields.entity'), dataIndex: 'entityType', render: (v) => t(`enums.cfEntity.${v}`) },
            { title: t('customFields.assetType'), dataIndex: 'assetTypeName' },
            { title: t('customFields.label'), dataIndex: 'label' },
            { title: t('customFields.key'), dataIndex: 'key', render: (v) => <span className="itam-mono">{v}</span> },
            { title: t('customFields.type'), dataIndex: 'dataType', render: (v) => <Tag>{t(`enums.cfType.${v}`)}</Tag> },
            { title: t('customFields.required'), dataIndex: 'isRequired', render: (v) => (v ? t('common.yes') : '') },
            { title: t('customFields.group'), dataIndex: 'group' },
            { title: t('customFields.placeholder'), render: (_, r) => <span className="itam-mono itam-muted">{`{{${r.entityType}.Custom.${r.key}}}`}</span> },
            { key: 'a', render: (_, r) => <Space>
              <Button size="small" onClick={() => { setEditing(r); form.setFieldsValue({ ...r, options: r.options.join('\n') }); }}>{t('common.edit')}</Button>
              <Button size="small" onClick={() => archive.mutate(r)}>{r.isArchived ? t('common.restore') : t('common.archive')}</Button>
            </Space> },
          ]} />
      </Card>
      <Modal open={editing !== undefined} title={editing ? editing.label : t('common.add')} onCancel={() => setEditing(undefined)} onOk={() => form.submit()} confirmLoading={save.isPending} width={640} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="entityType" label={t('customFields.entity')} rules={[{ required: true }]}><EnumSelect group="cfEntity" values={CUSTOM_FIELD_ENTITIES} disabled={!!editing} /></Form.Item></Col>
            <Col span={12}>{ent === 'Asset' && <Form.Item name="assetTypeId" label={t('customFields.assetType')} extra={t('customFields.assetTypeHint')}><LookupSelect lookup="asset-types" disabled={!!editing} /></Form.Item>}</Col>
            <Col span={12}><Form.Item name="label" label={t('customFields.label')} rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="key" label={t('customFields.key')} rules={[{ required: true, pattern: /^[A-Za-z][A-Za-z0-9_]*$/ }]} extra={t('customFields.keyHint')}><Input disabled={!!editing} className="itam-mono" /></Form.Item></Col>
            <Col span={12}><Form.Item name="dataType" label={t('customFields.type')} rules={[{ required: true }]}><EnumSelect group="cfType" values={CUSTOM_FIELD_TYPES} allowClear={false} /></Form.Item></Col>
            <Col span={12}><Form.Item name="group" label={t('customFields.group')}><Input /></Form.Item></Col>
            {(type === 'Dropdown' || type === 'MultiSelect') && <Col span={24}><Form.Item name="options" label={t('customFields.options')} rules={[{ required: true }]} extra={t('customFields.optionsHint')}><Input.TextArea rows={4} /></Form.Item></Col>}
            <Col span={12}><Form.Item name="defaultValue" label={t('customFields.default')}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="sortOrder" label={t('dict.field.sortOrder')}><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={24}><Form.Item name="helpText" label={t('customFields.help')}><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="isRequired" valuePropName="checked"><Checkbox>{t('customFields.required')}</Checkbox></Form.Item></Col>
            <Col span={8}><Form.Item name="showInList" valuePropName="checked"><Checkbox>{t('customFields.showInList')}</Checkbox></Form.Item></Col>
            <Col span={8}><Form.Item name="isSearchable" valuePropName="checked"><Checkbox>{t('customFields.searchable')}</Checkbox></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
    </>
  );
}
