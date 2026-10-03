import { Card, Skeleton } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { get } from '@/api/client';
import type { Checklist } from '@/api/types';
import { ChecklistView } from '@/components/ChecklistView';
import { DocumentsTable } from '@/components/Documents';
import { PageHeader } from '@/components/PageHeader';
import { OpenItemsList, useOpenItems } from '@/pages/employees/TerminateModal';

export default function ChecklistCard() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const q = useQuery<Checklist>({ queryKey: ['checklist', id], queryFn: () => get(`/checklists/${id}`) });
  const open = useOpenItems(q.data?.employeeId, q.data?.kind === 'Offboarding');
  if (q.isLoading || !q.data) return <Skeleton active />;
  const c = q.data;
  return (
    <>
      <PageHeader crumbs={[{ title: t(c.kind === 'Onboarding' ? 'menu.onboarding' : 'menu.offboarding'), to: c.kind === 'Onboarding' ? '/onboarding' : '/offboarding' }, { title: c.employeeName }]}
        title={c.title} subtitle={<Link to={`/employees/${c.employeeId}`}>{c.employeeName}</Link>} />
      <Card style={{ marginBottom: 16 }}><ChecklistView checklist={c} invalidate={[['checklist', id], ['open-items', c.employeeId]]} /></Card>
      {c.kind === 'Offboarding' && <Card title={t('offboarding.openItems')} style={{ marginBottom: 16 }}>{open.data && open.data.total === 0 ? t('offboarding.noOpenItems') : <OpenItemsList items={open.data} />}</Card>}
      <Card title={t('tabs.documents')}><DocumentsTable filter={{ sourceType: 'EmployeeChecklist', sourceId: c.id }} /></Card>
    </>
  );
}
