import { Button, Card, Checkbox, Col, Form, Input, Modal, Row, Select, Space, Table, Tag } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect, LookupSelect } from '@/components/Selects';
import { CHECKLIST_ACTIONS } from '@/utils/enums';

interface Tpl { id: string; name: string; description?: string; kind: string; departmentId?: string; departmentName?: string; positionId?: string; positionName?: string;
  regionId?: string; regionName?: string; isDefault: boolean; isArchived: boolean; items: { id: string; title: string; description?: string; actionType: string; targetId?: string; targetName?: string; isRequired: boolean }[] }

const TARGET_LOOKUP: Record<string, string> = { IssueAssetType: 'asset-types', GrantAccess: 'access-systems', AssignSoftware: 'software' };

export default function ChecklistTemplatesPage() {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<Tpl | null>();
  const [form] = Form.useForm();
  const q = useQuery<Tpl[]>({ queryKey: ['checklist-templates'], queryFn: () => get('/checklists/templates', { includeArchived: true }) });
  const save = useApiMutation((v: any) => (editing ? put(`/checklists/templates/${editing.id}`, v) : post('/checklists/templates', v)), {
    invalidate: [['checklist-templates']], onSuccess: () => setEditing(undefined),
  });
  const archive = useApiMutation((r: Tpl) => post(`/checklists/templates/${r.id}/archive?archived=${!r.isArchived}`), { invalidate: [['checklist-templates']] });
  return (
    <>
      <PageHeader title={t('menu.checklistTemplates')} crumbs={[{ title: t('menu.admin') }, { title: t('menu.checklistTemplates') }]}
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); form.setFieldsValue({ kind: 'Onboarding', items: [{ actionType: 'Manual', isRequired: true }] }); }}>{t('common.add')}</Button>} />
      <Card>
        <Table<Tpl> rowKey="id" size="small" loading={q.isLoading} dataSource={q.data} pagination={false} rowClassName={(r) => (r.isArchived ? 'itam-cancelled' : '')}
          expandable={{ expandedRowRender: (r) => r.items.map((i) => <div key={i.id}>• {i.title} <Tag>{t(`enums.checklistAction.${i.actionType}`)}</Tag>{i.targetName && <Tag color="blue">{i.targetName}</Tag>}{i.isRequired && <Tag color="red">*</Tag>}</div>) }}
          columns={[
            { title: t('common.name'), dataIndex: 'name' },
            { title: t('checklists.kind'), dataIndex: 'kind', render: (v) => t(`enums.checklistKind.${v}`) },
            { title: t('checklists.applies'), render: (_, r) => [r.departmentName, r.positionName, r.regionName].filter(Boolean).join(' · ') || t('checklists.everyone') },
            { title: t('checklists.items'), render: (_, r) => r.items.length },
            { title: t('templates.default'), dataIndex: 'isDefault', render: (v) => v && <Tag color="blue">{t('templates.default')}</Tag> },
            { key: 'a', render: (_, r) => <Space>
              <Button size="small" onClick={() => { setEditing(r); form.setFieldsValue(r); }}>{t('common.edit')}</Button>
              <Button size="small" onClick={() => archive.mutate(r)}>{r.isArchived ? t('common.restore') : t('common.archive')}</Button>
            </Space> },
          ]} />
      </Card>
      <Modal open={editing !== undefined} title={editing?.name ?? t('common.add')} width={900} onCancel={() => setEditing(undefined)} onOk={() => form.submit()} confirmLoading={save.isPending} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="kind" label={t('checklists.kind')}><Select options={['Onboarding', 'Offboarding'].map((k) => ({ value: k, label: t(`enums.checklistKind.${k}`) }))} /></Form.Item></Col>
            <Col span={8}><Form.Item name="departmentId" label={t('common.department')}><LookupSelect lookup="departments" /></Form.Item></Col>
            <Col span={8}><Form.Item name="positionId" label={t('employees.position')}><LookupSelect lookup="positions" /></Form.Item></Col>
            <Col span={8}><Form.Item name="regionId" label={t('common.region')}><LookupSelect lookup="regions" /></Form.Item></Col>
            <Col span={24}><Form.Item name="isDefault" valuePropName="checked"><Checkbox>{t('templates.makeDefault')}</Checkbox></Form.Item></Col>
          </Row>
          <Form.List name="items">
            {(fields, { add, remove }) => (
              <>
                {fields.map((f) => (
                  <Row gutter={8} key={f.key} align="middle">
                    <Col span={9}><Form.Item name={[f.name, 'title']} rules={[{ required: true }]}><Input placeholder={t('checklists.itemTitle')} /></Form.Item></Col>
                    <Col span={6}><Form.Item name={[f.name, 'actionType']}><EnumSelect group="checklistAction" values={CHECKLIST_ACTIONS} allowClear={false} /></Form.Item></Col>
                    <Col span={6}>
                      <Form.Item noStyle shouldUpdate>
                        {() => {
                          const action = form.getFieldValue(['items', f.name, 'actionType']);
                          return TARGET_LOOKUP[action] ? <Form.Item name={[f.name, 'targetId']} rules={[{ required: true }]}><LookupSelect lookup={TARGET_LOOKUP[action]} /></Form.Item> : <div />;
                        }}
                      </Form.Item>
                    </Col>
                    <Col span={2}><Form.Item name={[f.name, 'isRequired']} valuePropName="checked"><Checkbox>*</Checkbox></Form.Item></Col>
                    <Col span={1}><Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(f.name)} /></Col>
                  </Row>
                ))}
                <Button onClick={() => add({ actionType: 'Manual', isRequired: true })} icon={<PlusOutlined />}>{t('checklists.addItem')}</Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </>
  );
}
