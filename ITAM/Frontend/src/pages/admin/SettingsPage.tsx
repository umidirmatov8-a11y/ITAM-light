import { Button, Card, Checkbox, Col, Form, Input, InputNumber, Row, Select, Skeleton, Space, Tabs, TimePicker, Upload, Alert } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post, put, upload } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { PageHeader } from '@/components/PageHeader';
import { dayjs } from '@/utils/format';

type Settings = Record<'general' | 'numbering' | 'documents' | 'notifications' | 'backup' | 'security' | 'qr', Record<string, any>>;

function GroupForm({ group, values, children }: { group: string; values: Record<string, any>; children: React.ReactNode }) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const save = useApiMutation((v: any) => put(`/admin/settings/${group}`, { ...values, ...v }), { invalidate: [['settings'], ['me'], ['public-info']] });
  return (
    <Form form={form} layout="vertical" initialValues={values} onFinish={(v) => save.mutate(v)} style={{ maxWidth: 900 }}>
      {children}
      <Button type="primary" htmlType="submit" loading={save.isPending}>{t('common.save')}</Button>
    </Form>
  );
}

const TZ = ['Asia/Tashkent', 'Asia/Samarkand', 'Asia/Almaty', 'Europe/Moscow', 'UTC', 'Asia/Dubai', 'Europe/Istanbul'];

export default function SettingsPage() {
  const { t } = useTranslation();
  const q = useQuery<Settings>({ queryKey: ['settings'], queryFn: () => get('/admin/settings') });
  const [testTo, setTestTo] = useState('');
  const test = useApiMutation((channel: string) => post('/admin/settings/test-channel', { channel, recipient: testTo }), { success: t('settings.testSent') });
  const logo = useApiMutation((f: File) => upload('/admin/settings/logo', f), { invalidate: [['settings']] });
  if (q.isLoading || !q.data) return <Skeleton active />;
  const s = q.data;
  const num = (name: string, label: string, min = 0) => <Col span={8}><Form.Item name={name} label={label}><InputNumber min={min} style={{ width: '100%' }} /></Form.Item></Col>;
  const chk = (name: string, label: string) => <Col span={12}><Form.Item name={name} valuePropName="checked"><Checkbox>{label}</Checkbox></Form.Item></Col>;
  const txt = (name: string, label: string, extra?: string) => <Col span={12}><Form.Item name={name} label={label} extra={extra}><Input /></Form.Item></Col>;
  return (
    <>
      <PageHeader title={t('menu.settings')} crumbs={[{ title: t('menu.admin') }, { title: t('menu.settings') }]} />
      <Card>
        <Tabs tabPosition="left" items={[
          { key: 'general', label: t('settings.general'), children: (
            <GroupForm group="general" values={s.general}>
              <Row gutter={12}>
                {txt('organizationName', t('setup.organizationName'))}
                <Col span={12}><Form.Item name="timeZone" label={t('setup.timeZone')}><Select showSearch options={TZ.map((z) => ({ value: z, label: z }))} /></Form.Item></Col>
                <Col span={12}><Form.Item name="dateFormat" label={t('settings.dateFormat')}><Select options={['DD.MM.YYYY', 'YYYY-MM-DD', 'MM/DD/YYYY'].map((f) => ({ value: f, label: f }))} /></Form.Item></Col>
                <Col span={12}><Form.Item name="currency" label={t('setup.currency')}><Select options={['UZS', 'USD', 'EUR', 'RUB', 'KZT'].map((c) => ({ value: c, label: c }))} /></Form.Item></Col>
                <Col span={12}><Form.Item name="defaultLanguage" label={t('setup.language')}><Select options={[{ value: 'ru', label: 'Русский' }, { value: 'en', label: 'English' }, { value: 'uz', label: "O'zbekcha" }]} /></Form.Item></Col>
                {txt('publicBaseUrl', t('setup.publicBaseUrl'), t('setup.publicBaseUrlHint'))}
                <Col span={24}><Form.Item label={t('settings.logo')}>
                  <Space>{s.general.logoFileId && <img alt="logo" src={`/api/files/${s.general.logoFileId}?inline=true`} style={{ height: 40 }} />}
                    <Upload accept="image/png,image/jpeg" showUploadList={false} beforeUpload={(f) => { logo.mutate(f); return false; }}><Button icon={<UploadOutlined />}>{t('settings.uploadLogo')}</Button></Upload></Space>
                </Form.Item></Col>
              </Row>
            </GroupForm>
          ) },
          { key: 'numbering', label: t('settings.numbering'), children: (
            <GroupForm group="numbering" values={s.numbering}>
              <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t('settings.numberingHint')} />
              <Row gutter={12}>
                {['assetFormat', 'issueFormat', 'returnFormat', 'transferFormat', 'statusChangeFormat', 'repairFormat', 'documentFormat', 'inventoryFormat', 'employeeNumberFormat'].map((k) => txt(k, t(`settings.fmt.${k}`)))}
              </Row>
            </GroupForm>
          ) },
          { key: 'documents', label: t('settings.documents'), children: (
            <GroupForm group="documents" values={s.documents}>
              <Row gutter={12}>
                {chk('generatePdf', t('settings.generatePdf'))}
                {chk('requireSignatures', t('settings.requireSignatures'))}
                <Col span={12}><Form.Item name="pdfEngine" label={t('settings.pdfEngine')} extra={t('settings.pdfEngineHint')}><Select options={['auto', 'libreoffice', 'builtin'].map((v) => ({ value: v, label: t(`settings.engine.${v}`) }))} /></Form.Item></Col>
                {txt('libreOfficePath', t('settings.libreOfficePath'))}
              </Row>
            </GroupForm>
          ) },
          { key: 'notifications', label: t('settings.notifications'), children: (
            <GroupForm group="notifications" values={s.notifications}>
              <Row gutter={12}>
                {num('licenseExpiryDays', t('settings.licenseDays'))}
                {num('warrantyExpiryDays', t('settings.warrantyDays'))}
                {num('contractExpiryDays', t('settings.contractDays'))}
                {num('repairOverdueDays', t('settings.repairDays'))}
                {chk('notifyUnreturnedEquipment', t('settings.notifyUnreturned'))}
                {chk('notifyNoResponsible', t('settings.notifyNoResponsible'))}
                <Col span={24}><h4>Email (SMTP)</h4></Col>
                {chk('emailEnabled', t('settings.emailEnabled'))}
                {txt('smtpHost', t('settings.smtpHost'))}
                {num('smtpPort', t('settings.smtpPort'), 1)}
                {chk('smtpUseSsl', 'SSL/TLS')}
                {txt('smtpUser', t('settings.smtpUser'))}
                <Col span={12}><Form.Item name="smtpPassword" label={t('settings.smtpPassword')}><Input.Password autoComplete="new-password" /></Form.Item></Col>
                {txt('smtpFrom', t('settings.smtpFrom'))}
                {txt('emailRecipients', t('settings.emailRecipients'), t('settings.emailRecipientsHint'))}
                <Col span={24}><h4>Telegram</h4></Col>
                {chk('telegramEnabled', t('settings.telegramEnabled'))}
                <Col span={12}><Form.Item name="telegramBotToken" label={t('settings.telegramToken')}><Input.Password autoComplete="new-password" /></Form.Item></Col>
                {txt('telegramChatId', 'Chat ID')}
              </Row>
              <Space style={{ marginBottom: 16 }}>
                <Input placeholder={t('settings.testRecipient')} value={testTo} onChange={(e) => setTestTo(e.target.value)} style={{ width: 260 }} />
                <Button onClick={() => test.mutate('email')}>{t('settings.testEmail')}</Button>
                <Button onClick={() => test.mutate('telegram')}>{t('settings.testTelegram')}</Button>
              </Space>
            </GroupForm>
          ) },
          { key: 'backup', label: t('settings.backup'), children: (
            <GroupForm group="backup" values={{ ...s.backup, timeOfDay: s.backup.timeOfDay }}>
              <Row gutter={12}>
                {chk('autoEnabled', t('settings.autoBackup'))}
                {chk('includeFiles', t('settings.includeFiles'))}
                <Col span={8}><Form.Item name="schedule" label={t('settings.schedule')}><Select options={['Daily', 'Weekly'].map((v) => ({ value: v, label: t(`settings.sched.${v}`) }))} /></Form.Item></Col>
                <Col span={8}><Form.Item name="timeOfDay" label={t('settings.time')} getValueProps={(v) => ({ value: v ? dayjs(v, 'HH:mm') : null })} normalize={(v) => (v ? v.format('HH:mm') : null)}><TimePicker format="HH:mm" /></Form.Item></Col>
                <Col span={8}><Form.Item name="dayOfWeek" label={t('settings.dayOfWeek')}><Select options={['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((d) => ({ value: d, label: t(`settings.days.${d}`) }))} /></Form.Item></Col>
                {txt('location', t('settings.backupLocation'), t('settings.backupLocationHint'))}
                {num('retentionDays', t('settings.retentionDays'), 1)}
                {num('maxBackups', t('settings.maxBackups'), 1)}
              </Row>
            </GroupForm>
          ) },
          { key: 'security', label: t('settings.security'), children: (
            <GroupForm group="security" values={s.security}>
              <Row gutter={12}>
                {num('passwordMinLength', t('settings.minLength'), 8)}
                {num('lockoutThreshold', t('settings.lockoutThreshold'))}
                {num('lockoutMinutes', t('settings.lockoutMinutes'), 1)}
                {num('sessionIdleMinutes', t('settings.idleMinutes'), 5)}
                {num('sessionAbsoluteHours', t('settings.absoluteHours'), 1)}
                {num('passwordMaxAgeDays', t('settings.maxAge'))}
                {num('backdateToleranceHours', t('settings.backdateHours'))}
                {chk('requireUppercase', t('settings.upper'))}
                {chk('requireLowercase', t('settings.lower'))}
                {chk('requireDigit', t('settings.digit'))}
                {chk('requireSpecial', t('settings.special'))}
              </Row>
            </GroupForm>
          ) },
          { key: 'qr', label: 'QR', children: (
            <GroupForm group="qr" values={s.qr}>
              <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t('settings.qrHint')} />
              <Row gutter={12}>
                {chk('publicViewEnabled', t('settings.qrPublic'))}
                {chk('showStatus', t('settings.qrStatus'))}
                {chk('showModel', t('settings.qrModel'))}
                {chk('showLocation', t('settings.qrLocation'))}
              </Row>
            </GroupForm>
          ) },
        ]} />
      </Card>
    </>
  );
}
