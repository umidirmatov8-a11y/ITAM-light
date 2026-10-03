import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Button, Checkbox, Dropdown, Input, Popover, Space, Table, Tooltip } from 'antd';
import type { ColumnsType, TablePaginationConfig, TableProps } from 'antd/es/table';
import type { SorterResult } from 'antd/es/table/interface';
import { DownloadOutlined, ReloadOutlined, SettingOutlined } from '@ant-design/icons';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { download, get, type Paged } from '@/api/client';
import { useAuth } from '@/app/auth';
import { useNotify } from '@/api/hooks';

export type DataColumn<T> = ColumnsType<T>[number] & { key: string; hiddenByDefault?: boolean; alwaysVisible?: boolean };

interface Props<T> {
  id: string;
  url: string;
  columns: DataColumn<T>[];
  params?: Record<string, unknown>;
  exportUrl?: string;
  toolbar?: ReactNode;
  filters?: ReactNode;
  rowSelection?: TableProps<T>['rowSelection'];
  defaultPageSize?: number;
  searchPlaceholder?: string;
  onRow?: TableProps<T>['onRow'];
  size?: 'small' | 'middle';
  defaultSort?: { field: string; order: 'asc' | 'desc' };
}

/** Server-side table: search, sort, pagination, column selection (remembered per user), export. */
export function DataTable<T extends { id: string }>({ id, url, columns, params, exportUrl, toolbar, filters, rowSelection, defaultPageSize = 25, searchPlaceholder, onRow, size = 'middle', defaultSort }: Props<T>) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const notify = useNotify();
  const storageKey = `itam.table.${id}`;
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(() => Number(localStorage.getItem(storageKey + '.size')) || defaultPageSize);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<{ field?: string; order?: 'asc' | 'desc' }>(defaultSort ?? {});
  const [hidden, setHidden] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(storageKey + '.hidden');
      if (raw) return JSON.parse(raw);
    } catch {
      /* ignore */
    }
    return columns.filter((c) => c.hiddenByDefault).map((c) => c.key);
  });
  useEffect(() => {
    try {
      localStorage.setItem(storageKey + '.hidden', JSON.stringify(hidden));
      localStorage.setItem(storageKey + '.size', String(pageSize));
    } catch {
      /* ignore */
    }
  }, [hidden, pageSize, storageKey]);
  useEffect(() => setPage(1), [JSON.stringify(params), search]);

  const query = useQuery<Paged<T>>({
    queryKey: [id, url, params, page, pageSize, search, sort],
    queryFn: () => get<Paged<T>>(url, { ...params, page, pageSize, search, sort: sort.field, order: sort.order }),
    placeholderData: keepPreviousData,
  });

  const visibleColumns = useMemo(
    () => columns.filter((c) => c.alwaysVisible || !hidden.includes(c.key)).map((c) => ({ ...c, sortOrder: c.key === sort.field ? (sort.order === 'desc' ? 'descend' : 'ascend') : null })) as ColumnsType<T>,
    [columns, hidden, sort],
  );

  const onChange = (p: TablePaginationConfig, _f: unknown, s: SorterResult<T> | SorterResult<T>[]) => {
    setPage(p.current ?? 1);
    if (p.pageSize && p.pageSize !== pageSize) setPageSize(p.pageSize);
    const one = Array.isArray(s) ? s[0] : s;
    setSort(one?.order ? { field: String(one.columnKey ?? one.field), order: one.order === 'descend' ? 'desc' : 'asc' } : defaultSort ?? {});
  };

  const doExport = async (format: string) => {
    try {
      await download(exportUrl!, { ...params, search, sort: sort.field, order: sort.order, format });
    } catch (e) {
      notify.error(e);
    }
  };

  const columnPicker = (
    <Space direction="vertical" size={4} style={{ maxHeight: 360, overflow: 'auto' }}>
      {columns.filter((c) => !c.alwaysVisible).map((c) => (
        <Checkbox key={c.key} checked={!hidden.includes(c.key)} onChange={(e) => setHidden((h) => (e.target.checked ? h.filter((k) => k !== c.key) : [...h, c.key]))}>
          {c.title as ReactNode}
        </Checkbox>
      ))}
    </Space>
  );

  return (
    <>
      <div className="itam-table-toolbar">
        <Input.Search allowClear placeholder={searchPlaceholder ?? t('common.search')} style={{ width: 300 }} onSearch={setSearch} />
        {filters}
        <div className="grow" />
        {toolbar}
        <Tooltip title={t('common.refresh')}>
          <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
        </Tooltip>
        <Popover content={columnPicker} title={t('common.columns')} trigger="click" placement="bottomRight">
          <Button icon={<SettingOutlined />} />
        </Popover>
        {exportUrl && can('export.run') && (
          <Dropdown menu={{ items: ['xlsx', 'csv', 'pdf'].map((f) => ({ key: f, label: f.toUpperCase(), onClick: () => doExport(f) })) }}>
            <Button icon={<DownloadOutlined />}>{t('common.export')}</Button>
          </Dropdown>
        )}
      </div>
      <Table<T>
        rowKey="id"
        size={size}
        columns={visibleColumns}
        dataSource={query.data?.items ?? []}
        loading={query.isFetching}
        rowSelection={rowSelection}
        onChange={onChange as never}
        onRow={onRow}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          pageSize,
          total: query.data?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: [10, 25, 50, 100, 200],
          showTotal: (total) => t('common.total', { count: total }),
        }}
      />
    </>
  );
}
