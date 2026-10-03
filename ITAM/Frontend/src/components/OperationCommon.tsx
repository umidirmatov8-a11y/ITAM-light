import { Alert, Button, Checkbox, Col, DatePicker, Form, Result, Select, Space } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { get, openInline } from '@/api/client';
import { useAuth } from '@/app/auth';
import type { DocumentType, OperationResult } from '@/api/types';
import { dayjs, nowInTz } from '@/utils/format';

/** Business date with backdating hint (EffectiveAt vs RecordedAt). */
export function EffectiveAtField({ name = 'effectiveAt', label }: { name?: string; label?: string }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const form = Form.useFormInstance();
  const value = Form.useWatch(name, form) as dayjs.Dayjs | undefined;
  const backdated = value && value.isBefore(nowInTz().subtract(1, 'day'));
  return (
    <>
      <Form.Item name={name} label={label ?? t('operations.effectiveAt')} rules={[{ required: true }]} extra={t('operations.effectiveHint')}>
        <DatePicker showTime format="DD.MM.YYYY HH:mm" style={{ width: '100%' }} disabledDate={(d) => d.isAfter(nowInTz().endOf('day'))} />
      </Form.Item>
      {backdated && <Alert type={can('assets.backdate') ? 'warning' : 'error'} showIcon style={{ marginBottom: 16 }}
        message={can('assets.backdate') ? t('operations.backdatedWarning') : t('operations.backdatedForbidden')} />}
    </>
  );
}

export function DocumentOptions({ type }: { type: DocumentType }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const form = Form.useFormInstance();
  const generate = Form.useWatch('generateDocument', form);
  const templates = useQuery<{ id: string; name: string; activeVersion?: number }[]>({ queryKey: ['templates', type], queryFn: () => get('/templates', { type }), enabled: can('documents.generate') });
  if (!can('documents.generate')) return null;
  return (
    <Space align="start" wrap>
      <Form.Item name="generateDocument" valuePropName="checked"><Checkbox>{t('operations.generateDocument')}</Checkbox></Form.Item>
      {generate && (
        <Form.Item name="templateId" style={{ minWidth: 280 }}>
          <Select allowClear placeholder={t('documents.defaultTemplate')} options={(templates.data ?? []).map((tp) => ({ value: tp.id, label: `${tp.name} (v${tp.activeVersion ?? '-'})` }))} />
        </Form.Item>
      )}
    </Space>
  );
}

export function OperationDone({ result, onAgain }: { result: OperationResult; onAgain: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <Result status="success" title={t('operations.done', { number: result.number })}
      subTitle={[t('operations.assetsCount', { count: result.assetCount }), result.isBackdated ? t('operations.wasBackdated') : null].filter(Boolean).join(' · ')}
      extra={[
        <Button type="primary" key="o" onClick={() => navigate(`/operations/${result.batchId}`)}>{t('operations.openAct')}</Button>,
        result.documentId && <Button key="d" onClick={() => openInline(`/documents/${result.documentId}/download`, { format: 'pdf' })}>{t('operations.openDocument')}</Button>,
        result.repairIds?.length ? <Button key="r" onClick={() => navigate(`/repairs/${result.repairIds![0]}`)}>{t('operations.openRepair')}</Button> : null,
        <Button key="a" onClick={onAgain}>{t('operations.again')}</Button>,
      ].filter(Boolean)} />
  );
}

export const Half = ({ children }: { children: React.ReactNode }) => <Col xs={24} md={12}>{children}</Col>;

export const idsFromQuery = (v: string | null) => (v ? v.split(',').filter(Boolean) : []);
