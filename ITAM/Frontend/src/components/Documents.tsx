import { Button, DatePicker, Dropdown, Form, Input, Modal, Select, Space, Table, Tag, Tooltip, Upload } from 'antd';
import { DownloadOutlined, EyeOutlined, FileAddOutlined, MoreOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { download, get, openInline, post, put, upload, type Paged } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { DocumentItem, DocumentType } from '@/api/types';
import { SignatureTag } from '@/components/Tags';
import { SIGNATURE_METHODS, SIGNATURE_STATUSES } from '@/utils/enums';
import { fmtDateTime, toApiDateTime } from '@/utils/format';

/** Button generating a document for a source (operation, repair, checklist, inventory, employee) with template choice. */
export function GenerateDocumentButton({ sourceType, sourceId, documentType, onDone, size }: { sourceType: string; sourceId: string; documentType?: DocumentType; onDone?: () => void; size?: 'small' | 'middle' }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const [templateId, setTemplateId] = useState<string>();
  const templates = useQuery<{ id: string; name: string; activeVersion?: number }[]>({ queryKey: ['templates', documentType], queryFn: () => get('/templates', { type: documentType }), enabled: open });
  const gen = useApiMutation(() => post<DocumentItem>('/documents/generate', { sourceType, sourceId, templateId }), {
    invalidate: [['documents']],
    success: t('documents.generated'),
    onSuccess: (d) => { setOpen(false); onDone?.(); if (d.pdfFileId) openInline(`/documents/${d.id}/download`, { format: 'pdf' }); },
  });
  if (!can('documents.generate')) return null;
  return (
    <>
      <Button icon={<FileAddOutlined />} size={size} onClick={() => setOpen(true)}>{t('documents.generate')}</Button>
      <Modal open={open} onCancel={() => setOpen(false)} title={t('documents.generate')} onOk={() => gen.mutate(undefined)} confirmLoading={gen.isPending}>
        <Form layout="vertical">
          <Form.Item label={t('documents.template')} extra={t('documents.templateHint')}>
            <Select allowClear loading={templates.isLoading} value={templateId} onChange={setTemplateId}
              options={(templates.data ?? []).map((tp) => ({ value: tp.id, label: `${tp.name} (v${tp.activeVersion ?? '-'})` }))} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

/** Generated documents registry (optionally filtered by employee/asset/source). */
export function DocumentsTable({ filter }: { filter?: Record<string, unknown> }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const notify = useNotify();
  const [page, setPage] = useState(1);
  const [signDoc, setSignDoc] = useState<DocumentItem>();
  const [voidDoc, setVoidDoc] = useState<DocumentItem>();
  const [form] = Form.useForm();
  const key = ['documents', filter, page];
  const q = useQuery<Paged<DocumentItem>>({ queryKey: key, queryFn: () => get('/documents', { ...filter, page, pageSize: 20 }) });
  const sign = useApiMutation((v: any) => put(`/documents/${signDoc!.id}/signature`, { ...v, employeeSignedAt: toApiDateTime(v.employeeSignedAt) }), {
    invalidate: [['documents']], onSuccess: () => setSignDoc(undefined),
  });
  const voidMut = useApiMutation((reason: string) => post(`/documents/${voidDoc!.id}/void`, { reason }), { invalidate: [['documents']], onSuccess: () => setVoidDoc(undefined) });
  const scan = useApiMutation(({ id, file }: { id: string; file: File }) => upload(`/documents/${id}/scan`, file), { invalidate: [['documents']] });
  const [voidReason, setVoidReason] = useState('');

  return (
    <>
      <Table<DocumentItem> rowKey="id" size="small" loading={q.isLoading} dataSource={q.data?.items}
        pagination={{ current: page, pageSize: 20, total: q.data?.total, onChange: setPage }}
        scroll={{ x: 'max-content' }}
        columns={[
          { title: t('documents.number'), dataIndex: 'number', render: (v, r) => <span className={r.isVoided ? 'itam-cancelled' : undefined}>{v}</span> },
          { title: t('documents.title'), dataIndex: 'title' },
          { title: t('documents.type'), dataIndex: 'documentType', render: (v) => t(`enums.documentType.${v}`) },
          { title: t('documents.templateVersion'), render: (_, r) => <Tooltip title={r.templateName}><Tag>v{r.templateVersionNumber}</Tag></Tooltip> },
          { title: t('documents.employee'), dataIndex: 'employeeName' },
          { title: t('documents.employeeSignature'), dataIndex: 'employeeSignatureStatus', render: (v) => <SignatureTag status={v} /> },
          { title: t('documents.responsibleSignature'), dataIndex: 'responsibleSignatureStatus', render: (v) => <SignatureTag status={v} /> },
          { title: t('common.createdAt'), dataIndex: 'createdAt', render: fmtDateTime },
          { title: t('common.createdBy'), dataIndex: 'createdByName' },
          {
            key: 'a', fixed: 'right', render: (_, r) => (
              <Space>
                {r.pdfFileId && <Tooltip title="PDF"><Button size="small" icon={<EyeOutlined />} onClick={() => openInline(`/documents/${r.id}/download`, { format: 'pdf' }).catch(notify.error)} /></Tooltip>}
                <Dropdown menu={{ items: [
                  { key: 'docx', icon: <DownloadOutlined />, label: 'DOCX', onClick: () => download(`/documents/${r.id}/download`, { format: 'docx' }).catch(notify.error) },
                  r.pdfFileId && { key: 'pdf', icon: <DownloadOutlined />, label: 'PDF', onClick: () => download(`/documents/${r.id}/download`, { format: 'pdf' }).catch(notify.error) },
                  r.signedScanFileId && { key: 'scanget', label: t('documents.downloadScan'), onClick: () => download(`/documents/${r.id}/download`, { format: 'scan' }).catch(notify.error) },
                  can('documents.sign') && !r.isVoided && { key: 'sign', label: t('documents.signature'), onClick: () => { setSignDoc(r); form.setFieldsValue({ ...r, employeeSignedAt: null }); } },
                  can('documents.sign') && !r.isVoided && { key: 'scan', label: (
                    <Upload showUploadList={false} beforeUpload={(file) => { scan.mutate({ id: r.id, file }); return false; }}>{t('documents.uploadScan')}</Upload>
                  ) },
                  can('documents.generate') && !r.isVoided && { key: 'void', danger: true, label: t('documents.void'), onClick: () => setVoidDoc(r) },
                ].filter(Boolean) as never }}>
                  <Button size="small" icon={<MoreOutlined />} />
                </Dropdown>
              </Space>
            ),
          },
        ]} />
      <Modal open={!!signDoc} title={t('documents.signature')} onCancel={() => setSignDoc(undefined)} onOk={() => form.submit()} confirmLoading={sign.isPending}>
        <Form form={form} layout="vertical" onFinish={(v) => sign.mutate(v)}>
          <Form.Item name="employeeSignatureStatus" label={t('documents.employeeSignature')}><Select options={SIGNATURE_STATUSES.map((s) => ({ value: s, label: t(`enums.signature.${s}`) }))} /></Form.Item>
          <Form.Item name="responsibleSignatureStatus" label={t('documents.responsibleSignature')}><Select options={SIGNATURE_STATUSES.map((s) => ({ value: s, label: t(`enums.signature.${s}`) }))} /></Form.Item>
          <Form.Item name="signatureMethod" label={t('documents.signatureMethod')}><Select options={SIGNATURE_METHODS.map((s) => ({ value: s, label: t(`enums.signatureMethod.${s}`) }))} /></Form.Item>
          <Form.Item name="employeeSignedAt" label={t('documents.signedAt')}><DatePicker showTime format="DD.MM.YYYY HH:mm" /></Form.Item>
        </Form>
      </Modal>
      <Modal open={!!voidDoc} title={t('documents.void')} onCancel={() => setVoidDoc(undefined)} onOk={() => voidMut.mutate(voidReason)} okButtonProps={{ danger: true, disabled: !voidReason }}>
        <Input.TextArea rows={3} placeholder={t('common.reason')} value={voidReason} onChange={(e) => setVoidReason(e.target.value)} />
      </Modal>
    </>
  );
}
