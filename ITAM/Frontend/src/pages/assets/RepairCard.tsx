import { Button, Card, Col, DatePicker, Descriptions, Form, Input, Modal, Row, Skeleton, Space, Tabs, Timeline } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post } from '@/api/client';
import { useApiMutation, useLookup } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { Repair } from '@/api/types';
import { Attachments } from '@/components/Attachments';
import { CustomFieldsView } from '@/components/CustomFields';
import { DocumentsTable, GenerateDocumentButton } from '@/components/Documents';
import { PageHeader } from '@/components/PageHeader';
import { LookupSelect } from '@/components/Selects';
import { StatusTag } from '@/components/Tags';
import { fmtDate, fmtDateTime, fmtMoney, nowInTz, toApiDateTime } from '@/utils/format';
import { RepairForm } from './RepairForm';

export default function RepairCard() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can } = useAuth();
  const [edit, setEdit] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const [form] = Form.useForm();
  const statuses = useLookup('repair-statuses');
  const q = useQuery<Repair>({ queryKey: ['repair', id], queryFn: () => get(`/repairs/${id}`) });
  const selectedStatus = Form.useWatch('statusId', form);
  const closing = ['Returned', 'Cancelled'].includes(statuses.data?.find((s) => s.id === selectedStatus)?.stage);
  const change = useApiMutation((v: any) => post(`/repairs/${id}/status`, { ...v, changedAt: toApiDateTime(v.changedAt) }), {
    invalidate: [['repair', id], ['repairs'], ['asset', q.data?.assetId]], onSuccess: () => setStatusOpen(false),
  });
  if (q.isLoading || !q.data) return <Skeleton active />;
  const r = q.data;
  const closed = r.stage === 'Returned' || r.stage === 'Cancelled';
  return (
    <>
      <PageHeader crumbs={[{ title: t('menu.repairs'), to: '/repairs' }, { title: r.number }]} title={`${t('repairs.repair')} ${r.number}`}
        tags={<StatusTag name={r.statusName} color={r.statusColor} />}
        subtitle={<Link to={`/assets/${r.assetId}`}>{r.inventoryNumber} — {r.assetName}</Link>}
        extra={<>
          {can('assets.repair') && !closed && <Button type="primary" onClick={() => { form.resetFields(); form.setFieldsValue({ changedAt: nowInTz() }); setStatusOpen(true); }}>{t('repairs.changeStatus')}</Button>}
          {can('assets.repair') && <Button icon={<EditOutlined />} onClick={() => setEdit(true)}>{t('common.edit')}</Button>}
          <GenerateDocumentButton sourceType="Repair" sourceId={r.id} documentType="EquipmentRepair" />
        </>} />
      <Tabs items={[
        {
          key: 'o', label: t('tabs.overview'), children: (
            <Row gutter={16}>
              <Col xs={24} xl={16}>
                <Card>
                  <Descriptions bordered size="small" column={{ xs: 1, sm: 1, md: 2, lg: 2, xl: 2, xxl: 3 }}>
                    <Descriptions.Item label={t('repairs.asset')}><Link to={`/assets/${r.assetId}`}>{r.inventoryNumber}</Link> {r.serialNumber && <span className="itam-mono itam-muted">S/N {r.serialNumber}</span>}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.employee')}>{r.employeeId ? <Link to={`/employees/${r.employeeId}`}>{r.employeeName}</Link> : '—'}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.openedAt')}>{fmtDateTime(r.openedAt)}</Descriptions.Item>
                    <Descriptions.Item label={t('common.recordedAt')}>{fmtDateTime(r.recordedAt)}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.serviceCenter')}>{r.serviceCenterName}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.sentAt')}>{fmtDateTime(r.sentAt)}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.expectedReturn')}>{fmtDate(r.expectedReturnDate)}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.returnedAt')}>{fmtDateTime(r.actualReturnAt)}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.problem')} span={2}>{r.problem}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.diagnosis')} span={2}>{r.diagnosis}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.description')} span={2}>{r.repairDescription}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.parts')} span={2}>{r.parts}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.cost')}>{fmtMoney(r.cost, r.currency)}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.warranty')}>{r.isWarranty ? t('common.yes') : t('common.no')}</Descriptions.Item>
                    <Descriptions.Item label={t('repairs.technician')}>{r.technician}</Descriptions.Item>
                    <Descriptions.Item label={t('common.comment')}>{r.comment}</Descriptions.Item>
                  </Descriptions>
                  <CustomFieldsView entity="Repair" values={r.customFields} />
                </Card>
              </Col>
              <Col xs={24} xl={8}>
                <Card size="small" title={t('repairs.statusHistory')}>
                  <Timeline items={r.history.map((h) => ({ children: <><b>{h.statusName}</b> · {fmtDateTime(h.changedAt)}<div className="itam-muted" style={{ fontSize: 12 }}>{h.recordedByName} {h.comment}</div></> }))} />
                </Card>
              </Col>
            </Row>
          ),
        },
        { key: 'd', label: t('tabs.documents'), children: <DocumentsTable filter={{ sourceType: 'Repair', sourceId: r.id }} /> },
        { key: 'f', label: t('tabs.attachments'), children: <Attachments entityType="Repair" entityId={r.id} /> },
      ]} />
      <RepairForm open={edit} repair={r} onClose={() => setEdit(false)} />
      <Modal open={statusOpen} title={t('repairs.changeStatus')} onCancel={() => setStatusOpen(false)} onOk={() => form.submit()} confirmLoading={change.isPending}>
        <Form form={form} layout="vertical" onFinish={(v) => change.mutate(v)}>
          <Form.Item name="statusId" label={t('common.status')} rules={[{ required: true }]}><LookupSelect lookup="repair-statuses" filter={(s) => s.id !== r.statusId} /></Form.Item>
          <Form.Item name="changedAt" label={t('repairs.changedAt')}><DatePicker showTime format="DD.MM.YYYY HH:mm" /></Form.Item>
          {closing && <Form.Item name="returnStatusId" label={t('repairs.returnStatus')} extra={t('repairs.returnStatusHint')}><LookupSelect lookup="asset-statuses" filter={(s) => ['InStock', 'Reserved', 'Assigned', 'WrittenOff', 'Disposed'].includes(s.kind)} /></Form.Item>}
          <Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item>
          <Space />
        </Form>
      </Modal>
    </>
  );
}
