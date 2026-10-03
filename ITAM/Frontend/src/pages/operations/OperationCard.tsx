import { Alert, Button, Card, DatePicker, Descriptions, Form, Input, Modal, Select, Skeleton, Space, Table, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { Batch, DocumentType } from '@/api/types';
import { Attachments } from '@/components/Attachments';
import { DocumentsTable, GenerateDocumentButton } from '@/components/Documents';
import { PageHeader } from '@/components/PageHeader';
import { BackdatedTag, EnumTag } from '@/components/Tags';
import { SIGNATURE_METHODS, SIGNATURE_STATUSES } from '@/utils/enums';
import { fmtDateTime, parseDateTime, toApiDateTime } from '@/utils/format';

const DOC_TYPES: Record<string, DocumentType> = { Issue: 'EquipmentIssue', Return: 'EquipmentReturn', Transfer: 'EquipmentTransfer', StatusChange: 'WriteOffAct' };

export default function OperationCard() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can } = useAuth();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [signOpen, setSignOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [form] = Form.useForm();
  const q = useQuery<Batch>({ queryKey: ['operation', id], queryFn: () => get(`/operations/${id}`) });
  const cancel = useApiMutation(() => post(`/operations/${id}/cancel`, { reason }), { invalidate: [['operation', id], ['operations'], ['asset']], onSuccess: () => setCancelOpen(false) });
  const sign = useApiMutation((v: any) => put(`/operations/${id}/signature`, { ...v, signedAt: toApiDateTime(v.signedAt) }), { invalidate: [['operation', id]], onSuccess: () => setSignOpen(false) });
  if (q.isLoading || !q.data) return <Skeleton active />;
  const b = q.data;
  return (
    <>
      <PageHeader crumbs={[{ title: t('menu.operations'), to: '/operations' }, { title: b.number }]} title={`${t(`enums.operation.${b.type}`)} ${b.number}`}
        tags={<><BackdatedTag show={b.isBackdated} />{b.isCancelled && <Tag color="red">{t('common.cancelled')}</Tag>}</>}
        extra={<>
          {!b.isCancelled && <GenerateDocumentButton sourceType="OperationBatch" sourceId={b.id} documentType={DOC_TYPES[b.type]} />}
          {can('documents.sign') && !b.isCancelled && <Button onClick={() => { form.setFieldsValue({ ...b, signedAt: parseDateTime(b.signedAt) }); setSignOpen(true); }}>{t('documents.signature')}</Button>}
          {can('assets.correct') && !b.isCancelled && <Button danger onClick={() => setCancelOpen(true)}>{t('operations.cancel')}</Button>}
        </>} />
      {b.isCancelled && <Alert type="error" showIcon style={{ marginBottom: 16 }} message={t('operations.cancelledInfo', { date: fmtDateTime(b.cancelledAt) })} description={b.cancelReason} />}
      <Card style={{ marginBottom: 16 }}>
        <Descriptions bordered size="small" column={{ xs: 1, md: 2 }}>
          <Descriptions.Item label={t('operations.effectiveAt')}>{fmtDateTime(b.effectiveAt)}</Descriptions.Item>
          <Descriptions.Item label={t('common.recordedAt')}>{fmtDateTime(b.recordedAt)} · {b.createdBy}</Descriptions.Item>
          <Descriptions.Item label={t('operations.employee')}>
            {b.employeeId && <Link to={`/employees/${b.employeeId}`}>{b.employeeName}</Link>}
            {b.employeeSnapshot && <div className="itam-muted" style={{ fontSize: 12 }}>{t('operations.snapshot')}: {[b.employeeSnapshot.fullName, b.employeeSnapshot.position, b.employeeSnapshot.department, b.employeeSnapshot.region].filter(Boolean).join(' · ')}</div>}
          </Descriptions.Item>
          <Descriptions.Item label={t('common.responsible')}>{b.responsibleSnapshot?.fullName}</Descriptions.Item>
          <Descriptions.Item label={t('documents.employeeSignature')}><EnumTag group="signature" value={b.employeeSignatureStatus} /></Descriptions.Item>
          <Descriptions.Item label={t('documents.responsibleSignature')}><EnumTag group="signature" value={b.responsibleSignatureStatus} /> {b.signedAt && fmtDateTime(b.signedAt)}</Descriptions.Item>
          <Descriptions.Item label={t('common.comment')} span={2}>{b.comment}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title={t('operations.lines')} style={{ marginBottom: 16 }}>
        <Table<any> rowKey="id" size="small" pagination={false} dataSource={b.lines} rowClassName={(r) => (r.isCancelled ? 'itam-cancelled' : '')} scroll={{ x: 'max-content' }}
          columns={[
            { title: t('assets.inventoryNumber'), dataIndex: 'inventoryNumber', render: (v: string, r: any) => <Link className="itam-mono" to={`/assets/${r.assetId}`}>{v}</Link> },
            { title: t('assets.name'), dataIndex: 'assetName' },
            { title: t('assets.serialNumber'), dataIndex: 'serialNumber' },
            { title: t('assets.condition'), dataIndex: 'condition', render: (v: string) => v && <EnumTag group="condition" value={v} /> },
            { title: t('operations.accessories'), dataIndex: 'accessories' },
            b.type === 'Return' ? { title: t('operations.damage'), dataIndex: 'damage' } : {},
            b.type === 'Return' ? { title: t('operations.missingItems'), dataIndex: 'missingItems' } : {},
            ['Transfer', 'StatusChange'].includes(b.type) ? { title: t('operations.from'), dataIndex: 'from' } : {},
            ['Transfer', 'StatusChange'].includes(b.type) ? { title: t('operations.to'), dataIndex: 'to' } : {},
            b.type === 'Issue' ? { title: t('operations.returnedAt'), dataIndex: 'effectiveTo', render: fmtDateTime } : {},
          ].filter((c) => 'title' in c) as never} />
      </Card>
      <Card title={t('tabs.documents')} style={{ marginBottom: 16 }}><DocumentsTable filter={{ sourceType: 'OperationBatch', sourceId: b.id }} /></Card>
      <Card title={t('tabs.attachments')}><Attachments entityType="OperationBatch" entityId={b.id} /></Card>
      <Modal open={cancelOpen} title={t('operations.cancel')} onCancel={() => setCancelOpen(false)} onOk={() => cancel.mutate(undefined)} okButtonProps={{ danger: true, disabled: reason.length < 3 }} confirmLoading={cancel.isPending}>
        <Alert type="warning" showIcon message={t('operations.cancelWarning')} style={{ marginBottom: 12 }} />
        <Input.TextArea rows={3} placeholder={t('common.reason')} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
      <Modal open={signOpen} title={t('documents.signature')} onCancel={() => setSignOpen(false)} onOk={() => form.submit()} confirmLoading={sign.isPending}>
        <Form form={form} layout="vertical" onFinish={(v) => sign.mutate(v)}>
          <Form.Item name="employeeSignatureStatus" label={t('documents.employeeSignature')}><Select options={SIGNATURE_STATUSES.map((s) => ({ value: s, label: t(`enums.signature.${s}`) }))} /></Form.Item>
          <Form.Item name="responsibleSignatureStatus" label={t('documents.responsibleSignature')}><Select options={SIGNATURE_STATUSES.map((s) => ({ value: s, label: t(`enums.signature.${s}`) }))} /></Form.Item>
          <Form.Item name="signatureMethod" label={t('documents.signatureMethod')}><Select options={SIGNATURE_METHODS.map((s) => ({ value: s, label: t(`enums.signatureMethod.${s}`) }))} /></Form.Item>
          <Form.Item name="signedAt" label={t('documents.signedAt')}><DatePicker showTime format="DD.MM.YYYY HH:mm" /></Form.Item>
          <Space />
        </Form>
      </Modal>
    </>
  );
}
