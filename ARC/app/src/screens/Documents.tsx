import { useCallback, useEffect, useState } from "react";

import { IconDoc, IconFolder } from "../components/Icons";
import { Field, Panel, Toggle, formatDateTime } from "../components/ui";
import { get, post } from "../lib/api";
import { useArc } from "../lib/store";
import type { CommandResponse, DocJob, DocKind, DocumentsListing } from "../lib/types";

export const KIND_LABEL: Record<DocKind, string> = {
  pptx: "Презентация (PPTX)",
  docx: "Документ Word (DOCX)",
  xlsx: "Таблица Excel (XLSX)",
  pdf: "PDF",
  txt: "Текст (TXT)",
};

const ACTIVE = new Set(["queued", "research", "writing", "rendering", "verifying"]);

function JobRow({ job, onChange }: { job: DocJob; onChange: () => void }) {
  const { notify } = useArc();
  const active = ACTIVE.has(job.status);
  const tone = job.status === "done" ? "ok" : job.status === "error" ? "danger" : active ? "accent" : "";
  const open = async () => {
    try {
      const r = await post<CommandResponse>(`/api/documents/${job.id}/open`);
      if (r.status !== "done") notify("error", r.message);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };
  const cancel = async () => {
    await post(`/api/documents/${job.id}/cancel`).catch(() => undefined);
    onChange();
  };
  return (
    <li className="doc-job" data-testid={`doc-job-${job.status}`}>
      <div className="doc-job__head">
        <IconDoc size={18} />
        <b className="selectable">{job.title || job.topic}</b>
        <span className="tag">{job.kind.toUpperCase()}</span>
        <span className={`tag ${tone ? `tag--${tone}` : ""}`}>
          {active && <span className="led led--busy" />} {job.stage}
        </span>
        {job.use_web && <span className="tag tag--accent" title="Факты собраны поиском в интернете">ONLINE</span>}
        {job.status === "done" && !job.ai_used && <span className="tag tag--warn">шаблон</span>}
        <span className="dim">{formatDateTime(job.created)}</span>
      </div>
      {job.message && <div className="selectable doc-job__msg">{job.message}</div>}
      {job.warnings.map((w) => <div key={w} className="faint">⚠ {w}</div>)}
      <div className="btn-row">
        {job.status === "done" && (
          <>
            <button className="btn btn--sm" onClick={() => void open()} data-testid="doc-open">Открыть</button>
            <button className="btn btn--sm btn--ghost" onClick={() => window.arc?.showInFolder(job.path)}>
              <IconFolder size={14} /> Показать в папке
            </button>
            {job.sources > 0 && <span className="dim">источников: {job.sources}</span>}
          </>
        )}
        {active && <button className="btn btn--sm btn--ghost" onClick={() => void cancel()}>Отменить</button>}
      </div>
    </li>
  );
}

export function Documents() {
  const { state, settings, updateSettings, notify, sendCommand } = useArc();
  const [listing, setListing] = useState<DocumentsListing | null>(null);
  const [kind, setKind] = useState<DocKind>("pptx");
  const [topic, setTopic] = useState("");
  const [useWeb, setUseWeb] = useState(false);
  const [busy, setBusy] = useState(false);
  const online = state?.mode === "ONLINE";

  const refresh = useCallback(async () => {
    try {
      setListing(await get<DocumentsListing>("/api/documents"));
    } catch {
      /* backend banner covers this */
    }
  }, []);

  const running = Boolean(listing?.jobs.some((j) => ACTIVE.has(j.status)));
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(refresh, running ? 800 : 3000);
    return () => window.clearInterval(timer);
  }, [refresh, running]);

  const create = async () => {
    if (topic.trim().length < 2) return;
    setBusy(true);
    try {
      const r = await post<CommandResponse>("/api/documents", { kind, topic: topic.trim(), use_web: useWeb && online });
      if (r.status === "denied" || r.status === "error") notify("error", r.message);
      // category B: the confirmation dialog opens from the global state
      setTopic("");
      void refresh();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const openRecent = async (path: string) => {
    try {
      const r = await post<CommandResponse>("/api/documents/recent/open", { path });
      if (r.status !== "done") notify("error", r.message);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="screen" data-testid="documents-screen">
      <div className="page-title">
        <h1>Документы</h1>
        <span className="dim">Презентации, документы, таблицы, PDF и текст — создаются на этом компьютере</span>
      </div>
      <div className="grid-2">
        <Panel title="Создать" tag="категория B">
          <div className="form-grid">
            <Field label="Формат">
              <select className="select" value={kind} onChange={(e) => setKind(e.target.value as DocKind)}
                      data-testid="doc-kind">
                {(Object.keys(KIND_LABEL) as DocKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
              </select>
            </Field>
            <Field label="Тема" hint="Например: «Солнечная система для 5 класса»">
              <input className="input" value={topic} maxLength={300} onChange={(e) => setTopic(e.target.value)}
                     onKeyDown={(e) => e.key === "Enter" && void create()} data-testid="doc-topic" />
            </Field>
          </div>
          <Toggle checked={useWeb && online} disabled={!online} onChange={setUseWeb} testId="doc-web"
                  label="Собрать факты в интернете"
                  hint={online ? "Сначала поиск, затем текст по найденным источникам; источники перечисляются в конце"
                    : "Доступно в режиме ONLINE. В режиме LOCAL текст пишется без конкретных цифр и дат"} />
          <div className="btn-row" style={{ marginTop: 10 }}>
            <button className="btn btn--primary" disabled={busy || topic.trim().length < 2} onClick={() => void create()}
                    data-testid="doc-create">Создать</button>
            <button className="btn btn--ghost" disabled={busy || topic.trim().length < 2}
                    onClick={() => void sendCommand(`сделай ${kind === "pptx" ? "презентацию" : kind === "xlsx" ? "таблицу" : kind === "pdf" ? "pdf" : kind === "txt" ? "заметку" : "документ"} про ${topic.trim()}`)}>
              Как команду в терминал
            </button>
          </div>
          <p className="faint">
            Перед созданием файла A.R.C. спросит подтверждение. Готовый файл открывается заново и проверяется
            (слайды, разделы, строки), и только потом сохраняется под своим именем. Существующие файлы не перезаписываются.
          </p>
        </Panel>
        <Panel title="Папка и текст">
          <div className="selectable" data-testid="doc-folder">
            {listing?.folder || <span className="danger-text">{listing?.folder_error || "…"}</span>}
          </div>
          {listing?.folder && (
            <div className="btn-row" style={{ margin: "8px 0" }}>
              <button className="btn btn--sm btn--ghost" onClick={() => window.arc?.showInFolder(listing.folder)}>
                <IconFolder size={14} /> Открыть папку
              </button>
            </div>
          )}
          {settings && (
            <>
              <Toggle checked={settings.documents.use_ai} onChange={(v) => void updateSettings({ documents: { use_ai: v } })}
                      label="Текст пишет локальная модель"
                      hint="Выключено или модель недоступна — создаётся размеченный шаблон для заполнения" />
              <Toggle checked={settings.documents.open_when_ready}
                      onChange={(v) => void updateSettings({ documents: { open_when_ready: v } })}
                      label="Открывать файл, когда он готов" />
              <Field label={`Разделов / слайдов не больше: ${settings.documents.max_sections}`}>
                <input className="input" type="range" min={3} max={12} value={settings.documents.max_sections}
                       onChange={(e) => void updateSettings({ documents: { max_sections: Number(e.target.value) } })} />
              </Field>
              <p className="faint">Папку можно сменить в «Настройки → Документы» (она должна быть среди разрешённых каталогов).</p>
            </>
          )}
        </Panel>
      </div>
      <Panel title="Задания" tag={state?.documents_active ? `в работе: ${state.documents_active}` : undefined}>
        {!listing?.jobs.length ? (
          <div className="empty">Пока ничего не создано. Скажите: «сделай презентацию про солнечную систему».</div>
        ) : (
          <ul className="doc-jobs">{listing.jobs.map((j) => <JobRow key={j.id} job={j} onChange={refresh} />)}</ul>
        )}
      </Panel>
      <Panel title="Файлы в папке">
        {!listing?.recent.length ? (
          <div className="empty">Папка пуста</div>
        ) : (
          <table className="table">
            <tbody>
              {listing.recent.map((f) => (
                <tr key={f.path}>
                  <td className="selectable">{f.name}</td>
                  <td className="dim">{(f.size / 1024).toFixed(0)} КБ</td>
                  <td className="dim">{formatDateTime(f.modified)}</td>
                  <td>
                    <button className="btn btn--sm" onClick={() => void openRecent(f.path)}>Открыть</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
