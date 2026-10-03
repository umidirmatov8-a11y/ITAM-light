import { Alert, Button, Card, Checkbox, Col, Result, Row, Select, Space, Steps, Table, Typography, Upload } from 'antd';
import { DownloadOutlined, InboxOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { download, post, upload } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import { PageHeader } from '@/components/PageHeader';

interface Field { key: string; label: string; required: boolean }
interface Preview { jobId: string; headers: string[]; rows: (string | null)[][]; totalRows: number; fields: Field[]; suggestedMapping: Record<string, string | null> }
interface ImportErrorRow { row: number; column: string; value?: string; error: string }
interface Validation { totalRows: number; validRows: number; errorRows: number; errors: ImportErrorRow[]; newRecords: number; updatedRecords: number }

const ENTITIES = ['employees', 'assets', 'departments', 'locations'];

/** Upload → Preview → Column mapping → Validation → Confirm. No blind import. */
export default function ImportPage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const [entity, setEntity] = useState('employees');
  const [step, setStep] = useState(0);
  const [preview, setPreview] = useState<Preview>();
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [options, setOptions] = useState({ updateExisting: true, skipInvalid: false, createMissingReferences: true });
  const [validation, setValidation] = useState<Validation>();
  const [done, setDone] = useState<{ imported: number; skipped: number }>();
  const uploadMutation = useApiMutation((f: File) => upload<Preview>(`/import/${entity}/upload`, f), {
    success: false, onSuccess: (p) => { setPreview(p); setMapping(p.suggestedMapping); setStep(1); },
  });
  const validate = useApiMutation(() => post<Validation>(`/import/${preview!.jobId}/validate`, { mapping, ...options }), { success: false, onSuccess: (v) => { setValidation(v); setStep(3); } });
  const commit = useApiMutation(() => post<{ imported: number; skipped: number }>(`/import/${preview!.jobId}/commit`, { mapping, ...options }), { success: false, onSuccess: (r) => { setDone(r); setStep(4); } });
  const reset = () => { setStep(0); setPreview(undefined); setValidation(undefined); setDone(undefined); };

  return (
    <>
      <PageHeader title={t('menu.import')} crumbs={[{ title: t('menu.import') }]} />
      <Card>
        <Steps current={step} style={{ marginBottom: 24 }} items={['upload', 'preview', 'mapping', 'validation', 'done'].map((s) => ({ title: t(`import.steps.${s}`) }))} />
        {step === 0 && (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Space wrap>
              <Select value={entity} onChange={setEntity} style={{ width: 240 }} options={ENTITIES.map((e) => ({ value: e, label: t(`import.entities.${e}`) }))} />
              <Button icon={<DownloadOutlined />} onClick={() => download(`/import/template/${entity}`, { format: 'xlsx' }).catch(notify.error)}>{t('import.template')}</Button>
            </Space>
            <Upload.Dragger accept=".xlsx,.csv" showUploadList={false} beforeUpload={(f) => { uploadMutation.mutate(f); return false; }} disabled={uploadMutation.isPending}>
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p>{t('import.drop')}</p>
              <p className="itam-muted">{t('import.formats')}</p>
            </Upload.Dragger>
          </Space>
        )}
        {step === 1 && preview && (
          <>
            <Typography.Paragraph>{t('import.previewInfo', { count: preview.totalRows })}</Typography.Paragraph>
            <Table size="small" rowKey={(_, i) => String(i)} pagination={false} scroll={{ x: 'max-content' }} dataSource={preview.rows.map((r) => ({ ...r }))}
              columns={preview.headers.map((h, i) => ({ title: h, key: String(i), render: (_: unknown, row: Record<number, string | null>) => row[i] }))} />
            <Space style={{ marginTop: 16 }}><Button onClick={reset}>{t('common.back')}</Button><Button type="primary" onClick={() => setStep(2)}>{t('common.next')}</Button></Space>
          </>
        )}
        {step === 2 && preview && (
          <>
            <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t('import.mappingHint')} />
            <Row gutter={[16, 8]}>
              {preview.fields.map((f) => (
                <Col xs={24} md={12} key={f.key}>
                  <Space style={{ width: '100%' }}>
                    <span style={{ width: 220, display: 'inline-block' }}>{f.label}{f.required && <Typography.Text type="danger"> *</Typography.Text>}</span>
                    <Select allowClear style={{ width: 260 }} value={mapping[f.key] ?? undefined} onChange={(v) => setMapping((m) => ({ ...m, [f.key]: v ?? null }))}
                      options={preview.headers.map((h) => ({ value: h, label: h }))} placeholder={t('import.notMapped')} />
                  </Space>
                </Col>
              ))}
            </Row>
            <Space direction="vertical" style={{ marginTop: 16 }}>
              <Checkbox checked={options.updateExisting} onChange={(e) => setOptions((o) => ({ ...o, updateExisting: e.target.checked }))}>{t('import.updateExisting')}</Checkbox>
              <Checkbox checked={options.createMissingReferences} onChange={(e) => setOptions((o) => ({ ...o, createMissingReferences: e.target.checked }))}>{t('import.createRefs')}</Checkbox>
            </Space>
            <Space style={{ marginTop: 16, display: 'flex' }}><Button onClick={() => setStep(1)}>{t('common.back')}</Button><Button type="primary" loading={validate.isPending} onClick={() => validate.mutate(undefined)}>{t('import.validate')}</Button></Space>
          </>
        )}
        {step === 3 && validation && (
          <>
            <Alert type={validation.errorRows ? 'warning' : 'success'} showIcon style={{ marginBottom: 16 }}
              message={t('import.validationSummary', { total: validation.totalRows, valid: validation.validRows, errors: validation.errorRows, created: validation.newRecords, updated: validation.updatedRecords })} />
            {validation.errors.length > 0 && (
              <Table<ImportErrorRow> size="small" rowKey={(r, i) => `${r.row}-${i}`} dataSource={validation.errors} pagination={{ pageSize: 20 }}
                columns={[
                  { title: t('import.row'), dataIndex: 'row', width: 80 },
                  { title: t('import.column'), dataIndex: 'column' },
                  { title: t('import.value'), dataIndex: 'value' },
                  { title: t('import.error'), dataIndex: 'error' },
                ]} />
            )}
            <Space direction="vertical" style={{ marginTop: 16 }}>
              {validation.errorRows > 0 && <Checkbox checked={options.skipInvalid} onChange={(e) => setOptions((o) => ({ ...o, skipInvalid: e.target.checked }))}>{t('import.skipInvalid')}</Checkbox>}
              <Space>
                <Button onClick={() => setStep(2)}>{t('common.back')}</Button>
                <Button type="primary" disabled={validation.errorRows > 0 && !options.skipInvalid || validation.validRows === 0} loading={commit.isPending} onClick={() => commit.mutate(undefined)}>
                  {t('import.confirm', { count: validation.validRows })}
                </Button>
              </Space>
            </Space>
          </>
        )}
        {step === 4 && done && <Result status="success" title={t('import.done', { count: done.imported })} subTitle={t('import.skipped', { count: done.skipped })} extra={<Button onClick={reset}>{t('import.again')}</Button>} />}
      </Card>
    </>
  );
}
