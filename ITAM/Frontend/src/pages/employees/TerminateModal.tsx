import { Alert, Checkbox, DatePicker, Form, Input, List, Modal, Space, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { get, post } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { dayjs, fmtDate, toApiDate } from '@/utils/format';

interface OpenItems {
  assets: { assetId: string; inventoryNumber: string; name: string; type?: string; assignedAt?: string }[];
  licenses: { assignmentId: string; licenseName: string; software?: string }[];
  accesses: { id: string; system: string; username?: string; status: string }[];
  repairs: { id: string; number: string; assetInventoryNumber: string; status: string }[];
  unsignedDocuments: { id: string; number: string; title: string }[];
  checklists: { id: string; title: string; kind: string; done: number; total: number }[];
  total: number;
}

export function useOpenItems(employeeId?: string, enabled = true) {
  return useQuery<OpenItems>({ queryKey: ['open-items', employeeId], queryFn: () => get(`/employees/${employeeId}/open-items`), enabled: !!employeeId && enabled });
}

export function OpenItemsList({ items }: { items?: OpenItems }) {
  const { t } = useTranslation();
  if (!items) return null;
  const section = (title: string, data: { key: string; node: React.ReactNode }[]) =>
    data.length > 0 && (
      <div style={{ marginBottom: 8 }}>
        <Typography.Text strong>{title} <Tag color="red">{data.length}</Tag></Typography.Text>
        <List size="small" dataSource={data} renderItem={(d) => <List.Item key={d.key}>{d.node}</List.Item>} />
      </div>
    );
  return (
    <>
      {section(t('offboarding.assets'), items.assets.map((a) => ({ key: a.assetId, node: <Space><Link to={`/assets/${a.assetId}`}>{a.inventoryNumber}</Link>{a.name}<span className="itam-muted">{fmtDate(a.assignedAt)}</span></Space> })))}
      {section(t('offboarding.licenses'), items.licenses.map((l) => ({ key: l.assignmentId, node: <>{l.licenseName} {l.software && <span className="itam-muted">({l.software})</span>}</> })))}
      {section(t('offboarding.accesses'), items.accesses.map((a) => ({ key: a.id, node: <>{a.system} {a.username && <span className="itam-mono">{a.username}</span>}</> })))}
      {section(t('offboarding.repairs'), items.repairs.map((r) => ({ key: r.id, node: <Link to={`/repairs/${r.id}`}>{r.number} · {r.assetInventoryNumber} · {r.status}</Link> })))}
      {section(t('offboarding.documents'), items.unsignedDocuments.map((d) => ({ key: d.id, node: <>{d.number} — {d.title}</> })))}
      {section(t('offboarding.checklists'), items.checklists.map((c) => ({ key: c.id, node: <Link to={`/checklists/${c.id}`}>{c.title} ({c.done}/{c.total})</Link> })))}
    </>
  );
}

export function TerminateModal({ employeeId, open, onClose }: { employeeId: string; open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const items = useOpenItems(employeeId, open);
  const hasOpen = (items.data?.total ?? 0) > 0;
  const terminate = useApiMutation((v: any) => post(`/employees/${employeeId}/terminate`, { ...v, terminationDate: toApiDate(v.terminationDate) }), {
    invalidate: [['employee', employeeId], ['employees'], ['employee-checklists', employeeId]],
    onSuccess: onClose,
  });
  return (
    <Modal open={open} onCancel={onClose} title={t('offboarding.terminateTitle')} okText={t('offboarding.terminate')} okButtonProps={{ danger: true, loading: terminate.isPending }}
      onOk={() => form.submit()} width={720} destroyOnHidden>
      {hasOpen ? <Alert type="warning" showIcon message={t('offboarding.openItemsWarning')} style={{ marginBottom: 12 }} /> : <Alert type="success" showIcon message={t('offboarding.noOpenItems')} style={{ marginBottom: 12 }} />}
      <OpenItemsList items={items.data} />
      <Form form={form} layout="vertical" initialValues={{ terminationDate: dayjs(), startOffboarding: true }} onFinish={(v) => terminate.mutate(v)}>
        <Form.Item name="terminationDate" label={t('offboarding.terminationDate')} rules={[{ required: true }]}><DatePicker format="DD.MM.YYYY" /></Form.Item>
        <Form.Item name="reason" label={t('common.reason')}><Input.TextArea rows={2} /></Form.Item>
        <Form.Item name="startOffboarding" valuePropName="checked"><Checkbox>{t('offboarding.startChecklist')}</Checkbox></Form.Item>
        {hasOpen && <Form.Item name="force" valuePropName="checked"><Checkbox>{t('offboarding.force')}</Checkbox></Form.Item>}
      </Form>
    </Modal>
  );
}
