import { Alert, Button, Card, Modal, Popconfirm, Space, Table, Tag, Upload } from 'antd';
import { CloudUploadOutlined, DownloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { del, download, get, post, upload } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import { PageHeader } from '@/components/PageHeader';
import { fmtDateTime, fmtSize } from '@/utils/format';

interface BackupItem { id: string; fileName: string; size: number; sha256?: string; kind: string; status: string; startedAt: string; completedAt?: string; createdByName?: string; error?: string; includesFiles: boolean; fileExists: boolean }

export default function BackupPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const notify = useNotify();
  const q = useQuery<BackupItem[]>({ queryKey: ['backups'], queryFn: () => get('/admin/backups') });
  const create = useApiMutation(() => post<BackupItem>('/admin/backups'), { invalidate: [['backups']], success: t('backup.created') });
  const remove = useApiMutation((id: string) => del(`/admin/backups/${id}`), { invalidate: [['backups']] });
  const restore = useApiMutation((id: string) => post(`/admin/backups/${id}/restore`), { success: t('backup.restored'), onSuccess: () => setTimeout(() => window.location.reload(), 1500) });
  const uploadRestore = useApiMutation((f: File) => upload('/admin/backups/upload-restore', f), { success: t('backup.restored'), onSuccess: () => setTimeout(() => window.location.reload(), 1500) });
  const confirmRestore = (fn: () => void) => Modal.confirm({ title: t('backup.restoreConfirm'), content: t('backup.restoreWarning'), okType: 'danger', okText: t('backup.restore'), onOk: fn });
  return (
    <>
      <PageHeader title={t('menu.backup')} crumbs={[{ title: t('menu.admin') }, { title: t('menu.backup') }]}
        extra={<>
          <Button type="primary" loading={create.isPending} onClick={() => create.mutate(undefined)}>{t('backup.create')}</Button>
          {can('backup.restore') && <Upload accept=".zip" showUploadList={false} beforeUpload={(f) => { confirmRestore(() => uploadRestore.mutate(f)); return false; }}>
            <Button danger icon={<CloudUploadOutlined />} loading={uploadRestore.isPending}>{t('backup.uploadRestore')}</Button></Upload>}
        </>} />
      <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t('backup.info')} />
      <Card>
        <Table<BackupItem> rowKey="id" size="small" loading={q.isLoading} dataSource={q.data} pagination={{ pageSize: 30 }} scroll={{ x: 'max-content' }}
          columns={[
            { title: t('backup.file'), dataIndex: 'fileName' },
            { title: t('backup.kind'), dataIndex: 'kind', render: (v) => <Tag>{t(`backup.kinds.${v}`)}</Tag> },
            { title: t('common.status'), dataIndex: 'status', render: (v, r) => <Tag color={v === 'Completed' ? 'green' : v === 'Failed' ? 'red' : 'blue'} title={r.error}>{t(`backup.statuses.${v}`)}</Tag> },
            { title: t('backup.started'), dataIndex: 'startedAt', render: fmtDateTime },
            { title: t('backup.size'), dataIndex: 'size', render: (v) => (v ? fmtSize(v) : '') },
            { title: t('backup.files'), dataIndex: 'includesFiles', render: (v) => (v ? t('common.yes') : t('common.no')) },
            { title: t('common.createdBy'), dataIndex: 'createdByName' },
            { title: 'SHA-256', dataIndex: 'sha256', render: (v) => v && <span className="itam-mono itam-muted">{v.slice(0, 12)}…</span> },
            { key: 'a', render: (_, r) => <Space>
              {r.fileExists && <Button size="small" icon={<DownloadOutlined />} onClick={() => download(`/admin/backups/${r.id}/download`).catch(notify.error)} />}
              {can('backup.restore') && r.fileExists && r.status === 'Completed' && <Button size="small" danger onClick={() => confirmRestore(() => restore.mutate(r.id))}>{t('backup.restore')}</Button>}
              <Popconfirm title={t('common.confirmDelete')} onConfirm={() => remove.mutate(r.id)}><Button size="small">{t('common.delete')}</Button></Popconfirm>
            </Space> },
          ]} />
      </Card>
    </>
  );
}
