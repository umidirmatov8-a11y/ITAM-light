import { Button, Input, List, Popconfirm, Space, Upload } from 'antd';
import { DeleteOutlined, DownloadOutlined, EyeOutlined, PaperClipOutlined, UploadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { del, download, get, openInline, upload } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import type { StoredFile } from '@/api/types';
import { useAuth } from '@/app/auth';
import { fmtDateTime, fmtSize } from '@/utils/format';

/** Attachments (invoices, warranty, photos, acts) of an entity; every action is audited on the server. */
export function Attachments({ entityType, entityId }: { entityType: string; entityId: string }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const notify = useNotify();
  const [description, setDescription] = useState('');
  const key = ['files', entityType, entityId];
  const q = useQuery<StoredFile[]>({ queryKey: key, queryFn: () => get(`/files/${entityType}/${entityId}`) });
  const remove = useApiMutation((id: string) => del(`/files/${id}`), { invalidate: [key], success: t('common.deleted') });
  const uploadMutation = useApiMutation((file: File) => upload(`/files/${entityType}/${entityId}`, file, { description: description || undefined }), {
    invalidate: [key],
    success: t('files.uploaded'),
    onSuccess: () => setDescription(''),
  });
  return (
    <>
      {can('files.upload') && (
        <Space style={{ marginBottom: 12 }} wrap>
          <Input placeholder={t('files.description')} value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: 280 }} />
          <Upload showUploadList={false} beforeUpload={(f) => { uploadMutation.mutate(f); return false; }}>
            <Button icon={<UploadOutlined />} loading={uploadMutation.isPending}>{t('files.upload')}</Button>
          </Upload>
        </Space>
      )}
      <List
        loading={q.isLoading}
        dataSource={q.data ?? []}
        locale={{ emptyText: t('files.empty') }}
        renderItem={(f) => (
          <List.Item
            actions={[
              (f.contentType.startsWith('image/') || f.contentType === 'application/pdf') && (
                <Button key="v" type="link" icon={<EyeOutlined />} onClick={() => openInline(`/files/${f.id}`).catch(notify.error)} />
              ),
              <Button key="d" type="link" icon={<DownloadOutlined />} onClick={() => download(`/files/${f.id}`).catch(notify.error)} />,
              can('files.upload') && (
                <Popconfirm key="x" title={t('common.confirmDelete')} onConfirm={() => remove.mutate(f.id)}>
                  <Button type="link" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              ),
            ].filter(Boolean)}
          >
            <List.Item.Meta
              avatar={<PaperClipOutlined />}
              title={f.fileName}
              description={`${f.description ? f.description + ' · ' : ''}${fmtSize(f.size)} · ${fmtDateTime(f.createdAt)} · ${f.createdByName ?? ''} · SHA-256 ${f.sha256.slice(0, 12)}…`}
            />
          </List.Item>
        )}
      />
    </>
  );
}
