import { useCallback, useEffect, useState } from "react";

import { Panel } from "../components/ui";
import { get } from "../lib/api";
import { useArc } from "../lib/store";
import type { DiagnosticsReport } from "../lib/types";

const TONE: Record<string, string> = { ok: "ok", warn: "warn", error: "danger", info: "" };

export function Diagnostics() {
  const { backend, notify } = useArc();
  const [report, setReport] = useState<DiagnosticsReport | null>(null);
  const [running, setRunning] = useState(false);
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);

  const run = useCallback(async () => {
    setRunning(true);
    try {
      setReport(await get<DiagnosticsReport>("/api/diagnostics"));
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, [notify]);

  useEffect(() => {
    window.arc?.appInfo().then((i) => setInfo(i as unknown as Record<string, unknown>)).catch(() => undefined);
    if (backend.state === "ready") void run();
  }, [backend.state, run]);

  const text = () =>
    [
      `A.R.C. diagnostics ${new Date().toISOString()}`,
      `Backend: ${backend.state} — ${backend.message} (restarts: ${backend.restarts})`,
      info ? `App: ${JSON.stringify(info)}` : "",
      ...(report?.checks.map((c) => `[${c.state.toUpperCase()}] ${c.name}: ${c.detail}`) ?? []),
      report ? `Data: ${report.data_dir}` : "",
    ]
      .filter(Boolean)
      .join("\n");

  const save = async () => {
    const saved = await window.arc?.saveFile(`arc-diagnostics-${Date.now()}.txt`, text());
    if (saved) notify("ok", `Отчёт сохранён: ${saved}`);
  };

  const restart = async () => {
    await window.arc?.restartBackend();
    notify("info", "Ядро перезапускается");
  };

  return (
    <div className="screen">
      <div className="page-title">
        <h1>Диагностика</h1>
        <span className="dim">Проверка модулей, зависимостей и окружения</span>
      </div>
      <div className="btn-row" style={{ marginBottom: 12 }}>
        <button className="btn btn--solid" onClick={() => void run()} disabled={running || backend.state !== "ready"}>
          {running ? "Проверка…" : "Проверить снова"}
        </button>
        <button className="btn" onClick={() => void save()} disabled={!report}>Сохранить отчёт</button>
        <button className="btn btn--danger" onClick={() => void restart()}>Перезапустить ядро</button>
      </div>
      <Panel title="Ядро" tag={backend.state}>
        <p className={backend.state === "failed" ? "danger-text selectable" : "selectable"}>{backend.message}</p>
        {backend.restarts > 0 && <p className="dim">Автоматических перезапусков: {backend.restarts}</p>}
      </Panel>
      {report && (
        <Panel title="Проверки" tag={new Date(report.ts * 1000).toLocaleTimeString("ru-RU")}>
          <ul className="checks">
            {report.checks.map((c) => (
              <li key={c.name}>
                <span className={`led ${TONE[c.state] ? `led--${TONE[c.state]}` : ""}`} />
                <b>{c.name}</b>
                <span className="selectable dim">{c.detail}</span>
              </li>
            ))}
          </ul>
          <p className="faint selectable">Каталог данных: {report.data_dir}</p>
        </Panel>
      )}
    </div>
  );
}
