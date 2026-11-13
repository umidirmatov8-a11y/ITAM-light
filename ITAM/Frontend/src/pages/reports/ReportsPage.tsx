import { Badge, Button, Card, Checkbox, Col, DatePicker, Dropdown, Empty, InputNumber, List, Popover, Row, Space, Table, Typography } from 'antd';
import { DownloadOutlined, PlayCircleOutlined, TableOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { download, get } from '@/api/client';
import { useNotify } from '@/api/hooks';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, EnumSelect, LookupSelect } from '@/components/Selects';
import { ASSET_KINDS } from '@/utils/enums';
import { fmtDate, fmtDateTime, toApiDateTime } from '@/utils/format';

interface Def { key: string; title: string; description: string; parameters: string[] }
interface Data { title: string; columns: string[]; rows: unknown[][] }

const fmtCell = (v: unknown) => {
  if (v === null || v === undefined) return '';
  if (typeof v === 'boolean') return v ? '✓' : '';
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v)) return fmtDateTime(v);
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)) return fmtDate(v);
  if (typeof v === 'number') return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(v);
  return String(v);
};

/** Hidden columns per report, remembered in this browser (new columns of a report stay visible). */
const HIDDEN_KEY = 'itam.reports.hiddenColumns';
const loadHidden = (): Record<string, string[]> => {
  try { return JSON.parse(localStorage.getItem(HIDDEN_KEY) ?? '{}') ?? {}; } catch { return {}; }
};
const saveHidden = (v: Record<string, string[]>) => {
  try { localStorage.setItem(HIDDEN_KEY, JSON.stringify(v)); } catch { /* storage unavailable */ }
};

export default function ReportsPage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const defs = useQuery<Def[]>({ queryKey: ['report-defs'], queryFn: () => get('/reports') });
  const [current, setCurrent] = useState<Def>();
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [run, setRun] = useState(0);
  const data = useQuery<Data>({ queryKey: ['report', current?.key, params, run], queryFn: () => get(`/reports/${current!.key}`, params), enabled: !!current && run > 0 });
  const [hiddenAll, setHiddenAll] = useState<Record<string, string[]>>(loadHidden);
  const hidden = (current && hiddenAll[current.key]) || [];
  const setHidden = (cols: string[]) => {
    if (!current) return;
    const next = { ...hiddenAll, [current.key]: cols };
    setHiddenAll(next);
    saveHidden(next);
  };
  const columns = data.data?.columns ?? [];
  const visible = columns.map((c, i) => ({ c, i })).filter((x) => !hidden.includes(x.c));
  const set = (k: string) => (v: unknown) => setParams((p) => ({ ...p, [k]: v }));
  const has = (p: string) => current?.parameters.includes(p);
  return (
    <>
      <PageHeader title={t('menu.reports')} crumbs={[{ title: t('menu.reports') }]} />
      <Row gutter={16}>
        <Col xs={24} lg={7}>
          <Card size="small" title={t('reports.list')}>
            <List size="small" loading={defs.isLoading} dataSource={defs.data} renderItem={(d) => (
              <List.Item onClick={() => { setCurrent(d); setParams({}); setRun(0); }} style={{ cursor: 'pointer', background: current?.key === d.key ? 'rgba(42,120,214,0.12)' : undefined, paddingInline: 8 }}>
                <List.Item.Meta title={d.title} description={d.description} />
              </List.Item>
            )} />
          </Card>
        </Col>
        <Col xs={24} lg={17}>
          {!current ? <Card><Empty description={t('reports.choose')} /></Card> : (
            <Card title={current.title} extra={<Space>
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setRun((r) => r + 1)}>{t('reports.run')}</Button>
              <Popover trigger="click" placement="bottomRight" title={t('reports.columns')} content={columns.length === 0 ? (
                <Typography.Text type="secondary">{t('reports.columnsRunFirst')}</Typography.Text>
              ) : (
                <div style={{ maxWidth: 320 }}>
                  <Space style={{ marginBottom: 8 }}>
                    <Button size="small" onClick={() => setHidden([])}>{t('reports.columnsAll')}</Button>
                  </Space>
                  <Checkbox.Group style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 360, overflowY: 'auto' }}
                    value={columns.filter((c) => !hidden.includes(c))}
                    onChange={(v) => { const shown = v as string[]; if (shown.length) setHidden(columns.filter((c) => !shown.includes(c))); }}
                    options={columns.map((c) => ({ label: c, value: c }))} />
                  <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>{t('reports.columnsHint')}</Typography.Paragraph>
                </div>
              )}>
                <Badge dot={hidden.length > 0}><Button icon={<TableOutlined />}>{t('reports.columns')}</Button></Badge>
              </Popover>
              <Dropdown menu={{ items: ['xlsx', 'pdf', 'csv'].map((f) => ({ key: f, label: f.toUpperCase(), onClick: () => download(`/reports/${current.key}/export`, { ...params, excludeColumns: hidden.length ? hidden : undefined, format: f }).catch(notify.error) })) }}>
                <Button icon={<DownloadOutlined />}>{t('common.export')}</Button>
              </Dropdown>
            </Space>}>
              <Typography.Paragraph type="secondary">{current.description}</Typography.Paragraph>
              <Space wrap style={{ marginBottom: 16 }}>
                {has('asOf') && <DatePicker showTime format="DD.MM.YYYY HH:mm" placeholder={t('reports.asOf')} onChange={(d) => set('asOf')(toApiDateTime(d))} />}
                {has('from') && <DatePicker.RangePicker showTime format="DD.MM.YYYY" onChange={(r) => setParams((p) => ({ ...p, from: toApiDateTime(r?.[0]), to: toApiDateTime(r?.[1]) }))} />}
                {has('regionId') && <LookupSelect lookup="regions" placeholder={t('common.region')} style={{ width: 160 }} onChange={set('regionId')} />}
                {has('departmentId') && <LookupSelect lookup="departments" placeholder={t('common.department')} style={{ width: 200 }} onChange={set('departmentId')} />}
                {has('assetTypeId') && <LookupSelect lookup="asset-types" placeholder={t('assets.type')} style={{ width: 170 }} onChange={set('assetTypeId')} />}
                {has('statusKind') && <EnumSelect group="assetKind" values={ASSET_KINDS} placeholder={t('common.status')} style={{ width: 150 }} onChange={set('statusKind')} />}
                {has('employeeId') && <EmployeeSelect activeOnly={false} style={{ width: 240 }} onChange={set('employeeId')} />}
                {has('days') && <InputNumber min={1} placeholder={t('reports.days')} onChange={set('days')} />}
              </Space>
              {data.data && (
                <>
                  <Typography.Text strong>{data.data.title}</Typography.Text> <span className="itam-muted">({t('common.total', { count: data.data.rows.length })}{data.data.rows.length >= 1000 ? `, ${t('reports.previewLimit')}` : ''})</span>
                  <Table size="small" style={{ marginTop: 8 }} loading={data.isFetching} rowKey={(_, i) => String(i)} scroll={{ x: 'max-content' }} pagination={{ pageSize: 50 }}
                    dataSource={data.data.rows.map((r) => ({ ...r }))}
                    rowClassName={(r: Record<number, unknown>) => (Object.values(r).some((v) => v === 'Итого' || v === 'ИТОГО') ? 'itam-total-row' : '')}
                    columns={visible.map(({ c, i }) => ({ title: c, key: String(i), render: (_: unknown, row: Record<number, unknown>) => fmtCell(row[i]) }))} />
                </>
              )}
            </Card>
          )}
        </Col>
      </Row>
    </>
  );
}
