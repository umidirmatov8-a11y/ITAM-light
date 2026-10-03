import { Card, Empty, List, Spin, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { get } from '@/api/client';
import { PageHeader } from '@/components/PageHeader';

interface Result { query: string; hits: { kind: string; id: string; title: string; subtitle?: string; link: string }[]; exactLink?: string }

export default function SearchPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const q = params.get('q') ?? '';
  const r = useQuery<Result>({ queryKey: ['search', q], queryFn: () => get('/search', { q }), enabled: q.length >= 2 });
  useEffect(() => {
    // Exact inventory/serial/employee number → open the card directly.
    if (r.data?.exactLink && r.data.hits.length <= 1) navigate(r.data.exactLink, { replace: true });
  }, [r.data, navigate]);
  const groups = Object.entries((r.data?.hits ?? []).reduce<Record<string, Result['hits']>>((acc, h) => ((acc[h.kind] ??= []).push(h), acc), {}));
  return (
    <>
      <PageHeader title={t('search.title', { q })} crumbs={[{ title: t('search.crumb') }]} />
      {r.isLoading ? <Spin /> : groups.length === 0 ? <Empty description={t('search.nothing')} /> : groups.map(([kind, hits]) => (
        <Card key={kind} size="small" title={<Tag color="blue">{t(`search.kind.${kind}`)}</Tag>} style={{ marginBottom: 12 }}>
          <List size="small" dataSource={hits} renderItem={(h) => (
            <List.Item><List.Item.Meta title={<Link to={h.link}>{h.title}</Link>} description={h.subtitle} /></List.Item>
          )} />
        </Card>
      ))}
    </>
  );
}
