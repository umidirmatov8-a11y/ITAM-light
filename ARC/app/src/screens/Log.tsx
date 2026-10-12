import { useCallback, useEffect, useState } from "react";

import { Dialog, formatDateTime, Panel, RiskBadge, STATUS_LABEL, statusTone } from "../components/ui";
import { del, get } from "../lib/api";
import { useArc } from "../lib/store";
import type { AuditItem, HistoryItem } from "../lib/types";

const SOURCE_LABEL: Record<string, string> = {
  ui: "интерфейс",
  text: "текст",
  voice: "голос",
  gesture: "жест",
  scenario: "сценарий",
  ai: "ИИ",
};

export function Log() {
  const { notify, refreshHistory } = useArc();
  const [tab, setTab] = useState<"audit" | "history">("audit");
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [clearing, setClearing] = useState<"history" | "audit" | null>(null);

  const load = useCallback(async () => {
    try {
      const [a, h] = await Promise.all([get<AuditItem[]>("/api/audit?limit=500"), get<HistoryItem[]>("/api/history?limit=500")]);
      setAudit(a);
      setHistory(h);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const exportLog = async (format: "json" | "csv") => {
    try {
      const data = await get<{ filename: string; content: string }>(`/api/audit/export?format=${format}`);
      const saved = await window.arc?.saveFile(data.filename, data.content);
      if (saved) notify("ok", `Журнал сохранён: ${saved}`);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };

  const clear = async () => {
    if (!clearing) return;
    try {
      await del(clearing === "history" ? "/api/history" : "/api/audit");
      notify("ok", clearing === "history" ? "История команд очищена" : "Журнал операций очищен");
      await load();
      await refreshHistory();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
    setClearing(null);
  };

  return (
    <div className="screen">
      <div className="page-title">
        <h1>Журнал</h1>
        <span className="dim">Все выполненные, отклонённые и имитированные операции</span>
      </div>
      <Panel>
        <div className="toolbar">
          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === "audit"} onClick={() => setTab("audit")}>Операции ({audit.length})</button>
            <button role="tab" aria-selected={tab === "history"} onClick={() => setTab("history")}>Команды ({history.length})</button>
          </div>
          <span className="toolbar__spacer" />
          <button className="btn btn--sm" onClick={() => void load()}>Обновить</button>
          <button className="btn btn--sm" onClick={() => void exportLog("json")}>Экспорт JSON</button>
          <button className="btn btn--sm" onClick={() => void exportLog("csv")}>Экспорт CSV</button>
          <button className="btn btn--sm btn--danger" onClick={() => setClearing(tab)}>Очистить</button>
        </div>
        <div className="table-wrap">
          {tab === "audit" ? (
            <table className="table">
              <thead>
                <tr><th>Время</th><th>Риск</th><th>Действие</th><th>Источник</th><th>Решение</th><th>Итог</th><th>Сообщение</th></tr>
              </thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.id}>
                    <td className="faint">{formatDateTime(a.ts)}</td>
                    <td><RiskBadge risk={a.risk} /></td>
                    <td>
                      <code>{a.action}</code>
                      <div className="cell-path" title={JSON.stringify(a.params)}>{JSON.stringify(a.params)}</div>
                    </td>
                    <td className="dim">{SOURCE_LABEL[a.source] ?? a.source}</td>
                    <td className="dim">{a.decision}</td>
                    <td><span className={`tag tag--${statusTone(a.status) || "accent"}`}>{STATUS_LABEL[a.status] ?? a.status}</span></td>
                    <td className="selectable">{a.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="table">
              <thead><tr><th>Время</th><th>Источник</th><th>Команда</th><th>Итог</th><th>Ответ</th></tr></thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td className="faint">{formatDateTime(h.ts)}</td>
                    <td className="dim">{SOURCE_LABEL[h.source] ?? h.source}</td>
                    <td className="selectable">{h.input || <span className="faint">{h.action}</span>}</td>
                    <td><span className={`tag tag--${statusTone(h.status) || "accent"}`}>{STATUS_LABEL[h.status] ?? h.status}</span></td>
                    <td className="selectable">{h.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {(tab === "audit" ? audit : history).length === 0 && <div className="empty">Записей нет</div>}
        </div>
      </Panel>
      {clearing && (
        <Dialog title="Очистка" onClose={() => setClearing(null)}
                footer={
                  <>
                    <button className="btn btn--ghost" onClick={() => setClearing(null)}>Отмена</button>
                    <button className="btn btn--danger btn--solid" onClick={() => void clear()}>Очистить</button>
                  </>
                }>
          <p>{clearing === "history" ? "Удалить историю команд?" : "Удалить журнал операций? Факт очистки будет записан."}</p>
        </Dialog>
      )}
    </div>
  );
}
