import { Button, Card, Checkbox, Col, Form, Input, Modal, Popconfirm, Row, Select, Space, Table, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { del, get, post, put, type Paged } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, LookupSelect } from '@/components/Selects';
import { fmtDateTime } from '@/utils/format';

interface User { id: string; userName: string; displayName: string; email?: string; isActive: boolean; isLocked: boolean; lastLoginAt?: string; lastLoginIp?: string;
  mustChangePassword: boolean; allRegions: boolean; authProvider: string; employeeId?: string; employeeName?: string; roles: { id: string; name: string }[]; regions: { id: string; name: string }[] }
interface Session { id: string; userName: string; createdAt: string; lastSeenAt: string; expiresAt: string; ipAddress?: string; userAgent?: string; isCurrent: boolean }

export default function UsersPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [inactive, setInactive] = useState(false);
  const [editing, setEditing] = useState<User | null>();
  const [reset, setReset] = useState<User>();
  const [form] = Form.useForm();
  const [resetForm] = Form.useForm();
  const allRegions = Form.useWatch('allRegions', form);
  const q = useQuery<Paged<User>>({ queryKey: ['users', search, inactive], queryFn: () => get('/admin/users', { search, includeArchived: inactive, pageSize: 200 }) });
  const roles = useQuery<{ id: string; name: string }[]>({ queryKey: ['role-options'], queryFn: () => get('/admin/roles/options') });
  const sessions = useQuery<Session[]>({ queryKey: ['sessions'], queryFn: () => get('/admin/users/sessions') });
  const save = useApiMutation((v: any) => (editing ? put(`/admin/users/${editing.id}`, v) : post('/admin/users', v)), { invalidate: [['users']], onSuccess: () => setEditing(undefined) });
  const resetPwd = useApiMutation((v: any) => post(`/admin/users/${reset!.id}/reset-password`, v), { invalidate: [['users'], ['sessions']], onSuccess: () => setReset(undefined) });
  const unlock = useApiMutation((id: string) => post(`/admin/users/${id}/unlock`), { invalidate: [['users']] });
  const remove = useApiMutation((id: string) => del(`/admin/users/${id}`), { invalidate: [['users']] });
  const revoke = useApiMutation((id: string) => del(`/admin/users/sessions/${id}`), { invalidate: [['sessions']] });
  return (
    <>
      <PageHeader title={t('menu.users')} crumbs={[{ title: t('menu.admin') }, { title: t('menu.users') }]}
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); form.setFieldsValue({ isActive: true, mustChangePassword: true, roleIds: [], regionIds: [] }); }}>{t('users.new')}</Button>} />
      <Card style={{ marginBottom: 16 }}>
        <Space style={{ marginBottom: 12 }}><Input.Search allowClear onSearch={setSearch} placeholder={t('common.search')} /><Checkbox checked={inactive} onChange={(e) => setInactive(e.target.checked)}>{t('users.showInactive')}</Checkbox></Space>
        <Table<User> rowKey="id" size="small" loading={q.isLoading} dataSource={q.data?.items} pagination={false} scroll={{ x: 'max-content' }}
          columns={[
            { title: t('login.userName'), dataIndex: 'userName', render: (v, r) => <Space>{v}{!r.isActive && <Tag>{t('users.disabled')}</Tag>}{r.isLocked && <Tag color="red">{t('users.locked')}</Tag>}</Space> },
            { title: t('common.name'), dataIndex: 'displayName' },
            { title: t('profile.roles'), render: (_, r) => r.roles.map((x) => <Tag key={x.id}>{x.name}</Tag>) },
            { title: t('profile.regions'), render: (_, r) => (r.allRegions ? <Tag color="blue">{t('profile.allRegions')}</Tag> : r.regions.map((x) => <Tag key={x.id}>{x.name}</Tag>)) },
            { title: t('users.employee'), dataIndex: 'employeeName' },
            { title: t('profile.lastLogin'), render: (_, r) => <>{fmtDateTime(r.lastLoginAt)} <span className="itam-muted">{r.lastLoginIp}</span></> },
            { key: 'a', render: (_, r) => <Space>
              <Button size="small" onClick={() => { setEditing(r); form.setFieldsValue({ ...r, roleIds: r.roles.map((x) => x.id), regionIds: r.regions.map((x) => x.id) }); }}>{t('common.edit')}</Button>
              <Button size="small" onClick={() => { setReset(r); resetForm.resetFields(); }}>{t('users.resetPassword')}</Button>
              {r.isLocked && <Button size="small" onClick={() => unlock.mutate(r.id)}>{t('users.unlock')}</Button>}
              <Popconfirm title={t('common.confirmDelete')} onConfirm={() => remove.mutate(r.id)}><Button size="small" danger>{t('common.delete')}</Button></Popconfirm>
            </Space> },
          ]} />
      </Card>
      <Card title={t('users.sessions')}>
        <Table<Session> rowKey="id" size="small" dataSource={sessions.data} pagination={{ pageSize: 20 }} scroll={{ x: 'max-content' }}
          columns={[
            { title: t('login.userName'), dataIndex: 'userName', render: (v, r) => <>{v} {r.isCurrent && <Tag color="green">{t('users.current')}</Tag>}</> },
            { title: 'IP', dataIndex: 'ipAddress' },
            { title: t('users.started'), dataIndex: 'createdAt', render: fmtDateTime },
            { title: t('users.lastSeen'), dataIndex: 'lastSeenAt', render: fmtDateTime },
            { title: t('profile.expires'), dataIndex: 'expiresAt', render: fmtDateTime },
            { title: 'User-Agent', dataIndex: 'userAgent', ellipsis: true, width: 260 },
            { key: 'a', render: (_, r) => !r.isCurrent && <Button size="small" danger onClick={() => revoke.mutate(r.id)}>{t('users.endSession')}</Button> },
          ]} />
      </Card>
      <Modal open={editing !== undefined} title={editing ? editing.userName : t('users.new')} onCancel={() => setEditing(undefined)} onOk={() => form.submit()} confirmLoading={save.isPending} width={680} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="userName" label={t('login.userName')} rules={[{ required: true, pattern: /^[A-Za-z0-9._@-]+$/ }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="displayName" label={t('common.name')} rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="email" label="Email" rules={[{ type: 'email' }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="employeeId" label={t('users.employee')} extra={t('users.employeeHint')}><EmployeeSelect initialLabel={editing?.employeeName} /></Form.Item></Col>
            {!editing && <Col span={12}><Form.Item name="password" label={t('login.password')} rules={[{ required: true }]} extra={t('setup.passwordPolicy')}><Input.Password autoComplete="new-password" /></Form.Item></Col>}
            <Col span={24}><Form.Item name="roleIds" label={t('profile.roles')}><Select mode="multiple" options={(roles.data ?? []).map((r) => ({ value: r.id, label: r.name }))} /></Form.Item></Col>
            <Col span={24}><Form.Item name="allRegions" valuePropName="checked"><Checkbox>{t('profile.allRegions')}</Checkbox></Form.Item></Col>
            {!allRegions && <Col span={24}><Form.Item name="regionIds" label={t('profile.regions')} extra={t('users.regionsHint')}><LookupSelect lookup="regions" mode="multiple" /></Form.Item></Col>}
            <Col span={12}><Form.Item name="isActive" valuePropName="checked"><Checkbox>{t('users.active')}</Checkbox></Form.Item></Col>
            <Col span={12}><Form.Item name="mustChangePassword" valuePropName="checked"><Checkbox>{t('users.mustChange')}</Checkbox></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
      <Modal open={!!reset} title={`${t('users.resetPassword')}: ${reset?.userName}`} onCancel={() => setReset(undefined)} onOk={() => resetForm.submit()} confirmLoading={resetPwd.isPending}>
        <Form form={resetForm} layout="vertical" initialValues={{ mustChangePassword: true }} onFinish={(v) => resetPwd.mutate(v)}>
          <Form.Item name="newPassword" label={t('password.new')} rules={[{ required: true }]} extra={t('setup.passwordPolicy')}><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item name="mustChangePassword" valuePropName="checked"><Checkbox>{t('users.mustChange')}</Checkbox></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
