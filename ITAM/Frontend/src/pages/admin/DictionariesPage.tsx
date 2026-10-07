import { Button, Card, Checkbox, Col, ColorPicker, Form, Input, InputNumber, Menu, Modal, Row, Select, Space, Switch, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import type { LookupItem } from '@/api/types';
import { CustomFieldsFormItems } from '@/components/CustomFields';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, LookupSelect } from '@/components/Selects';
import { fmtDateTime } from '@/utils/format';

interface FieldDef { name: string; type: 'enum' | 'ref' | 'bool' | 'number' | 'date' | 'string'; nullable: boolean; enumValues?: string[] }
interface Definition { key: string; title: string; canView: boolean; canManage: boolean; fields: FieldDef[]; hasCustomFields: boolean }

const REF_LOOKUPS: Record<string, string> = {
  regionId: 'regions', categoryId: 'asset-categories', accessSystemId: 'access-systems', departmentId: 'departments', positionId: 'positions', supplierId: 'suppliers',
};
const CF_ENTITY: Record<string, 'Location' | 'Department' | 'Software'> = { locations: 'Location', departments: 'Department', software: 'Software' };

export const useDefinitions = () => useQuery<Definition[]>({ queryKey: ['lookup-definitions'], queryFn: () => get('/lookups'), staleTime: 10 * 60_000 });

function FieldInput({ field, lookupKey }: { field: FieldDef; lookupKey: string }) {
  const { t } = useTranslation();
  if (field.type === 'enum') return <Select allowClear={field.nullable} options={field.enumValues!.map((v) => ({ value: v, label: t(`dict.enum.${field.name}.${v}`, { defaultValue: t(`enums.${field.name}.${v}`, { defaultValue: v }) }) }))} />;
  if (field.type === 'bool') return <Switch />;
  if (field.type === 'number') return <InputNumber style={{ width: '100%' }} />;
  if (field.type === 'ref') {
    if (field.name === 'headEmployeeId') return <EmployeeSelect />;
    const target = field.name === 'parentId' ? lookupKey : REF_LOOKUPS[field.name];
    return target ? <LookupSelect lookup={target} /> : <Input />;
  }
  if (field.name === 'color') return <ColorPickerInput />;
  return <Input />;
}

function ColorPickerInput({ value, onChange }: { value?: string; onChange?: (v: string) => void }) {
  return <ColorPicker value={value} onChange={(c) => onChange?.(c.toHexString())} showText />;
}

/** Generic dictionary table + editor driven by server definitions (no hard-coded reference data). */
export function DictionaryTable({ lookupKey, onOpen }: { lookupKey: string; onOpen?: (i: LookupItem) => void }) {
  const { t } = useTranslation();
  const defs = useDefinitions();
  const def = defs.data?.find((d) => d.key === lookupKey);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [editing, setEditing] = useState<LookupItem | null>();
  const [form] = Form.useForm();
  const save = useApiMutation((v: any) => (editing ? put(`/lookups/${lookupKey}/${editing.id}`, v) : post(`/lookups/${lookupKey}`, v)), {
    invalidate: [[`dict-${lookupKey}`], ['lookup-options', lookupKey]], onSuccess: () => setEditing(undefined),
  });
  const archive = useApiMutation(({ id, restore }: { id: string; restore: boolean }) => post(`/lookups/${lookupKey}/${id}/${restore ? 'restore' : 'archive'}`), {
    invalidate: [[`dict-${lookupKey}`], ['lookup-options', lookupKey]],
  });
  if (!def) return null;
  const fieldLabel = (n: string) => t(`dict.field.${n}`, { defaultValue: n });
  const columns: DataColumn<LookupItem>[] = [
    { key: 'name', title: t('common.name'), dataIndex: 'name', sorter: true, alwaysVisible: true, render: (v, r) => <Space>{onOpen ? <a onClick={() => onOpen(r)}>{(r.fullPath as string) || v}</a> : (r.fullPath as string) || v}{r.isArchived && <Tag>{t('common.archived')}</Tag>}</Space> },
    { key: 'code', title: t('common.code'), dataIndex: 'code', sorter: true },
    ...def.fields.filter((f) => f.name !== 'isSystem' && f.name !== 'description').map((f) => ({
      key: f.name, title: fieldLabel(f.name), hiddenByDefault: def.fields.length > 6 && !['type', 'kind', 'stage', 'prefix', 'regionId', 'model'].includes(f.name),
      render: (_: unknown, r: LookupItem) => {
        const v = r[f.name];
        if (f.type === 'ref') return r[f.name.replace(/Id$/, 'Name')] ?? '';
        if (f.type === 'bool') return v ? t('common.yes') : '';
        if (f.type === 'enum') return v ? <Tag>{t(`dict.enum.${f.name}.${v}`, { defaultValue: t(`enums.${f.name}.${v}`, { defaultValue: v }) })}</Tag> : '';
        if (f.name === 'color' && v) return <Tag color={v}>{v}</Tag>;
        return v ?? '';
      },
    })),
    { key: 'description', title: t('common.description'), dataIndex: 'description', hiddenByDefault: true },
    { key: 'sortOrder', title: t('dict.field.sortOrder'), dataIndex: 'sortOrder', sorter: true, hiddenByDefault: true },
    { key: 'updatedAt', title: t('common.updatedAt'), render: (_, r) => fmtDateTime(r.updatedAt ?? r.createdAt), hiddenByDefault: true },
    {
      key: 'actions', title: '', alwaysVisible: true, render: (_, r) => def.canManage && (
        <Space>
          <Button size="small" onClick={() => { setEditing(r); form.resetFields(); form.setFieldsValue({ ...r, customFields: r.customFields ?? {} }); }}>{t('common.edit')}</Button>
          {!r.isSystem && <Button size="small" onClick={() => archive.mutate({ id: r.id, restore: r.isArchived })}>{r.isArchived ? t('common.restore') : t('common.archive')}</Button>}
        </Space>
      ),
    },
  ];
  return (
    <Card title={def.title} extra={def.canManage && <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); }}>{t('common.add')}</Button>}>
      <DataTable<LookupItem> id={`dict-${lookupKey}`} url={`/lookups/${lookupKey}`} columns={columns} params={{ includeArchived }} size="small"
        filters={<Checkbox checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)}>{t('common.showArchived')}</Checkbox>} />
      <Modal open={editing !== undefined} title={editing ? editing.name : t('common.add')} onCancel={() => setEditing(undefined)} onOk={() => form.submit()} confirmLoading={save.isPending} width={680} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Row gutter={12}>
            <Col span={16}><Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="code" label={t('common.code')}><Input /></Form.Item></Col>
            {def.fields.filter((f) => f.name !== 'isSystem' && !(editing?.isSystem && ['kind', 'stage'].includes(f.name))).map((f) => (
              <Col span={12} key={f.name}>
                <Form.Item name={f.name} label={fieldLabel(f.name)} valuePropName={f.type === 'bool' ? 'checked' : 'value'}
                  rules={[{ required: !f.nullable && f.type !== 'bool' && f.type !== 'number', message: t('common.required') }]}>
                  <FieldInput field={f} lookupKey={lookupKey} />
                </Form.Item>
              </Col>
            ))}
            <Col span={12}><Form.Item name="sortOrder" label={t('dict.field.sortOrder')}><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={24}><Form.Item name="description" label={t('common.description')}><Input.TextArea rows={2} /></Form.Item></Col>
          </Row>
          {CF_ENTITY[lookupKey] && <CustomFieldsFormItems entity={CF_ENTITY[lookupKey]} />}
        </Form>
      </Modal>
    </Card>
  );
}

const GROUPS: { title: string; keys: string[] }[] = [
  { title: 'dict.group.org', keys: ['regions', 'locations', 'departments', 'positions'] },
  { title: 'dict.group.employees', keys: ['employee-statuses'] },
  { title: 'dict.group.assets', keys: ['asset-categories', 'asset-types', 'asset-statuses', 'manufacturers', 'suppliers', 'repair-statuses', 'stock-items'] },
  { title: 'dict.group.licenses', keys: ['software', 'license-types'] },
  { title: 'dict.group.access', keys: ['access-systems', 'access-levels'] },
];

export default function DictionariesPage() {
  const { t } = useTranslation();
  const { key } = useParams<{ key: string }>();
  const navigate = useNavigate();
  const defs = useDefinitions();
  const visible = (k: string) => defs.data?.find((d) => d.key === k)?.canView;
  const current = key ?? GROUPS.flatMap((g) => g.keys).find(visible) ?? 'regions';
  return (
    <>
      <PageHeader title={t('menu.dictionaries')} crumbs={[{ title: t('menu.admin') }, { title: t('menu.dictionaries') }]} />
      <Row gutter={16}>
        <Col xs={24} md={6} xl={5}>
          <Card size="small" styles={{ body: { padding: 0 } }}>
            <Menu mode="inline" selectedKeys={[current]} onClick={(e) => navigate(`/admin/dictionaries/${e.key}`)}
              items={GROUPS.map((g) => ({
                type: 'group' as const, key: g.title, label: t(g.title),
                children: g.keys.filter(visible).map((k) => ({ key: k, label: defs.data?.find((d) => d.key === k)?.title })),
              })).filter((g) => g.children.length > 0)} />
          </Card>
        </Col>
        <Col xs={24} md={18} xl={19}>
          <DictionaryTable key={current} lookupKey={current} />
        </Col>
      </Row>
    </>
  );
}
