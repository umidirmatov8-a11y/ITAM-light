import { useEffect, useMemo, useState } from 'react';
import { Select, Space, Tag, type SelectProps } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { get, type Paged } from '@/api/client';
import { useLookup } from '@/api/hooks';
import type { AssetListItem, EmployeeListItem, LookupItem } from '@/api/types';

type BaseProps = Omit<SelectProps, 'options' | 'loading'>;

/** Dropdown bound to a dictionary (/api/lookups/{key}/options) with optional client-side filter. */
export function LookupSelect({ lookup, filter, labelOf, ...rest }: BaseProps & { lookup: string; filter?: (i: LookupItem) => boolean; labelOf?: (i: LookupItem) => string }) {
  const { t } = useTranslation();
  const q = useLookup(lookup);
  const options = useMemo(
    () => (q.data ?? []).filter((i) => !filter || filter(i)).map((i) => ({ value: i.id, label: labelOf ? labelOf(i) : (i.fullPath as string) || i.name })),
    [q.data, filter, labelOf],
  );
  return <Select allowClear showSearch optionFilterProp="label" placeholder={t('common.select')} loading={q.isLoading} options={options} {...rest} />;
}

function useDebounced(value: string) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setV(value), 300);
    return () => clearTimeout(h);
  }, [value]);
  return v;
}

/** Remote employee search. */
export function EmployeeSelect({ activeOnly = true, initialLabel, ...rest }: BaseProps & { activeOnly?: boolean; initialLabel?: string }) {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const debounced = useDebounced(search);
  const q = useQuery({
    queryKey: ['employee-select', debounced, activeOnly],
    queryFn: () => get<Paged<EmployeeListItem>>('/employees', { search: debounced, pageSize: 30, activeOnly }),
  });
  const options = (q.data?.items ?? []).map((e) => ({
    value: e.id,
    label: `${e.fullName} (${e.employeeNumber})`,
    desc: [e.departmentName, e.positionName].filter(Boolean).join(' · '),
  }));
  if (initialLabel && rest.value && !options.some((o) => o.value === rest.value)) options.unshift({ value: rest.value as string, label: initialLabel, desc: '' });
  return (
    <Select
      showSearch
      allowClear
      filterOption={false}
      onSearch={setSearch}
      loading={q.isFetching}
      placeholder={t('common.searchEmployee')}
      options={options}
      optionRender={(o) => (
        <Space direction="vertical" size={0}>
          <span>{o.data.label}</span>
          {o.data.desc && <span className="itam-muted" style={{ fontSize: 12 }}>{o.data.desc}</span>}
        </Space>
      )}
      {...rest}
    />
  );
}

/** Remote asset search with optional server filters (e.g. statusKind=InStock or employeeId). */
export function AssetSelect({ filters, ...rest }: BaseProps & { filters?: Record<string, unknown> }) {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const debounced = useDebounced(search);
  const q = useQuery({
    queryKey: ['asset-select', debounced, filters],
    queryFn: () => get<Paged<AssetListItem>>('/assets', { search: debounced, pageSize: 30, ...filters }),
  });
  return (
    <Select
      showSearch
      allowClear
      filterOption={false}
      onSearch={setSearch}
      loading={q.isFetching}
      placeholder={t('common.searchAsset')}
      options={(q.data?.items ?? []).map((a) => ({ value: a.id, label: `${a.inventoryNumber} — ${a.name}`, status: a.statusName, color: a.statusColor, sn: a.serialNumber }))}
      optionRender={(o) => (
        <Space>
          <span>{o.data.label}</span>
          {o.data.sn && <span className="itam-muted">S/N {o.data.sn}</span>}
          <Tag color={o.data.color}>{o.data.status}</Tag>
        </Space>
      )}
      {...rest}
    />
  );
}

/** Select of enum values with translated labels. */
export function EnumSelect({ group, values, ...rest }: BaseProps & { group: string; values: readonly string[] }) {
  const { t } = useTranslation();
  return <Select allowClear placeholder={t('common.select')} options={values.map((v) => ({ value: v, label: t(`enums.${group}.${v}`, { defaultValue: v }) }))} {...rest} />;
}
