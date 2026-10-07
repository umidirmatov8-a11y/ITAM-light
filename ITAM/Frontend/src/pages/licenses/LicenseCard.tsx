import { Alert, Button, Card, Col, DatePicker, Descriptions, Form, Input, InputNumber, Modal, Progress, Row, Skeleton, Space, Table, Tabs, Typography } from 'antd';
import { EditOutlined, EyeOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post, ApiError } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { License, LicenseAssignment } from '@/api/types';
import { Attachments } from '@/components/Attachments';
import { CustomFieldsView } from '@/components/CustomFields';
import { PageHeader } from '@/components/PageHeader';
import { AssetSelect, EmployeeSelect } from '@/components/Selects';
import { EnumTag } from '@/components/Tags';
import { fmtDate, fmtDateTime, fmtMoney, nowInTz, toApiDateTime } from '@/utils/format';
import { LicenseForm } from './LicenseForm';
import { ExpiryTag } from './LicensesPage';

export default function LicenseCard() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can } = useAuth();
  const notify = useNotify();
  const [edit, setEdit] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [key, setKey] = useState<string | null>();
  const [form] = Form.useForm();
  const q = useQuery<License>({ queryKey: ['license', id], queryFn: () => get(`/licenses/${id}`) });
  const assignments = useQuery<LicenseAssignment[]>({ queryKey: ['license-assignments', id], queryFn: () => get(`/licenses/${id}/assignments`) });
  const assign = useApiMutation((v: any) => post(`/licenses/${id}/assignments`, { ...v, assignedAt: toApiDateTime(v.assignedAt) }), {
    invalidate: [['license', id], ['license-assignments', id], ['licenses']], onSuccess: () => setAssignOpen(false),
  });
  const revoke = useApiMutation((aid: string) => post(`/licenses/assignments/${aid}/revoke`, {}), { invalidate: [['license', id], ['license-assignments', id], ['licenses']] });
  const archive = useApiMutation(() => post(`/licenses/${id}/archive`), { invalidate: [['license', id]] });

  const submitAssign = async (v: any) => {
    try {
      await assign.mutateAsync(v);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'LICENSE_EXPIRED')
        Modal.confirm({ title: t('licenses.expiredConfirm'), content: e.message, okText: t('licenses.assignAnyway'), onOk: () => assign.mutateAsync({ ...v, confirmExpired: true }) });
    }
  };
  const reveal = async () => {
    try {
      const r = await get<{ key: string | null }>(`/licenses/${id}/key`);
      setKey(r.key);
    } catch (e) {
      notify.error(e);
    }
  };

  if (q.isLoading || !q.data) return <Skeleton active />;
  const l = q.data;
  return (
    <>
      <PageHeader crumbs={[{ title: t('menu.licenses'), to: '/licenses' }, { title: l.name }]} title={l.name} tags={<><ExpiryTag days={l.daysToExpiry} expired={l.isExpired} />{l.isArchived && <EnumTag group="common" value="Archived" />}</>}
        subtitle={[l.softwareName, l.vendorName].filter(Boolean).join(' · ')}
        extra={<>
          {can('licenses.manage') && !l.isArchived && <Button type="primary" onClick={() => { form.resetFields(); form.setFieldsValue({ assignedAt: nowInTz(), seatCount: 1 }); setAssignOpen(true); }}>{t('licenses.assign')}</Button>}
          {can('licenses.manage') && <Button icon={<EditOutlined />} onClick={() => setEdit(true)}>{t('common.edit')}</Button>}
          {can('licenses.manage') && !l.isArchived && <Button onClick={() => Modal.confirm({ title: t('common.archiveConfirm'), onOk: () => archive.mutateAsync(undefined) })}>{t('common.archive')}</Button>}
        </>} />
      {l.isExpired && <Alert type="error" showIcon message={t('licenses.expiredAlert', { date: fmtDate(l.expirationDate) })} style={{ marginBottom: 16 }} />}
      <Tabs items={[
        {
          key: 'o', label: t('tabs.overview'), children: (
            <Row gutter={16}>
              <Col xs={24} xl={16}>
                <Card>
                  <Descriptions bordered size="small" column={{ xs: 1, sm: 1, md: 2, lg: 2, xl: 2, xxl: 3 }}>
                    <Descriptions.Item label={t('licenses.software')}>{l.softwareName}</Descriptions.Item>
                    <Descriptions.Item label={t('licenses.type')}>{l.licenseTypeName}</Descriptions.Item>
                    <Descriptions.Item label={t('licenses.model')}><EnumTag group="licenseModel" value={l.model} /></Descriptions.Item>
                    <Descriptions.Item label={t('common.region')}>{l.regionName ?? t('licenses.allRegions')}</Descriptions.Item>
                    <Descriptions.Item label={t('licenses.vendor')}>{l.vendorName}</Descriptions.Item>
                    <Descriptions.Item label={t('assets.supplier')}>{l.supplierName}</Descriptions.Item>
                    <Descriptions.Item label={t('licenses.key')} span={2}>
                      <Space><span className="itam-mono">{key ?? l.licenseKeyMasked ?? '—'}</span>
                        {l.licenseKeyMasked && can('licenses.keys.view') && key === undefined && <Button size="small" icon={<EyeOutlined />} onClick={reveal}>{t('licenses.showKey')}</Button>}
                        {key && <Typography.Text copyable={{ text: key }} />}
                      </Space>
                    </Descriptions.Item>
                    <Descriptions.Item label={t('assets.purchaseDate')}>{fmtDate(l.purchaseDate)}</Descriptions.Item>
                    <Descriptions.Item label={t('licenses.expiration')}>{fmtDate(l.expirationDate)}</Descriptions.Item>
                    <Descriptions.Item label={t('licenses.renewal')}>{fmtDate(l.renewalDate)}</Descriptions.Item>
                    <Descriptions.Item label={t('assets.price')}>{fmtMoney(l.cost, l.currency)}</Descriptions.Item>
                    <Descriptions.Item label={t('licenses.contract')}>{l.contractNumber}</Descriptions.Item>
                    <Descriptions.Item label={t('common.comment')}>{l.notes}</Descriptions.Item>
                  </Descriptions>
                  <CustomFieldsView entity="License" values={l.customFields} />
                </Card>
              </Col>
              <Col xs={24} xl={8}>
                <Card title={t('licenses.usage')}>
                  <Progress type="dashboard" percent={l.seats ? Math.round((l.usedSeats / l.seats) * 100) : 0} status={l.usedSeats > l.seats ? 'exception' : undefined} />
                  <Descriptions size="small" column={1}>
                    <Descriptions.Item label={t('licenses.summary.totalSeats')}>{l.seats}</Descriptions.Item>
                    <Descriptions.Item label={t('licenses.summary.usedSeats')}>{l.usedSeats}</Descriptions.Item>
                    <Descriptions.Item label={t('licenses.summary.availableSeats')}>{l.availableSeats}</Descriptions.Item>
                    <Descriptions.Item label={t('licenses.summary.expiredSeats')}>{l.expiredSeats}</Descriptions.Item>
                  </Descriptions>
                </Card>
              </Col>
            </Row>
          ),
        },
        {
          key: 'a', label: t('licenses.assignments'), children: (
            <Table<LicenseAssignment> rowKey="id" size="small" dataSource={assignments.data} loading={assignments.isLoading} pagination={{ pageSize: 50 }}
              rowClassName={(r) => (r.revokedAt ? 'itam-cancelled' : '')}
              columns={[
                { title: t('licenses.employee'), dataIndex: 'employeeName', render: (v, r) => r.employeeId && <Link to={`/employees/${r.employeeId}`}>{v}</Link> },
                { title: t('licenses.device'), dataIndex: 'assetInventoryNumber', render: (v, r) => r.assetId && <Link to={`/assets/${r.assetId}`}>{v}</Link> },
                { title: t('licenses.seats'), dataIndex: 'seatCount' },
                { title: t('licenses.assignedAt'), dataIndex: 'assignedAt', render: fmtDateTime },
                { title: t('licenses.revokedAt'), dataIndex: 'revokedAt', render: fmtDateTime },
                { title: t('common.comment'), dataIndex: 'comment' },
                { key: 'x', render: (_, r) => !r.revokedAt && can('licenses.manage') && <Button size="small" danger onClick={() => revoke.mutate(r.id)}>{t('licenses.revoke')}</Button> },
              ]} />
          ),
        },
        { key: 'f', label: t('tabs.attachments'), children: <Attachments entityType="License" entityId={l.id} /> },
      ]} />
      <LicenseForm open={edit} license={l} onClose={() => setEdit(false)} />
      <Modal open={assignOpen} title={t('licenses.assign')} onCancel={() => setAssignOpen(false)} onOk={() => form.submit()} confirmLoading={assign.isPending}>
        <Form form={form} layout="vertical" onFinish={submitAssign}>
          <Form.Item name="employeeId" label={t('licenses.employee')} rules={[{ required: l.model === 'PerUser' }]}><EmployeeSelect /></Form.Item>
          <Form.Item name="assetId" label={t('licenses.device')} rules={[{ required: l.model === 'PerDevice' }]}><AssetSelect /></Form.Item>
          <Form.Item name="assignedAt" label={t('licenses.assignedAt')}><DatePicker showTime format="DD.MM.YYYY HH:mm" /></Form.Item>
          <Form.Item name="seatCount" label={t('licenses.seats')}><InputNumber min={1} /></Form.Item>
          <Form.Item name="comment" label={t('common.comment')}><Input /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
