import { Drawer, Table, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, type Paged } from '@/api/client';
import { useAuth } from '@/app/auth';
import type { LicenseListItem, LookupItem } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { DictionaryTable } from '@/pages/admin/DictionariesPage';
import { fmtDate } from '@/utils/format';

/** Software catalogue (dictionary) + licenses per product. */
export default function SoftwarePage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [selected, setSelected] = useState<LookupItem>();
  const licenses = useQuery<Paged<LicenseListItem>>({ queryKey: ['software-licenses', selected?.id], queryFn: () => get(`/licenses/by-software/${selected!.id}`), enabled: !!selected && can('licenses.view') });
  return (
    <>
      <PageHeader title={t('menu.software')} crumbs={[{ title: t('menu.software') }]} />
      <DictionaryTable lookupKey="software" onOpen={setSelected} />
      <Drawer open={!!selected} onClose={() => setSelected(undefined)} width={720} title={selected?.name}>
        <Table<LicenseListItem> rowKey="id" size="small" loading={licenses.isLoading} dataSource={licenses.data?.items} pagination={false}
          columns={[
            { title: t('licenses.license'), dataIndex: 'name', render: (v, r) => <Link to={`/licenses/${r.id}`}>{v}</Link> },
            { title: t('licenses.usage'), render: (_, r) => `${r.usedSeats}/${r.seats}` },
            { title: t('licenses.expiration'), dataIndex: 'expirationDate', render: (v, r) => <>{fmtDate(v)} {r.isExpired && <Tag color="red">{t('licenses.expired')}</Tag>}</> },
          ]} />
      </Drawer>
    </>
  );
}
