import { Alert, Button, Card, Checkbox, Col, Form, Input, Modal, Row, Skeleton, Space, Table, Tag, Typography, Upload } from 'antd';
import { DownloadOutlined, UploadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, download, get, post, put } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect } from '@/components/Selects';
import { DOCUMENT_TYPES } from '@/utils/enums';
import { fmtDateTime } from '@/utils/format';

interface Version { id: string; versionNumber: number; fileId: string; fileName: string; fileHash: string; changeNote?: string; isActive: boolean; createdAt: string; createdByName?: string; placeholders: string[]; documentsGenerated: number }
interface Tpl { id: string; name: string; code?: string; description?: string; documentType: string; isDefault: boolean; isArchived: boolean; versions: Version[]; availablePlaceholders: { key: string; description: string }[] }

export default function TemplateCard() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can } = useAuth();
  const notify = useNotify();
  const [form] = Form.useForm();
  const [vOpen, setVOpen] = useState(false);
  const [file, setFile] = useState<File>();
  const [note, setNote] = useState('');
  const q = useQuery<Tpl>({ queryKey: ['template', id], queryFn: () => get(`/templates/${id}`) });
  const manage = can('documents.templates.manage');
  const saveMeta = useApiMutation((v: any) => put(`/templates/${id}`, v), { invalidate: [['template', id], ['templates-admin']] });
  const activate = useApiMutation((vid: string) => post(`/templates/${id}/versions/${vid}/activate`), { invalidate: [['template', id], ['templates-admin']] });
  const archive = useApiMutation((archived: boolean) => post(`/templates/${id}/archive?archived=${archived}`), { invalidate: [['template', id], ['templates-admin']] });
  const addVersion = useApiMutation(async () => {
    const fd = new FormData();
    fd.append('file', file!);
    fd.append('changeNote', note);
    fd.append('activate', 'true');
    return (await api.post(`/templates/${id}/versions`, fd)).data;
  }, { invalidate: [['template', id], ['templates-admin']], onSuccess: () => { setVOpen(false); setFile(undefined); setNote(''); } });
  if (q.isLoading || !q.data) return <Skeleton active />;
  const tpl = q.data;
  const active = tpl.versions.find((v) => v.isActive);
  const unknown = active ? active.placeholders.filter((p) => !tpl.availablePlaceholders.some((a) => a.key === p || (a.key.includes('<') && p.startsWith(a.key.split('<')[0])))) : [];
  return (
    <>
      <PageHeader crumbs={[{ title: t('menu.templates'), to: '/admin/templates' }, { title: tpl.name }]} title={tpl.name}
        tags={<>{tpl.isDefault && <Tag color="blue">{t('templates.default')}</Tag>}{tpl.isArchived && <Tag>{t('common.archived')}</Tag>}</>}
        extra={manage && <>
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setVOpen(true)}>{t('templates.newVersion')}</Button>
          <Button onClick={() => archive.mutate(!tpl.isArchived)}>{tpl.isArchived ? t('common.restore') : t('common.archive')}</Button>
        </>} />
      <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t('templates.versioningHint')} />
      <Row gutter={16}>
        <Col xs={24} xl={14}>
          <Card title={t('templates.versions')} style={{ marginBottom: 16 }}>
            <Table<Version> rowKey="id" size="small" dataSource={tpl.versions} pagination={false}
              columns={[
                { title: t('templates.version'), dataIndex: 'versionNumber', render: (v, r) => <Space>v{v}{r.isActive && <Tag color="green">{t('templates.active')}</Tag>}</Space> },
                { title: t('common.createdAt'), dataIndex: 'createdAt', render: fmtDateTime },
                { title: t('common.createdBy'), dataIndex: 'createdByName' },
                { title: t('templates.changeNote'), dataIndex: 'changeNote' },
                { title: t('templates.generated'), dataIndex: 'documentsGenerated' },
                { title: 'SHA-256', dataIndex: 'fileHash', render: (v) => <span className="itam-mono itam-muted">{v.slice(0, 10)}…</span> },
                { key: 'a', render: (_, r) => <Space>
                  <Button size="small" icon={<DownloadOutlined />} onClick={() => download(`/templates/${id}/versions/${r.id}/download`).catch(notify.error)} />
                  {manage && !r.isActive && <Button size="small" onClick={() => activate.mutate(r.id)}>{t('templates.activate')}</Button>}
                </Space> },
              ]} />
          </Card>
          {active && (
            <Card title={t('templates.usedPlaceholders', { v: active.versionNumber })}>
              {active.placeholders.map((p) => <Tag key={p} color={unknown.includes(p) ? 'red' : 'blue'} className="itam-mono">{`{{${p}}}`}</Tag>)}
              {unknown.length > 0 && <Alert type="warning" showIcon style={{ marginTop: 12 }} message={t('templates.unknownPlaceholders')} />}
            </Card>
          )}
        </Col>
        <Col xs={24} xl={10}>
          {manage && (
            <Card title={t('templates.properties')} style={{ marginBottom: 16 }}>
              <Form form={form} layout="vertical" initialValues={tpl} onFinish={(v) => saveMeta.mutate(v)}>
                <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="documentType" label={t('documents.type')}><EnumSelect group="documentType" values={DOCUMENT_TYPES} allowClear={false} /></Form.Item>
                <Form.Item name="code" label={t('common.code')}><Input /></Form.Item>
                <Form.Item name="description" label={t('common.description')}><Input.TextArea rows={2} /></Form.Item>
                <Form.Item name="isDefault" valuePropName="checked"><Checkbox>{t('templates.makeDefault')}</Checkbox></Form.Item>
                <Button htmlType="submit" type="primary" loading={saveMeta.isPending}>{t('common.save')}</Button>
              </Form>
            </Card>
          )}
          <Card title={t('templates.placeholders')}>
            <Typography.Paragraph type="secondary">{t('templates.placeholdersHint')}</Typography.Paragraph>
            <Table size="small" rowKey="key" pagination={false} dataSource={tpl.availablePlaceholders}
              columns={[
                { title: t('templates.placeholder'), dataIndex: 'key', render: (v) => <Typography.Text code copyable={{ text: `{{${v}}}` }}>{`{{${v}}}`}</Typography.Text> },
                { title: t('common.description'), dataIndex: 'description' },
              ]} />
          </Card>
        </Col>
      </Row>
      <Modal open={vOpen} title={t('templates.newVersion')} onCancel={() => setVOpen(false)} onOk={() => addVersion.mutate(undefined)} okButtonProps={{ disabled: !file }} confirmLoading={addVersion.isPending}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Upload accept=".docx" maxCount={1} beforeUpload={(f) => { setFile(f); return false; }} onRemove={() => setFile(undefined)}><Button icon={<UploadOutlined />}>{t('templates.chooseDocx')}</Button></Upload>
          <Input.TextArea rows={2} placeholder={t('templates.changeNote')} value={note} onChange={(e) => setNote(e.target.value)} />
        </Space>
      </Modal>
    </>
  );
}
