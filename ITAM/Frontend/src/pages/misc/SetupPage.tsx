import { Alert, Button, Card, Checkbox, Descriptions, Form, Input, Result, Select, Space, Steps, Typography } from 'antd';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { get, post, ApiError } from '@/api/client';

interface Status { setupCompleted: boolean; databaseConnected: boolean; databaseVersion?: string; databaseName?: string; organizationName?: string; appVersion: string; error?: string }

const TIMEZONES = ['Asia/Tashkent', 'Asia/Samarkand', 'Asia/Almaty', 'Europe/Moscow', 'UTC', 'Asia/Dubai', 'Europe/Istanbul'];

/** First-run wizard: Database → Organization → Administrator → Timezone → Initial settings → Finish. */
export default function SetupPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [form] = Form.useForm();
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const status = useQuery<Status>({ queryKey: ['setup-status'], queryFn: () => get('/setup/status'), refetchInterval: (q) => (q.state.data?.databaseConnected ? false : 5000) });

  const steps = [t('setup.stepDatabase'), t('setup.stepOrganization'), t('setup.stepAdmin'), t('setup.stepTimezone'), t('setup.stepSettings'), t('setup.stepFinish')];
  const fieldsByStep: string[][] = [[], ['organizationName'], ['adminUserName', 'adminDisplayName', 'adminEmail', 'adminPassword', 'adminPassword2'], ['timeZone'], ['language', 'currency', 'assetNumberFormat', 'publicBaseUrl', 'loadDemoData'], []];

  const next = async () => {
    await form.validateFields(fieldsByStep[step]);
    setStep((s) => s + 1);
  };

  const finish = async () => {
    setSaving(true);
    setError(undefined);
    try {
      const v = form.getFieldsValue(true);
      await post('/setup/complete', v);
      setDone(true);
      await qc.invalidateQueries({ queryKey: ['public-info'] });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  if (done)
    return (
      <div className="itam-login-bg">
        <Card style={{ maxWidth: 560 }}>
          <Result status="success" title={t('setup.doneTitle')} subTitle={t('setup.doneText')} extra={<Button type="primary" href="/login">{t('setup.goLogin')}</Button>} />
        </Card>
      </div>
    );

  return (
    <div className="itam-login-bg">
      <Card style={{ width: '100%', maxWidth: 820 }} title={<Typography.Title level={4} style={{ margin: 0 }}>{t('setup.title')}</Typography.Title>}>
        <Steps current={step} items={steps.map((s) => ({ title: s }))} size="small" style={{ marginBottom: 24 }} responsive />
        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
        <Form form={form} layout="vertical" initialValues={{ adminUserName: 'admin', timeZone: 'Asia/Tashkent', language: 'ru', currency: 'UZS', assetNumberFormat: '{PREFIX}-{SEQ:6}', publicBaseUrl: window.location.origin, loadDemoData: false }}>
          <div style={{ display: step === 0 ? 'block' : 'none' }}>
            {status.data?.databaseConnected ? (
              <Alert type="success" showIcon message={t('setup.dbOk')} description={
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label={t('setup.dbName')}>{status.data.databaseName}</Descriptions.Item>
                  <Descriptions.Item label={t('setup.dbVersion')}>{status.data.databaseVersion}</Descriptions.Item>
                  <Descriptions.Item label={t('setup.appVersion')}>{status.data.appVersion}</Descriptions.Item>
                </Descriptions>
              } />
            ) : (
              <Alert type="warning" showIcon message={t('setup.dbFail')} description={<><div>{status.data?.error}</div><div>{t('setup.dbHint')}</div></>} />
            )}
          </div>
          <div style={{ display: step === 1 ? 'block' : 'none' }}>
            <Form.Item name="organizationName" label={t('setup.organizationName')} rules={[{ required: true, message: t('common.required') }]}>
              <Input placeholder={t('setup.organizationPlaceholder')} />
            </Form.Item>
          </div>
          <div style={{ display: step === 2 ? 'block' : 'none' }}>
            <Form.Item name="adminUserName" label={t('setup.adminUserName')} rules={[{ required: true, pattern: /^[A-Za-z0-9._@-]+$/, message: t('setup.loginRule') }]}><Input /></Form.Item>
            <Form.Item name="adminDisplayName" label={t('setup.adminDisplayName')}><Input /></Form.Item>
            <Form.Item name="adminEmail" label="Email" rules={[{ type: 'email' }]}><Input /></Form.Item>
            <Form.Item name="adminPassword" label={t('setup.adminPassword')} extra={t('setup.passwordPolicy')} rules={[{ required: true, min: 10, message: t('setup.passwordPolicy') }]}><Input.Password /></Form.Item>
            <Form.Item name="adminPassword2" label={t('setup.adminPassword2')} dependencies={['adminPassword']}
              rules={[{ required: true }, ({ getFieldValue }) => ({ validator: (_, v) => (v === getFieldValue('adminPassword') ? Promise.resolve() : Promise.reject(t('setup.passwordMismatch'))) })]}>
              <Input.Password />
            </Form.Item>
          </div>
          <div style={{ display: step === 3 ? 'block' : 'none' }}>
            <Form.Item name="timeZone" label={t('setup.timeZone')} rules={[{ required: true }]} extra={t('setup.timeZoneHint')}>
              <Select showSearch options={TIMEZONES.map((z) => ({ value: z, label: z }))} />
            </Form.Item>
          </div>
          <div style={{ display: step === 4 ? 'block' : 'none' }}>
            <Form.Item name="language" label={t('setup.language')}><Select options={[{ value: 'ru', label: 'Русский' }, { value: 'en', label: 'English' }, { value: 'uz', label: "O'zbekcha" }]} /></Form.Item>
            <Form.Item name="currency" label={t('setup.currency')}><Select options={['UZS', 'USD', 'EUR', 'RUB', 'KZT'].map((c) => ({ value: c, label: c }))} /></Form.Item>
            <Form.Item name="assetNumberFormat" label={t('setup.assetNumberFormat')} extra={t('setup.assetNumberHint')}><Input /></Form.Item>
            <Form.Item name="publicBaseUrl" label={t('setup.publicBaseUrl')} extra={t('setup.publicBaseUrlHint')}><Input /></Form.Item>
            <Form.Item name="loadDemoData" valuePropName="checked"><Checkbox>{t('setup.loadDemo')}</Checkbox></Form.Item>
          </div>
          <div style={{ display: step === 5 ? 'block' : 'none' }}>
            <Typography.Paragraph>{t('setup.reviewText')}</Typography.Paragraph>
            <Form.Item noStyle shouldUpdate>
              {() => {
                const v = form.getFieldsValue(true);
                return (
                  <Descriptions bordered size="small" column={1}>
                    <Descriptions.Item label={t('setup.organizationName')}>{v.organizationName}</Descriptions.Item>
                    <Descriptions.Item label={t('setup.adminUserName')}>{v.adminUserName}</Descriptions.Item>
                    <Descriptions.Item label={t('setup.timeZone')}>{v.timeZone}</Descriptions.Item>
                    <Descriptions.Item label={t('setup.currency')}>{v.currency}</Descriptions.Item>
                    <Descriptions.Item label={t('setup.assetNumberFormat')}>{v.assetNumberFormat}</Descriptions.Item>
                    <Descriptions.Item label={t('setup.loadDemo')}>{v.loadDemoData ? t('common.yes') : t('common.no')}</Descriptions.Item>
                  </Descriptions>
                );
              }}
            </Form.Item>
          </div>
        </Form>
        <Space style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
          {step > 0 && <Button onClick={() => setStep((s) => s - 1)}>{t('common.back')}</Button>}
          {step < steps.length - 1 && <Button type="primary" onClick={next} disabled={step === 0 && !status.data?.databaseConnected}>{t('common.next')}</Button>}
          {step === steps.length - 1 && <Button type="primary" loading={saving} onClick={finish}>{t('setup.finish')}</Button>}
        </Space>
      </Card>
    </div>
  );
}
