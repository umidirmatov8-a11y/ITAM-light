import { Alert, Button, Card, Form, Input, Typography } from 'antd';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { post, ApiError } from '@/api/client';
import { useAuth } from '@/app/auth';

export function ChangePasswordForm({ onDone }: { onDone?: () => void }) {
  const { t } = useTranslation();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();
  const submit = async (v: { currentPassword: string; newPassword: string }) => {
    setLoading(true);
    setError(undefined);
    try {
      await post('/auth/change-password', { currentPassword: v.currentPassword, newPassword: v.newPassword });
      form.resetFields();
      onDone?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };
  return (
    <Form form={form} layout="vertical" onFinish={submit} style={{ maxWidth: 420 }}>
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
      <Form.Item name="currentPassword" label={t('password.current')} rules={[{ required: true }]}><Input.Password autoComplete="current-password" /></Form.Item>
      <Form.Item name="newPassword" label={t('password.new')} rules={[{ required: true, min: 8 }]} extra={t('setup.passwordPolicy')}><Input.Password autoComplete="new-password" /></Form.Item>
      <Form.Item name="confirm" label={t('password.confirm')} dependencies={['newPassword']}
        rules={[{ required: true }, ({ getFieldValue }) => ({ validator: (_, v) => (v === getFieldValue('newPassword') ? Promise.resolve() : Promise.reject(t('setup.passwordMismatch'))) })]}>
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={loading}>{t('password.change')}</Button>
    </Form>
  );
}

export default function ChangePasswordPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { me, logout } = useAuth();
  return (
    <div className="itam-login-bg">
      <Card className="itam-login-card" style={{ maxWidth: 460 }}>
        <Typography.Title level={4}>{t('password.title')}</Typography.Title>
        {me?.mustChangePassword && <Alert type="warning" showIcon message={t('password.mustChange')} style={{ marginBottom: 16 }} />}
        <ChangePasswordForm onDone={async () => { await qc.invalidateQueries({ queryKey: ['me'] }); navigate('/'); }} />
        <Button type="link" onClick={logout} style={{ marginTop: 8, paddingLeft: 0 }}>{t('header.logout')}</Button>
      </Card>
    </div>
  );
}
