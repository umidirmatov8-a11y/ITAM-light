import { Button, Modal, Progress, Select, Space } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { post } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { ChecklistKind } from '@/api/types';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, LookupSelect } from '@/components/Selects';
import { EnumTag } from '@/components/Tags';
import { fmtDate, fmtDateTime } from '@/utils/format';

interface Row { id: string; employeeId: string; employeeName: string; departmentName?: string; regionName?: string; title: string; kind: string; status: string; startedAt: string; dueDate?: string; completedAt?: string; manualDone: number; total: number }

export default function ChecklistsPage({ kind }: { kind: ChecklistKind }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<Record<string, unknown>>({ status: 'InProgress' });
  const [start, setStart] = useState(false);
  const [employeeId, setEmployeeId] = useState<string>();
  const startMutation = useApiMutation(() => post<{ id: string }>(`/employees/${employeeId}/checklists`, { kind }), { invalidate: [['checklists']], onSuccess: (r) => navigate(`/checklists/${r.id}`) });
  const columns: DataColumn<Row>[] = [
    { key: 'employeeName', title: t('access.employee'), dataIndex: 'employeeName', alwaysVisible: true, render: (v, r) => <Link to={`/employees/${r.employeeId}`}>{v}</Link> },
    { key: 'title', title: t('checklists.title'), dataIndex: 'title', render: (v, r) => <Link to={`/checklists/${r.id}`}>{v}</Link> },
    { key: 'departmentName', title: t('common.department'), dataIndex: 'departmentName' },
    { key: 'regionName', title: t('common.region'), dataIndex: 'regionName' },
    { key: 'status', title: t('common.status'), dataIndex: 'status', render: (v) => <EnumTag group="checklistStatus" value={v} /> },
    { key: 'progress', title: t('checklists.progress'), render: (_, r) => <Progress size="small" style={{ width: 120 }} percent={r.total ? Math.round((r.manualDone / r.total) * 100) : 0} /> },
    { key: 'startedAt', title: t('checklists.startedAt'), dataIndex: 'startedAt', render: fmtDateTime },
    { key: 'dueDate', title: t('checklists.dueDate'), dataIndex: 'dueDate', render: fmtDate },
    { key: 'completedAt', title: t('checklists.completedAt'), dataIndex: 'completedAt', render: fmtDateTime, hiddenByDefault: true },
  ];
  return (
    <>
      <PageHeader title={t(kind === 'Onboarding' ? 'menu.onboarding' : 'menu.offboarding')} subtitle={t(kind === 'Onboarding' ? 'checklists.onboardingHint' : 'checklists.offboardingHint')}
        crumbs={[{ title: t('menu.lifecycle') }, { title: t(kind === 'Onboarding' ? 'menu.onboarding' : 'menu.offboarding') }]}
        extra={can('checklists.manage') && <Button type="primary" icon={<PlusOutlined />} onClick={() => setStart(true)}>{t('checklists.start')}</Button>} />
      <DataTable<Row> id={`checklists-${kind}`} url="/checklists" columns={columns} params={{ ...filters, kind }}
        filters={<>
          <Select allowClear style={{ width: 170 }} value={filters.status as string} onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
            options={['InProgress', 'Completed', 'Cancelled'].map((s) => ({ value: s, label: t(`enums.checklistStatus.${s}`) }))} placeholder={t('common.status')} />
          <LookupSelect lookup="regions" style={{ width: 160 }} placeholder={t('common.region')} onChange={(v) => setFilters((f) => ({ ...f, regionId: v }))} />
        </>} />
      <Modal open={start} title={t('checklists.start')} onCancel={() => setStart(false)} onOk={() => startMutation.mutate(undefined)} okButtonProps={{ disabled: !employeeId }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <EmployeeSelect activeOnly={kind === 'Onboarding'} style={{ width: '100%' }} value={employeeId} onChange={setEmployeeId} />
          {kind === 'Offboarding' && <span className="itam-muted">{t('checklists.offboardingStartHint')}</span>}
        </Space>
      </Modal>
    </>
  );
}
