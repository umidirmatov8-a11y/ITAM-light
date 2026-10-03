import { Avatar, Button, Card, Col, Descriptions, Dropdown, Empty, Modal, Row, Skeleton, Space, Table, Tabs, Tag, Upload } from 'antd';
import { EditOutlined, MoreOutlined, RollbackOutlined, SendOutlined, UploadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { del, get, post, upload } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { AccessItem, AssetListItem, Checklist, Employee, LicenseAssignment, TimelineItem } from '@/api/types';
import { Attachments } from '@/components/Attachments';
import { AuditTable, type AuditRow } from '@/components/AuditTable';
import { ChecklistView } from '@/components/ChecklistView';
import { CustomFieldsView } from '@/components/CustomFields';
import { DocumentsTable, GenerateDocumentButton } from '@/components/Documents';
import { PageHeader } from '@/components/PageHeader';
import { EnumTag, StatusTag } from '@/components/Tags';
import { TimelineView } from '@/components/TimelineView';
import { fmtDate, fmtDateTime } from '@/utils/format';
import { EmployeeForm } from './EmployeeForm';
import { TerminateModal } from './TerminateModal';
import { AccessForm } from '@/pages/access/AccessForm';

export default function EmployeeCard() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [edit, setEdit] = useState(false);
  const [terminate, setTerminate] = useState(false);
  const [grant, setGrant] = useState(false);
  const [tab, setTab] = useState('overview');
  const q = useQuery<Employee>({ queryKey: ['employee', id], queryFn: () => get(`/employees/${id}`) });
  const assets = useQuery<AssetListItem[]>({ queryKey: ['employee-assets', id], queryFn: () => get(`/employees/${id}/assets`), enabled: can('assets.view') });
  const licenses = useQuery<LicenseAssignment[]>({ queryKey: ['employee-licenses', id], queryFn: () => get(`/licenses/by-employee/${id}`), enabled: tab === 'licenses' });
  const access = useQuery<{ items: AccessItem[] }>({ queryKey: ['employee-access', id], queryFn: () => get('/access', { employeeId: id, pageSize: 200 }), enabled: tab === 'access' });
  const checklists = useQuery<Checklist[]>({ queryKey: ['employee-checklists', id], queryFn: () => get(`/employees/${id}/checklists`), enabled: tab === 'checklists' && can('checklists.view') });
  const timeline = useQuery<TimelineItem[]>({ queryKey: ['employee-timeline', id], queryFn: () => get(`/employees/${id}/timeline`), enabled: tab === 'history' });
  const orgHistory = useQuery<any[]>({ queryKey: ['employee-org', id], queryFn: () => get(`/employees/${id}/org-history`), enabled: tab === 'org' });
  const audit = useQuery<AuditRow[]>({ queryKey: ['employee-audit', id], queryFn: () => get(`/audit/entity/Employee/${id}`), enabled: tab === 'audit' && can('audit.view') });

  const startChecklist = useApiMutation((kind: string) => post(`/employees/${id}/checklists`, { kind }), { invalidate: [['employee-checklists', id]], onSuccess: () => setTab('checklists') });
  const archive = useApiMutation(() => post(`/employees/${id}/archive`), { invalidate: [['employee', id]] });
  const remove = useApiMutation(() => del(`/employees/${id}`), { onSuccess: () => navigate('/employees') });
  const photo = useApiMutation((file: File) => upload(`/files/Employee/${id}`, file, { photo: true }), { invalidate: [['employee', id]] });
  const revokeAccess = useApiMutation((accessId: string) => post(`/access/${accessId}/revoke`, {}), { invalidate: [['employee-access', id], ['employee', id]] });
  const revokeLicense = useApiMutation((aid: string) => post(`/licenses/assignments/${aid}/revoke`, {}), { invalidate: [['employee-licenses', id], ['employee', id]] });

  if (q.isLoading || !q.data) return <Skeleton active />;
  const e = q.data;
  const terminated = e.statusKind === 'Terminated' || e.statusKind === 'Archived';

  return (
    <>
      <PageHeader
        crumbs={[{ title: t('menu.employees'), to: '/employees' }, { title: e.fullName }]}
        title={<Space><Avatar size={48} src={e.photoFileId ? `/api/files/${e.photoFileId}?inline=true` : undefined}>{e.lastName[0]}</Avatar>{e.fullName}</Space>}
        tags={<StatusTag name={e.statusName} color={e.statusColor} />}
        subtitle={[e.employeeNumber, e.positionName, e.departmentPath ?? e.departmentName, e.regionName].filter(Boolean).join(' · ')}
        extra={<>
          {can('assets.assign') && !terminated && <Button type="primary" icon={<SendOutlined />} onClick={() => navigate(`/operations/issue?employeeId=${id}`)}>{t('assets.actions.issue')}</Button>}
          {can('assets.return') && e.assetCount > 0 && <Button icon={<RollbackOutlined />} onClick={() => navigate(`/operations/return?employeeId=${id}`)}>{t('assets.actions.return')}</Button>}
          {can('employees.edit') && <Button icon={<EditOutlined />} onClick={() => setEdit(true)}>{t('common.edit')}</Button>}
          <Dropdown menu={{ items: [
            can('checklists.manage') && { key: 'on', label: t('employees.startOnboardingNow'), onClick: () => startChecklist.mutate('Onboarding') },
            can('checklists.manage') && { key: 'off', label: t('employees.startOffboardingNow'), onClick: () => startChecklist.mutate('Offboarding') },
            can('employees.terminate') && !terminated && { key: 'term', danger: true, label: t('offboarding.terminate'), onClick: () => setTerminate(true) },
            can('employees.delete') && { key: 'arch', label: t('employees.archive'), onClick: () => Modal.confirm({ title: t('employees.archiveConfirm'), onOk: () => archive.mutateAsync(undefined) }) },
            can('employees.delete') && { key: 'del', danger: true, label: t('common.delete'), onClick: () => Modal.confirm({ title: t('employees.deleteConfirm'), content: t('employees.deleteHint'), onOk: () => remove.mutateAsync(undefined) }) },
          ].filter(Boolean) as never }}>
            <Button icon={<MoreOutlined />} />
          </Dropdown>
        </>}
      />
      <Tabs activeKey={tab} onChange={setTab} items={[
        {
          key: 'overview', label: t('tabs.overview'), children: (
            <Row gutter={16}>
              <Col xs={24} xl={16}>
                <Card>
                  <Descriptions bordered size="small" column={{ xs: 1, sm: 1, md: 2, lg: 2, xl: 2, xxl: 3 }}>
                    <Descriptions.Item label={t('employees.number')}>{e.employeeNumber}</Descriptions.Item>
                    <Descriptions.Item label={t('common.status')}><StatusTag name={e.statusName} color={e.statusColor} /></Descriptions.Item>
                    <Descriptions.Item label={t('employees.position')}>{e.positionName}</Descriptions.Item>
                    <Descriptions.Item label={t('common.department')}>{e.departmentPath ?? e.departmentName}</Descriptions.Item>
                    <Descriptions.Item label={t('common.region')}>{e.regionName}</Descriptions.Item>
                    <Descriptions.Item label={t('employees.office')}>{e.locationName}</Descriptions.Item>
                    <Descriptions.Item label={t('employees.room')}>{e.roomName}</Descriptions.Item>
                    <Descriptions.Item label={t('employees.manager')}>{e.managerId ? <Link to={`/employees/${e.managerId}`}>{e.managerName}</Link> : null}</Descriptions.Item>
                    <Descriptions.Item label={t('employees.login')}>{e.login}</Descriptions.Item>
                    <Descriptions.Item label="Email">{e.email}</Descriptions.Item>
                    <Descriptions.Item label={t('employees.phone')}>{e.phone}</Descriptions.Item>
                    <Descriptions.Item label={t('employees.hireDate')}>{fmtDate(e.hireDate)}</Descriptions.Item>
                    <Descriptions.Item label={t('employees.terminationDate')}>{fmtDate(e.terminationDate)}</Descriptions.Item>
                    <Descriptions.Item label={t('common.updatedAt')}>{fmtDateTime(e.updatedAt ?? e.createdAt)}</Descriptions.Item>
                    <Descriptions.Item label={t('common.comment')} span={2}>{e.comment}</Descriptions.Item>
                  </Descriptions>
                  <CustomFieldsView entity="Employee" values={e.customFields} />
                </Card>
              </Col>
              <Col xs={24} xl={8}>
                <Card size="small" title={t('employees.summary')}>
                  <Space direction="vertical">
                    <span>{t('employees.assetCount')}: <Tag color="blue">{e.assetCount}</Tag></span>
                    <span>{t('menu.licenses')}: <Tag color="purple">{e.licenseCount}</Tag></span>
                    <span>{t('menu.access')}: <Tag color="cyan">{e.accessCount}</Tag></span>
                  </Space>
                  {can('files.upload') && (
                    <div style={{ marginTop: 16 }}>
                      <Upload showUploadList={false} accept="image/*" beforeUpload={(f) => { photo.mutate(f); return false; }}>
                        <Button icon={<UploadOutlined />}>{t('employees.uploadPhoto')}</Button>
                      </Upload>
                    </div>
                  )}
                  {terminated && can('documents.generate') && <div style={{ marginTop: 12 }}><GenerateDocumentButton sourceType="Employee" sourceId={e.id} documentType="EmployeeOffboarding" /></div>}
                </Card>
              </Col>
            </Row>
          ),
        },
        can('assets.view') && {
          key: 'assets', label: <>{t('tabs.assets')} <Tag>{e.assetCount}</Tag></>, children: (
            <Table<AssetListItem> rowKey="id" size="small" loading={assets.isLoading} dataSource={assets.data} pagination={false}
              columns={[
                { title: t('assets.inventoryNumber'), dataIndex: 'inventoryNumber', render: (v, r) => <Link to={`/assets/${r.id}`}>{v}</Link> },
                { title: t('assets.name'), dataIndex: 'name' },
                { title: t('assets.type'), dataIndex: 'typeName' },
                { title: t('assets.serialNumber'), dataIndex: 'serialNumber' },
                { title: t('common.status'), dataIndex: 'statusName', render: (v, r) => <StatusTag name={v} color={r.statusColor} /> },
              ]} />
          ),
        },
        can('licenses.view') && {
          key: 'licenses', label: t('menu.licenses'), children: (
            <Table<LicenseAssignment> rowKey="id" size="small" loading={licenses.isLoading} dataSource={licenses.data} pagination={false}
              columns={[
                { title: t('licenses.license'), dataIndex: 'licenseName', render: (v, r) => <Link to={`/licenses/${r.licenseId}`}>{v}</Link> },
                { title: t('licenses.software'), dataIndex: 'softwareName' },
                { title: t('licenses.device'), dataIndex: 'assetInventoryNumber' },
                { title: t('licenses.assignedAt'), dataIndex: 'assignedAt', render: fmtDateTime },
                { title: t('licenses.revokedAt'), dataIndex: 'revokedAt', render: fmtDateTime },
                { key: 'a', render: (_, r) => !r.revokedAt && can('licenses.manage') && <Button size="small" danger onClick={() => revokeLicense.mutate(r.id)}>{t('licenses.revoke')}</Button> },
              ]} />
          ),
        },
        can('access.view') && {
          key: 'access', label: t('menu.access'), children: (
            <>
              {can('access.manage') && !terminated && <Button style={{ marginBottom: 12 }} type="primary" onClick={() => setGrant(true)}>{t('access.grant')}</Button>}
              <Table<AccessItem> rowKey="id" size="small" loading={access.isLoading} dataSource={access.data?.items} pagination={false}
                columns={[
                  { title: t('access.system'), dataIndex: 'systemName' },
                  { title: t('access.username'), dataIndex: 'username' },
                  { title: t('access.level'), dataIndex: 'levelName' },
                  { title: t('access.role'), dataIndex: 'role' },
                  { title: t('common.status'), dataIndex: 'status', render: (v) => <EnumTag group="accessStatus" value={v} /> },
                  { title: t('access.grantedAt'), dataIndex: 'grantedAt', render: fmtDateTime },
                  { title: t('access.revokedAt'), dataIndex: 'revokedAt', render: fmtDateTime },
                  { key: 'a', render: (_, r) => r.status !== 'Revoked' && can('access.manage') && <Button size="small" danger onClick={() => revokeAccess.mutate(r.id)}>{t('access.revoke')}</Button> },
                ]} />
            </>
          ),
        },
        can('documents.view') && { key: 'documents', label: t('tabs.documents'), children: <DocumentsTable filter={{ employeeId: id }} /> },
        can('checklists.view') && {
          key: 'checklists', label: t('tabs.checklists'), children: checklists.data?.length
            ? <Space direction="vertical" style={{ width: '100%' }} size={16}>{checklists.data.map((c) => <Card key={c.id} size="small"><ChecklistView checklist={c} invalidate={[['employee-checklists', id]]} /></Card>)}</Space>
            : <Empty />,
        },
        { key: 'history', label: t('tabs.history'), children: <Card><TimelineView items={timeline.data} /></Card> },
        {
          key: 'org', label: t('tabs.orgHistory'), children: (
            <Table rowKey="id" size="small" dataSource={orgHistory.data} pagination={false}
              columns={[
                { title: t('employees.effectiveFrom'), dataIndex: 'effectiveFrom', render: fmtDateTime },
                { title: t('employees.effectiveTo'), dataIndex: 'effectiveTo', render: fmtDateTime },
                { title: t('common.department'), dataIndex: 'department' },
                { title: t('employees.position'), dataIndex: 'position' },
                { title: t('common.region'), dataIndex: 'region' },
                { title: t('employees.office'), dataIndex: 'location' },
                { title: t('employees.manager'), dataIndex: 'manager' },
                { title: t('common.reason'), dataIndex: 'reason' },
                { title: t('common.recordedAt'), dataIndex: 'recordedAt', render: fmtDateTime },
              ]} />
          ),
        },
        { key: 'files', label: t('tabs.attachments'), children: <Attachments entityType="Employee" entityId={e.id} /> },
        can('audit.view') && { key: 'audit', label: t('tabs.audit'), children: <AuditTable rows={audit.data} loading={audit.isLoading} /> },
      ].filter(Boolean) as never} />
      <EmployeeForm open={edit} employee={e} onClose={() => setEdit(false)} />
      <TerminateModal employeeId={e.id} open={terminate} onClose={() => setTerminate(false)} />
      <AccessForm open={grant} employeeId={e.id} onClose={() => setGrant(false)} invalidate={[['employee-access', id], ['employee', id]]} />
    </>
  );
}
