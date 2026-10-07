import { Card, Checkbox, Col, Form, Input, Row, Button, Table, Select, Alert } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { get, post } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import type { AssetCondition, AssetListItem, OperationResult } from '@/api/types';
import { DocumentOptions, EffectiveAtField, Half, OperationDone, idsFromQuery } from '@/components/OperationCommon';
import { PageHeader } from '@/components/PageHeader';
import { EmployeeSelect, LookupSelect } from '@/components/Selects';
import { CONDITIONS } from '@/utils/enums';
import { nowInTz, toApiDateTime } from '@/utils/format';

interface Line { assetId: string; selected: boolean; condition: AssetCondition; damage?: string; missingItems?: string; accessories?: string; sendToRepair: boolean; repairProblem?: string }

export default function ReturnPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [form] = Form.useForm();
  const [result, setResult] = useState<OperationResult>();
  const employeeId = Form.useWatch('employeeId', form) ?? params.get('employeeId') ?? undefined;
  const [lines, setLines] = useState<Record<string, Line>>({});
  const preselected = idsFromQuery(params.get('assetIds'));
  const assets = useQuery<AssetListItem[]>({ queryKey: ['employee-assets', employeeId], queryFn: () => get(`/employees/${employeeId}/assets`), enabled: !!employeeId });
  useEffect(() => {
    if (!assets.data) return;
    setLines(Object.fromEntries(assets.data.map((a) => [a.id, { assetId: a.id, selected: preselected.length ? preselected.includes(a.id) : true, condition: 'Good', sendToRepair: false } as Line])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assets.data]);
  const upd = (id: string, patch: Partial<Line>) => setLines((l) => ({ ...l, [id]: { ...l[id], ...patch } }));
  const ret = useApiMutation((v: any) => post<OperationResult>('/operations/return', {
    ...v, effectiveAt: toApiDateTime(v.effectiveAt),
    items: Object.values(lines).filter((l) => l.selected).map(({ selected: _s, ...rest }) => rest),
  }), { invalidate: [['assets'], ['asset'], ['employees'], ['employee-assets'], ['operations']], success: false, onSuccess: setResult });
  const selectedCount = Object.values(lines).filter((l) => l.selected).length;

  return (
    <>
      <PageHeader title={t('operations.returnTitle')} crumbs={[{ title: t('menu.operations'), to: '/operations' }, { title: t('operations.returnTitle') }]} />
      <Card>
        {result ? <OperationDone result={result} onAgain={() => { setResult(undefined); assets.refetch(); }} /> : (
          <Form form={form} layout="vertical" onFinish={(v) => ret.mutate(v)} initialValues={{ employeeId: params.get('employeeId') ?? undefined, effectiveAt: nowInTz(), generateDocument: true }}>
            <Row gutter={16}>
              <Half><Form.Item name="employeeId" label={t('operations.employee')} rules={[{ required: true }]}><EmployeeSelect activeOnly={false} /></Form.Item></Half>
              <Half><EffectiveAtField /></Half>
              <Col span={24}>
                <Form.Item label={t('operations.assetsToReturn')} required>
                  {employeeId && assets.data?.length === 0 && <Alert type="info" message={t('operations.noAssignedAssets')} />}
                  <Table<AssetListItem> rowKey="id" size="small" pagination={false} loading={assets.isLoading} dataSource={assets.data} scroll={{ x: 'max-content' }}
                    columns={[
                      { key: 's', width: 40, render: (_, a) => <Checkbox checked={lines[a.id]?.selected} onChange={(e) => upd(a.id, { selected: e.target.checked })} /> },
                      { title: t('assets.inventoryNumber'), dataIndex: 'inventoryNumber', render: (v) => <span className="itam-mono">{v}</span> },
                      { title: t('assets.name'), dataIndex: 'name' },
                      { title: t('assets.condition'), render: (_, a) => <Select size="small" style={{ width: 160 }} value={lines[a.id]?.condition} onChange={(v) => upd(a.id, { condition: v })} options={CONDITIONS.map((c) => ({ value: c, label: t(`enums.condition.${c}`) }))} /> },
                      { title: t('operations.damage'), render: (_, a) => <Input size="small" value={lines[a.id]?.damage} onChange={(e) => upd(a.id, { damage: e.target.value })} /> },
                      { title: t('operations.missingItems'), render: (_, a) => <Input size="small" value={lines[a.id]?.missingItems} onChange={(e) => upd(a.id, { missingItems: e.target.value })} /> },
                      { title: t('operations.accessories'), render: (_, a) => <Input size="small" value={lines[a.id]?.accessories} onChange={(e) => upd(a.id, { accessories: e.target.value })} /> },
                      { title: t('operations.toRepair'), render: (_, a) => <Checkbox checked={lines[a.id]?.sendToRepair} onChange={(e) => upd(a.id, { sendToRepair: e.target.checked })} /> },
                      { title: t('repairs.problem'), render: (_, a) => lines[a.id]?.sendToRepair && <Input size="small" value={lines[a.id]?.repairProblem} onChange={(e) => upd(a.id, { repairProblem: e.target.value })} /> },
                    ]} />
                </Form.Item>
              </Col>
              <Half><Form.Item name="locationId" label={t('operations.returnLocation')}><LookupSelect lookup="locations" /></Form.Item></Half>
              <Half><Form.Item name="responsibleEmployeeId" label={t('operations.acceptedBy')}><EmployeeSelect /></Form.Item></Half>
              <Col span={24}><Form.Item name="comment" label={t('common.comment')}><Input.TextArea rows={2} /></Form.Item></Col>
              <Col span={24}><DocumentOptions type="EquipmentReturn" /></Col>
            </Row>
            <Button type="primary" htmlType="submit" size="large" disabled={selectedCount === 0} loading={ret.isPending}>{t('operations.returnSubmit', { count: selectedCount })}</Button>
          </Form>
        )}
      </Card>
    </>
  );
}
