import { Button, Checkbox, Input, List, Modal, Progress, Space, Tag, Typography } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { post, put } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/app/auth';
import type { Checklist } from '@/api/types';
import { EnumTag } from '@/components/Tags';
import { GenerateDocumentButton } from '@/components/Documents';
import { fmtDate, fmtDateTime } from '@/utils/format';

/** Onboarding / offboarding checklist with manual and smart (auto-evaluated) items. */
export function ChecklistView({ checklist, invalidate }: { checklist: Checklist; invalidate: unknown[][] }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [comment, setComment] = useState<Record<string, string>>({});
  const editable = checklist.status === 'InProgress' && can('checklists.manage');
  const update = useApiMutation((v: { itemId: string; isDone: boolean }) => put(`/checklists/${checklist.id}/items/${v.itemId}`, { isDone: v.isDone, comment: comment[v.itemId] }), {
    invalidate: invalidate as never, success: false,
  });
  const complete = useApiMutation((force: boolean) => post(`/checklists/${checklist.id}/complete?force=${force}`), { invalidate: invalidate as never });
  const cancel = useApiMutation(() => post(`/checklists/${checklist.id}/cancel`, { reason: null }), { invalidate: invalidate as never });
  const percent = checklist.total ? Math.round((checklist.done / checklist.total) * 100) : 0;
  return (
    <div>
      <Space wrap style={{ marginBottom: 12 }}>
        <Typography.Text strong>{checklist.title}</Typography.Text>
        <EnumTag group="checklistKind" value={checklist.kind} />
        <EnumTag group="checklistStatus" value={checklist.status} />
        <span className="itam-muted">{t('checklists.started', { date: fmtDateTime(checklist.startedAt) })}{checklist.dueDate && ` · ${t('checklists.due', { date: fmtDate(checklist.dueDate) })}`}</span>
      </Space>
      <Progress percent={percent} size="small" />
      <List size="small" dataSource={checklist.items} renderItem={(i) => (
        <List.Item actions={i.isAuto ? [<Tag key="a" icon={<ThunderboltOutlined />} color="blue">{t('checklists.auto')}</Tag>] : []}>
          <Space direction="vertical" size={2} style={{ width: '100%' }}>
            <Checkbox checked={i.isDone} disabled={!editable || (i.isAuto && i.isDone)} onChange={(e) => update.mutate({ itemId: i.id, isDone: e.target.checked })}>
              <span style={{ textDecoration: i.isDone ? 'line-through' : undefined }}>{i.title}</span>
              {i.isRequired && <Typography.Text type="danger"> *</Typography.Text>}
              {i.targetName && <Tag style={{ marginLeft: 8 }}>{i.targetName}</Tag>}
            </Checkbox>
            {(i.doneByName || i.comment) && <span className="itam-muted" style={{ fontSize: 12, marginLeft: 24 }}>{i.doneByName} {fmtDateTime(i.doneAt)} {i.comment}</span>}
            {editable && !i.isAuto && !i.isDone && (
              <Input size="small" style={{ marginLeft: 24, maxWidth: 380 }} placeholder={t('common.comment')} value={comment[i.id]} onChange={(e) => setComment((c) => ({ ...c, [i.id]: e.target.value }))} />
            )}
          </Space>
        </List.Item>
      )} />
      {checklist.status === 'InProgress' && (
        <Space style={{ marginTop: 12 }} wrap>
          {can('checklists.manage') && <Button type="primary" onClick={() => complete.mutate(false)} loading={complete.isPending}>{t('checklists.complete')}</Button>}
          {can('checklists.manage') && <Button onClick={() => Modal.confirm({ title: t('checklists.forceConfirm'), onOk: () => complete.mutateAsync(true) })}>{t('checklists.completeForce')}</Button>}
          <GenerateDocumentButton sourceType="EmployeeChecklist" sourceId={checklist.id} documentType={checklist.kind === 'Onboarding' ? 'EmployeeOnboarding' : 'EmployeeOffboarding'} />
          {can('checklists.manage') && <Button danger onClick={() => cancel.mutate(undefined)}>{t('checklists.cancel')}</Button>}
        </Space>
      )}
    </div>
  );
}
