import { Avatar, Button, Dropdown, Modal, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { post } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { Can, useAuth } from '@/app/auth';
import type { EmployeeListItem } from '@/api/types';
import { DataTable, type DataColumn } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect, LookupSelect } from '@/components/Selects';
import { StatusTag } from '@/components/Tags';
import { EMPLOYEE_KINDS } from '@/utils/enums';
import { fmtDate } from '@/utils/format';
import { EmployeeForm } from './EmployeeForm';

export default function EmployeesPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState<Record<string, unknown>>({ statusKind: params.get('statusKind') ?? undefined, hasAssets: params.get('hasAssets') ?? undefined });
  const [selected, setSelected] = useState<string[]>([]);
  const [bulk, setBulk] = useState<{ action: string; value?: string }>();
  const formOpen = params.get('new') === '1';
  const set = (k: string) => (v: unknown) => setFilters((f) => ({ ...f, [k]: v }));

  const bulkMutation = useApiMutation((v: { action: string; value?: string }) => post<{ succeeded: number; errors: { name?: string; message: string }[] }>('/employees/bulk', { ids: selected, ...v }), {
    invalidate: [['employees']],
    success: false,
    onSuccess: (r) => {
      Modal.info({ title: t('bulk.result', { count: r.succeeded }), content: r.errors.map((e, i) => <div key={i}>{e.name}: {e.message}</div>) });
      setSelected([]);
      setBulk(undefined);
    },
  });

  const columns: DataColumn<EmployeeListItem>[] = [
    { key: 'fullName', title: t('employees.fullName'), dataIndex: 'fullName', sorter: true, alwaysVisible: true,
      render: (v, r) => <Space><Avatar size="small" src={r.photoFileId ? `/api/files/${r.photoFileId}?inline=true` : undefined}>{v[0]}</Avatar><Link to={`/employees/${r.id}`}>{v}</Link></Space> },
    { key: 'employeeNumber', title: t('employees.number'), dataIndex: 'employeeNumber', sorter: true },
    { key: 'positionName', title: t('employees.position'), dataIndex: 'positionName', sorter: true },
    { key: 'departmentName', title: t('common.department'), dataIndex: 'departmentName', sorter: true },
    { key: 'regionName', title: t('common.region'), dataIndex: 'regionName', sorter: true },
    { key: 'locationName', title: t('employees.office'), dataIndex: 'locationName', hiddenByDefault: true },
    { key: 'email', title: 'Email', dataIndex: 'email', sorter: true, hiddenByDefault: true },
    { key: 'phone', title: t('employees.phone'), dataIndex: 'phone', hiddenByDefault: true },
    { key: 'login', title: t('employees.login'), dataIndex: 'login', hiddenByDefault: true },
    { key: 'statusName', title: t('common.status'), dataIndex: 'statusName', sorter: true, render: (v, r) => <StatusTag name={v} color={r.statusColor} /> },
    { key: 'hireDate', title: t('employees.hireDate'), dataIndex: 'hireDate', sorter: true, render: fmtDate, hiddenByDefault: true },
    { key: 'assetCount', title: t('employees.assetCount'), dataIndex: 'assetCount', render: (v) => (v ? <Tag color="blue">{v}</Tag> : <span className="itam-muted">0</span>) },
  ];

  return (
    <>
      <PageHeader title={t('menu.employees')} crumbs={[{ title: t('menu.employees') }]}
        extra={<Can perm="employees.create"><Button type="primary" icon={<PlusOutlined />} onClick={() => setParams({ new: '1' })}>{t('employees.new')}</Button></Can>} />
      <DataTable<EmployeeListItem>
        id="employees" url="/employees" exportUrl="/employees/export" columns={columns} params={filters}
        searchPlaceholder={t('employees.searchHint')}
        rowSelection={can('employees.bulk') ? { selectedRowKeys: selected, onChange: (k) => setSelected(k as string[]), preserveSelectedRowKeys: true } : undefined}
        filters={<>
          <LookupSelect lookup="regions" placeholder={t('common.region')} style={{ width: 160 }} onChange={set('regionId')} />
          <LookupSelect lookup="departments" placeholder={t('common.department')} style={{ width: 200 }} onChange={set('departmentId')} />
          <LookupSelect lookup="positions" placeholder={t('employees.position')} style={{ width: 180 }} onChange={set('positionId')} />
          <EnumSelect group="employeeKind" values={EMPLOYEE_KINDS} placeholder={t('common.status')} style={{ width: 150 }} value={filters.statusKind as string} onChange={set('statusKind')} />
        </>}
        toolbar={selected.length > 0 && (
          <Dropdown menu={{ items: [
            { key: 'changeRegion', label: t('bulk.changeRegion'), onClick: () => setBulk({ action: 'changeRegion' }) },
            { key: 'changeDepartment', label: t('bulk.changeDepartment'), onClick: () => setBulk({ action: 'changeDepartment' }) },
            { key: 'changePosition', label: t('bulk.changePosition'), onClick: () => setBulk({ action: 'changePosition' }) },
            { key: 'changeStatus', label: t('bulk.changeStatus'), onClick: () => setBulk({ action: 'changeStatus' }) },
            { key: 'archive', label: t('bulk.archive'), danger: true, onClick: () => Modal.confirm({ title: t('bulk.archiveConfirm', { count: selected.length }), onOk: () => bulkMutation.mutateAsync({ action: 'archive' }) }) },
          ] }}>
            <Button>{t('bulk.actions', { count: selected.length })}</Button>
          </Dropdown>
        )}
        onRow={(r) => ({ onDoubleClick: () => navigate(`/employees/${r.id}`) })}
      />
      <Modal open={!!bulk && bulk.action !== 'archive'} title={bulk && t(`bulk.${bulk.action}`)} onCancel={() => setBulk(undefined)} confirmLoading={bulkMutation.isPending}
        onOk={() => bulk && bulkMutation.mutate(bulk)}>
        {bulk?.action === 'changeRegion' && <LookupSelect lookup="regions" style={{ width: '100%' }} onChange={(v) => setBulk({ ...bulk, value: v })} />}
        {bulk?.action === 'changeDepartment' && <LookupSelect lookup="departments" style={{ width: '100%' }} onChange={(v) => setBulk({ ...bulk, value: v })} />}
        {bulk?.action === 'changePosition' && <LookupSelect lookup="positions" style={{ width: '100%' }} onChange={(v) => setBulk({ ...bulk, value: v })} />}
        {bulk?.action === 'changeStatus' && <LookupSelect lookup="employee-statuses" style={{ width: '100%' }} onChange={(v) => setBulk({ ...bulk, value: v })} />}
      </Modal>
      <EmployeeForm open={formOpen} onClose={() => setParams({})} onSaved={(e) => navigate(`/employees/${e.id}`)} />
    </>
  );
}
