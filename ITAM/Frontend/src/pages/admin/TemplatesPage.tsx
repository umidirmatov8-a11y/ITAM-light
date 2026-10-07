import { Button, Card, Checkbox, Form, Input, Modal, Table, Tag, Upload } from 'antd';
import { PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, get } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect } from '@/components/Selects';
import { DOCUMENT_TYPES } from '@/utils/enums';
import { fmtDateTime } from '@/utils/format';

interface Tpl { id: string; name: string; code?: string; description?: string; documentType: string; isDefault: boolean; isArchived: boolean; activeVersion?: number; versionCount: number; updatedAt?: string }

export default function TemplatesPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File>();
  const [form] = Form.useForm();
  const q = useQuery<Tpl[]>({ queryKey: ['templates-admin'], queryFn: () => get('/templates', { includeArchived: true }) });
  const create = useApiMutation(async (v: any) => {
    const fd = new FormData();
    Object.entries(v).forEach(([k, x]) => x !== undefined && x !== null && fd.append(k, String(x)));
    fd.append('file', file!);
    return (await api.post<{ id: string }>('/templates', fd)).data;
  }, { invalidate: [['templates-admin'], ['templates']], onSuccess: (r) => { setOpen(false); navigate(`/admin/templates/${r.id}`); } });
  return (
    <>
      <PageHeader title={t('menu.templates')} crumbs={[{ title: t('menu.admin') }, { title: t('menu.templates') }]}
        extra={can('documents.templates.manage') && <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setFile(undefined); setOpen(true); }}>{t('templates.new')}</Button>} />
      <Card>
        <Table<Tpl> rowKey="id" size="small" loading={q.isLoading} dataSource={q.data} pagination={false} rowClassName={(r) => (r.isArchived ? 'itam-cancelled' : '')}
          columns={[
            { title: t('common.name'), dataIndex: 'name', render: (v, r) => <Link to={`/admin/templates/${r.id}`}>{v}</Link> },
            { title: t('documents.type'), dataIndex: 'documentType', render: (v) => t(`enums.documentType.${v}`) },
            { title: t('templates.activeVersion'), dataIndex: 'activeVersion', render: (v) => v && <Tag color="green">v{v}</Tag> },
            { title: t('templates.versions'), dataIndex: 'versionCount' },
            { title: t('templates.default'), dataIndex: 'isDefault', render: (v) => v && <Tag color="blue">{t('templates.default')}</Tag> },
            { title: t('common.updatedAt'), dataIndex: 'updatedAt', render: fmtDateTime },
            { title: t('common.description'), dataIndex: 'description' },
          ]} />
      </Card>
      <Modal open={open} title={t('templates.new')} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={create.isPending} okButtonProps={{ disabled: !file }}>
        <Form form={form} layout="vertical" onFinish={(v) => create.mutate(v)} initialValues={{ documentType: 'EquipmentIssue', isDefault: false }}>
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="documentType" label={t('documents.type')} rules={[{ required: true }]}><EnumSelect group="documentType" values={DOCUMENT_TYPES} allowClear={false} /></Form.Item>
          <Form.Item name="code" label={t('common.code')}><Input /></Form.Item>
          <Form.Item name="description" label={t('common.description')}><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="isDefault" valuePropName="checked"><Checkbox>{t('templates.makeDefault')}</Checkbox></Form.Item>
          <Upload accept=".docx" maxCount={1} beforeUpload={(f) => { setFile(f); return false; }} onRemove={() => setFile(undefined)}>
            <Button icon={<UploadOutlined />}>{t('templates.chooseDocx')}</Button>
          </Upload>
        </Form>
      </Modal>
    </>
  );
}
