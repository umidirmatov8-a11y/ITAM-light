import { Alert, Button, Card, Form, Input, Select, Space, Typography } from 'antd';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useQueryClient, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { get, post, ApiError } from '@/api/client';
import { LANGUAGES, setLanguage } from '@/i18n';

export default function LoginPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const info = useQuery<{ organizationName: string; version: string }>({ queryKey: ['public-info'], queryFn: () => get('/public/info') });

  const onFinish = async (v: { userName: string; password: string }) => {
    setLoading(true);
    setError(undefined);
    try {
      await get('/auth/csrf');
      await post('/auth/login', v);
      await qc.invalidateQueries({ queryKey: ['me'] });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="itam-login-bg">
      <Card className="itam-login-card" variant="borderless">
        <Space direction="vertical" size={4} style={{ width: '100%', marginBottom: 20, textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <span className="itam-logo-mark" style={{ width: 52, height: 52, fontSize: 20, color: '#fff', borderRadius: 14 }}>IT</span>
          </div>
          <Typography.Title level={3} style={{ margin: '8px 0 0' }}>{info.data?.organizationName ?? 'ITAM'}</Typography.Title>
          <Typography.Text type="secondary">{t('login.subtitle')}</Typography.Text>
        </Space>
        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
        <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item name="userName" label={t('login.userName')} rules={[{ required: true, message: t('common.required') }]}>
            <Input prefix={<UserOutlined />} autoFocus autoComplete="username" size="large" />
          </Form.Item>
          <Form.Item name="password" label={t('login.password')} rules={[{ required: true, message: t('common.required') }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" size="large" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block size="large" loading={loading}>{t('login.submit')}</Button>
        </Form>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16, alignItems: 'center' }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>ITAM Platform {info.data?.version}</Typography.Text>
          <Select size="small" value={i18n.language} onChange={setLanguage} style={{ width: 120 }} options={LANGUAGES.map((l) => ({ value: l.code, label: l.label }))} />
        </div>
      </Card>
    </div>
  );
}
