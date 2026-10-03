import { Card, Input, Select, Space, Checkbox } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DocumentsTable } from '@/components/Documents';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect } from '@/components/Selects';
import { DOCUMENT_TYPES, SIGNATURE_STATUSES } from '@/utils/enums';

export default function DocumentsPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [filter, setFilter] = useState<Record<string, unknown>>({ search: params.get('search') ?? undefined, signatureStatus: params.get('signatureStatus') ?? undefined });
  const set = (k: string) => (v: unknown) => setFilter((f) => ({ ...f, [k]: v || undefined }));
  return (
    <>
      <PageHeader title={t('menu.documents')} crumbs={[{ title: t('menu.documents') }]} subtitle={t('documents.registryHint')} />
      <Card>
        <Space wrap style={{ marginBottom: 12 }}>
          <Input.Search allowClear defaultValue={filter.search as string} placeholder={t('documents.searchHint')} onSearch={set('search')} style={{ width: 280 }} />
          <EnumSelect group="documentType" values={DOCUMENT_TYPES} placeholder={t('documents.type')} style={{ width: 220 }} onChange={set('documentType')} />
          <Select allowClear placeholder={t('documents.employeeSignature')} style={{ width: 200 }} value={filter.signatureStatus as string} onChange={set('signatureStatus')}
            options={SIGNATURE_STATUSES.map((s) => ({ value: s, label: t(`enums.signature.${s}`) }))} />
          <Checkbox onChange={(e) => set('includeVoided')(e.target.checked)}>{t('documents.showVoided')}</Checkbox>
        </Space>
        <DocumentsTable filter={filter} />
      </Card>
    </>
  );
}
