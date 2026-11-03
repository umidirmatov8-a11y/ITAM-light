import { Link } from 'react-router-dom';
import { api } from '../api';
import { ErrorBox, Loading, PageHead, useLoad } from '../components/ui';
import { fmtDate, fmtDateTime, fmtNum, FINDING_TYPE } from '../i18n';

export function DashboardPage() {
  const { data, error, loading } = useLoad<any>(() => api.get('/dashboard'));
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const { last, lastScoped, trend, exceptions, counts, scoped } = data;
  const s = last?.summary ?? {};
  const max = Math.max(1, ...trend.map((t: any) => t.critical + t.high + t.medium + t.review));
  const total = s.totalAccesses || 1;
  const pct = (n: number) => `${((n ?? 0) / total) * 100}%`;

  return (
    <div>
      <PageHead title="Главная" sub={scoped ? 'Показаны данные только по системам, владельцем которых вы являетесь' : 'Сводка по последнему аудиту и динамика находок'} />
      {!last ? (
        <div className="card">
          <h2>Аудиты ещё не выполнялись</h2>
          <p className="muted">Заполните справочники и матрицу полномочий, затем создайте аудит и загрузите выгрузки фактических доступов.</p>
          <Link className="btn primary" to="/audits">Перейти к аудитам</Link>
        </div>
      ) : (
        <>
          <div className="card">
            <div className="row">
              <div>
                <div className="muted small">Последний аудит</div>
                <h2 style={{ margin: '2px 0' }}><Link to={`/audits/${last.id}`}>{last.name}</Link></h2>
                <div className="muted small">Дата среза {fmtDate(last.as_of_date)} · матрица {last.matrix_version} · выполнен {fmtDateTime(last.completed_at)}</div>
              </div>
              <div className="spacer" />
              <Link className="btn" to={`/audits/${last.id}?tab=findings`}>Открыть находки</Link>
            </div>
            {!scoped && (
              <div style={{ marginTop: 14 }}>
                <div className="bar" title="Распределение назначений по результату">
                  <span className="c-ok" style={{ width: pct(s.byResult?.COMPLIANT) }} />
                  <span className="c-cov" style={{ width: pct(s.byResult?.COVERED_BY_EXCEPTION) }} />
                  <span className="c-high" style={{ width: pct(s.byResult?.VIOLATION) }} />
                  <span className="c-rev" style={{ width: pct(s.byResult?.NEEDS_REVIEW) }} />
                </div>
                <div className="legend">
                  <span><i className="c-ok" />Соответствует: {fmtNum(s.byResult?.COMPLIANT)}</span>
                  <span><i className="c-cov" />Покрыто исключением: {fmtNum(s.byResult?.COVERED_BY_EXCEPTION)}</span>
                  <span><i className="c-high" />Нарушение: {fmtNum(s.byResult?.VIOLATION)}</span>
                  <span><i className="c-rev" />Требует проверки: {fmtNum(s.byResult?.NEEDS_REVIEW)}</span>
                </div>
              </div>
            )}
          </div>
          <div className="kpis">
            {!scoped && <div className="kpi"><div className="label">Атомарных назначений</div><div className="value">{fmtNum(s.totalAccesses)}</div></div>}
            <div className="kpi crit"><div className="label">Критические находки</div><div className="value">{fmtNum(lastScoped?.critical)}</div></div>
            <div className="kpi high"><div className="label">Высокие находки</div><div className="value">{fmtNum(lastScoped?.high)}</div></div>
            <div className="kpi"><div className="label">Требуют проверки</div><div className="value">{fmtNum(lastScoped?.review)}</div></div>
            <div className="kpi high"><div className="label">{FINDING_TYPE.TERMINATED_USER_ACCESS}</div><div className="value">{fmtNum(lastScoped?.terminated)}</div></div>
            <div className="kpi warn"><div className="label">Конфликты SoD</div><div className="value">{fmtNum(lastScoped?.sod)}</div></div>
            <div className="kpi"><div className="label">Необработанные находки</div><div className="value">{fmtNum(lastScoped?.open)}</div></div>
          </div>
        </>
      )}
      <div className="grid cols-2">
        <div className="card">
          <h2>Динамика нарушений по аудитам</h2>
          {trend.length === 0 ? <div className="empty">Нет выполненных аудитов</div> : (
            <>
              <div className="chart">
                {trend.map((t: any) => {
                  const h = (n: number) => `${(n / max) * 150}px`;
                  return (
                    <div className="col" key={t.id} title={`${t.name}: критич. ${t.critical}, выс. ${t.high}, сред. ${t.medium}, проверка ${t.review}`}>
                      <div className="small">{t.critical + t.high + t.medium + t.review}</div>
                      <div className="stack">
                        <span className="c-crit" style={{ height: h(t.critical) }} />
                        <span className="c-high" style={{ height: h(t.high) }} />
                        <span className="c-med" style={{ height: h(t.medium) }} />
                        <span className="c-rev" style={{ height: h(t.review) }} />
                      </div>
                      <div className="lbl">{fmtDate(t.as_of_date)}</div>
                    </div>
                  );
                })}
              </div>
              <div className="legend"><span><i className="c-crit" />Критические</span><span><i className="c-high" />Высокие</span><span><i className="c-med" />Средние</span><span><i className="c-rev" />Требуют проверки</span></div>
            </>
          )}
        </div>
        <div className="card">
          <h2>Исключения</h2>
          <div className="kpis" style={{ marginBottom: 8 }}>
            <div className="kpi ok"><div className="label">Действуют</div><div className="value">{exceptions.active}</div></div>
            <div className="kpi warn"><div className="label">Истекают в 30 дней</div><div className="value">{exceptions.expiring}</div></div>
            <div className="kpi high"><div className="label">Истекли</div><div className="value">{exceptions.expired}</div></div>
          </div>
          <Link to="/exceptions">Журнал исключений →</Link>
          <h2 style={{ marginTop: 18 }}>Нормативные данные</h2>
          <dl className="kv">
            <dt>Действующая матрица</dt><dd>{counts.current_matrix ?? <span className="badge HIGH">нет утверждённой версии</span>}</dd>
            <dt>Активных систем</dt><dd>{counts.systems}</dd>
            <dt>Сотрудников в справочнике</dt><dd>{fmtNum(counts.employees)}</dd>
            <dt>Активных SoD-правил</dt><dd>{counts.sod_rules}</dd>
            <dt>Аудитов всего</dt><dd>{counts.audits}</dd>
          </dl>
        </div>
      </div>
    </div>
  );
}
