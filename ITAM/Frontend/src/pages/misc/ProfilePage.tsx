import { Button, Card, Col, Descriptions, Form, Input, InputNumber, Modal, Popconfirm, Row, Table, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { del, get, post } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import { PageHeader } from '@/components/PageHeader';
import { fmtDateTime } from '@/utils/format';
import { ChangePasswordForm } from './ChangePasswordPage';

interface Token { id: string; name: string; prefix: string; createdAt: string; expiresAt?: string; lastUsedAt?: string; revokedAt?: string }

export default function ProfilePage() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const notify = useNotify();
  const tokens = useQuery<Token[]>({ queryKey: ['tokens'], queryFn: () => get('/auth/tokens') });
  const [secret, setSecret] = useState<string>();
  const create = useApiMutation((v: { name: string; expiresInDays?: number }) => post<{ secret: string }>('/auth/tokens', v), {
    invalidate: [['tokens']],
    onSuccess: (r) => setSecret(r.secret),
  });
  const revoke = useApiMutation((id: string) => del(`/auth/tokens/${id}`), { invalidate: [['tokens']] });
  return (
    <>
      <PageHeader title={t('profile.title')} crumbs={[{ title: t('profile.title') }]} />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title={t('profile.account')}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('login.userName')}>{me?.userName}</Descriptions.Item>
              <Descriptions.Item label={t('common.name')}>{me?.displayName}</Descriptions.Item>
              <Descriptions.Item label={t('profile.roles')}>{me?.roles.map((r) => <Tag key={r}>{r}</Tag>)}</Descriptions.Item>
              <Descriptions.Item label={t('profile.regions')}>{me?.allRegions ? t('profile.allRegions') : me?.regions.map((r) => <Tag key={r.id}>{r.name}</Tag>)}</Descriptions.Item>
              <Descriptions.Item label={t('profile.lastLogin')}>{fmtDateTime(me?.lastLoginAt)}</Descriptions.Item>
              <Descriptions.Item label={t('profile.permissions')}>{me?.permissions.length}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={t('password.title')}>
            <ChangePasswordForm onDone={() => notify.success(t('password.changed'))} />
          </Card>
        </Col>
        <Col span={24}>
          <Card title={t('profile.tokens')} extra={<Typography.Text type="secondary">{t('profile.tokensHint')}</Typography.Text>}>
            <Form layout="inline" onFinish={(v) => create.mutate(v)} style={{ marginBottom: 16 }}>
              <Form.Item name="name" rules={[{ required: true }]}><Input placeholder={t('profile.tokenName')} /></Form.Item>
              <Form.Item name="expiresInDays"><InputNumber min={1} placeholder={t('profile.expiresDays')} /></Form.Item>
              <Button htmlType="submit" type="primary" loading={create.isPending}>{t('common.create')}</Button>
            </Form>
            <Table<Token> rowKey="id" size="small" dataSource={tokens.data} pagination={false}
              columns={[
                { title: t('common.name'), dataIndex: 'name' },
                { title: t('profile.prefix'), dataIndex: 'prefix', render: (v) => <span className="itam-mono">{v}…</span> },
                { title: t('common.createdAt'), dataIndex: 'createdAt', render: fmtDateTime },
                { title: t('profile.expires'), dataIndex: 'expiresAt', render: fmtDateTime },
                { title: t('profile.lastUsed'), dataIndex: 'lastUsedAt', render: fmtDateTime },
                { title: t('common.status'), render: (_, r) => (r.revokedAt ? <Tag>{t('profile.revoked')}</Tag> : <Tag color="green">{t('profile.active')}</Tag>) },
                { key: 'a', render: (_, r) => !r.revokedAt && <Popconfirm title={t('common.confirm')} onConfirm={() => revoke.mutate(r.id)}><Button danger size="small">{t('profile.revoke')}</Button></Popconfirm> },
              ]} />
          </Card>
        </Col>
      </Row>
      <Modal open={!!secret} onCancel={() => setSecret(undefined)} onOk={() => setSecret(undefined)} title={t('profile.tokenCreated')}>
        <Typography.Paragraph>{t('profile.tokenOnce')}</Typography.Paragraph>
        <Typography.Paragraph copyable code>{secret}</Typography.Paragraph>
      </Modal>
    </>
  );
}
