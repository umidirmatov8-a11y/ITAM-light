import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import { api } from '../api';
import { DataTable, FormFields } from '../components/crud';
import { Badge, ErrorBox, Loading, Modal, PageHead, useLoad } from '../components/ui';
import { AUDIT_STATUS, fmtDate, fmtDateTime, fmtNum } from '../i18n';

export function AuditsPage() {
  const { can } = useAuth();
  const nav = useNavigate();
  const audits = useLoad<any[]>(() => api.get('/audits'));
  const versions = useLoad<any[]>(() => api.get('/matrix/versions'));
  const [form, setForm] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const open = async () => {
    const date = new Date().toISOString().slice(0, 10);
    const mv = await api.get(`/audits/matrix-for-date?date=${date}`).catch(() => null);
    setError(null);
    setForm({ name: '', as_of_date: date, matrix_version_id: mv?.id ?? '' });
  };
  const setFormWithMatrix = async (f: Record<string, any>) => {
    if (form && f.as_of_date !== form.as_of_date && /^\d{4}-\d{2}-\d{2}$/.test(f.as_of_date)) {
      const mv = await api.get(`/audits/matrix-for-date?date=${f.as_of_date}`).catch(() => null);
      f = { ...f, matrix_version_id: mv?.id ?? '' };
    }
    setForm(f);
  };
  const create = async () => {
    setError(null);
    try {
      const a = await api.post('/audits', form);
      nav(`/audits/${a.id}`);
    } catch (e: any) { setError(e.message); }
  };

  return (
    <div>
      <PageHead title="Аудиты и импорт" sub="Каждый выполненный аудит — неизменяемый снимок: исходные файлы, нормализованные назначения, версия матрицы, версия правил и результаты.">
        {can('audit.create') && <button className="btn primary" onClick={open}>+ Новый аудит</button>}
      </PageHead>
      <ErrorBox error={audits.error} />
      <div className="card flush">
        {audits.loading && !audits.data ? <Loading /> : (
          <DataTable rows={audits.data ?? []} onRowClick={(r) => nav(`/audits/${r.id}`)} empty="Аудитов пока нет"
            columns={[
              { key: 'name', label: 'Аудит', render: (r) => <><b>{r.name}</b>{r.description && <div className="muted small">{r.description}</div>}</> },
              { key: 'as_of_date', label: 'Дата среза', render: (r) => fmtDate(r.as_of_date) },
              { key: 'matrix_version', label: 'Матрица', render: (r) => r.matrix_version ?? <span className="badge HIGH">не выбрана</span> },
              { key: 'status', label: 'Статус', render: (r) => <Badge value={r.status} label={AUDIT_STATUS} /> },
              { key: 'batches_count', label: 'Файлов', className: 'num' },
              { key: 'snapshots_count', label: 'Назначений', className: 'num', render: (r) => fmtNum(r.snapshots_count) },
              { key: 'findings', label: 'Находок', className: 'num', render: (r) => (r.summary ? fmtNum(r.summary.findings) : '—') },
              { key: 'crit', label: 'Крит./выс.', className: 'num', render: (r) => (r.summary ? `${r.summary.bySeverity?.CRITICAL ?? 0} / ${r.summary.bySeverity?.HIGH ?? 0}` : '—') },
              { key: 'completed_at', label: 'Выполнен', render: (r) => (r.completed_at ? `${fmtDateTime(r.completed_at)}` : '—') },
            ]} />
        )}
      </div>
      {form && (
        <Modal title="Новый аудит" onClose={() => setForm(null)} footer={<><button className="btn" onClick={() => setForm(null)}>Отмена</button><button className="btn primary" onClick={create}>Создать и перейти к импорту</button></>}>
          <ErrorBox error={error} />
          <FormFields form={form} setForm={setFormWithMatrix} fields={[
            { name: 'name', label: 'Наименование аудита', required: true, full: true },
            { name: 'as_of_date', label: 'Дата среза (as-of)', type: 'date', required: true, hint: 'Версия матрицы подбирается автоматически по дате' },
            { name: 'matrix_version_id', label: 'Версия матрицы', type: 'select', emptyLabel: '— не выбрана —',
              options: (versions.data ?? []).filter((v) => v.status !== 'DRAFT').map((v) => ({ value: v.id, label: `${v.version} — ${v.name} (${fmtDate(v.valid_from)}–${v.valid_to ? fmtDate(v.valid_to) : '∞'})` })) },
            { name: 'description', label: 'Описание / основание проверки', type: 'textarea' },
          ]} />
        </Modal>
      )}
    </div>
  );
}
