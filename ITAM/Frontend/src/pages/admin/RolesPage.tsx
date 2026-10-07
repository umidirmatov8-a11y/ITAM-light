import { Button, Card, Checkbox, Col, Form, Input, Modal, Popconfirm, Row, Space, Table, Tag, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { del, get, post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { PageHeader } from '@/components/PageHeader';

interface Role { id: string; name: string; code: string; description?: string; isSystem: boolean; permissions: string[]; userCount: number }
interface Perm { code: string; group: string; description: string }

export default function RolesPage() {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<Role | null>();
  const [form] = Form.useForm();
  const roles = useQuery<Role[]>({ queryKey: ['roles'], queryFn: () => get('/admin/roles') });
  const perms = useQuery<Perm[]>({ queryKey: ['permissions'], queryFn: () => get('/admin/roles/permissions') });
  const groups = useMemo(() => Object.entries((perms.data ?? []).reduce<Record<string, Perm[]>>((a, p) => ((a[p.group] ??= []).push(p), a), {})), [perms.data]);
  const save = useApiMutation((v: any) => (editing ? put(`/admin/roles/${editing.id}`, v) : post('/admin/roles', v)), { invalidate: [['roles'], ['role-options']], onSuccess: () => setEditing(undefined) });
  const remove = useApiMutation((id: string) => del(`/admin/roles/${id}`), { invalidate: [['roles']] });
  return (
    <>
      <PageHeader title={t('menu.roles')} crumbs={[{ title: t('menu.admin') }, { title: t('menu.roles') }]}
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); form.setFieldsValue({ permissions: [] }); }}>{t('roles.new')}</Button>} />
      <Card>
        <Table<Role> rowKey="id" size="small" loading={roles.isLoading} dataSource={roles.data} pagination={false}
          columns={[
            { title: t('common.name'), dataIndex: 'name', render: (v, r) => <>{v} {r.isSystem && <Tag>{t('roles.system')}</Tag>}</> },
            { title: t('common.code'), dataIndex: 'code', render: (v) => <span className="itam-mono">{v}</span> },
            { title: t('common.description'), dataIndex: 'description' },
            { title: t('profile.permissions'), render: (_, r) => r.permissions.length },
            { title: t('roles.users'), dataIndex: 'userCount' },
            { key: 'a', render: (_, r) => <Space>
              <Button size="small" onClick={() => { setEditing(r); form.setFieldsValue(r); }}>{t('common.edit')}</Button>
              {!r.isSystem && <Popconfirm title={t('common.confirmDelete')} onConfirm={() => remove.mutate(r.id)}><Button size="small" danger>{t('common.delete')}</Button></Popconfirm>}
            </Space> },
          ]} />
      </Card>
      <Modal open={editing !== undefined} title={editing?.name ?? t('roles.new')} width={960} onCancel={() => setEditing(undefined)} onOk={() => form.submit()} confirmLoading={save.isPending} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Row gutter={12}>
            <Col span={8}><Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="code" label={t('common.code')} rules={[{ required: true, pattern: /^[a-z0-9_-]+$/ }]}><Input disabled={editing?.isSystem} /></Form.Item></Col>
            <Col span={10}><Form.Item name="description" label={t('common.description')}><Input /></Form.Item></Col>
          </Row>
          <Form.Item name="permissions" label={t('profile.permissions')}>
            <Checkbox.Group style={{ width: '100%' }}>
              <Row gutter={[16, 8]}>
                {groups.map(([g, list]) => (
                  <Col xs={24} md={12} xl={8} key={g}>
                    <Typography.Text strong>{g}</Typography.Text>
                    {list.map((p) => <div key={p.code}><Checkbox value={p.code}>{p.description} <span className="itam-mono itam-muted" style={{ fontSize: 11 }}>{p.code}</span></Checkbox></div>)}
                  </Col>
                ))}
              </Row>
            </Checkbox.Group>
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
