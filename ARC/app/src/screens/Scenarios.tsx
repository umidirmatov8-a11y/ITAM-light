import { useCallback, useEffect, useState } from "react";

import { IconEdit, IconPlay, IconPlus, IconTrash } from "../components/Icons";
import { Dialog, Field, Panel, Toggle } from "../components/ui";
import { del, get, post, put } from "../lib/api";
import { useArc } from "../lib/store";
import type { CommandResponse, Scenario, ScenarioStep } from "../lib/types";

export const STEP_LABEL: Record<string, string> = {
  "app.launch": "Запустить приложение",
  "volume.set": "Установить громкость",
  "volume.change": "Изменить громкость",
  "volume.mute": "Звук вкл/выкл",
  "window.minimize_all": "Свернуть все окна",
  "window.restore_all": "Вернуть окна",
  "browser.open_url": "Открыть сайт",
  "explorer.open": "Открыть папку",
  "profile.silent": "Режим тишины",
  "mode.set": "Режим LOCAL/ONLINE",
};

const FOLDERS: Record<string, string> = {
  desktop: "Рабочий стол",
  documents: "Документы",
  downloads: "Загрузки",
  pictures: "Изображения",
  music: "Музыка",
  videos: "Видео",
};

export function defaultParams(action: string): Record<string, any> {
  switch (action) {
    case "volume.set":
      return { level: 50 };
    case "volume.change":
      return { delta: 10 };
    case "volume.mute":
      return { muted: true };
    case "browser.open_url":
      return { url: "https://" };
    case "explorer.open":
      return { folder: "documents" };
    case "profile.silent":
      return { enabled: true };
    case "mode.set":
      return { mode: "LOCAL" };
    default:
      return {};
  }
}

export function describeStep(step: ScenarioStep, appName: (id: string) => string): string {
  const p = step.params;
  switch (step.action) {
    case "app.launch":
      return `${STEP_LABEL[step.action]}: ${appName(p.app_id)}`;
    case "volume.set":
      return `Громкость ${p.level}%`;
    case "volume.change":
      return `Громкость ${p.delta > 0 ? "+" : ""}${p.delta}%`;
    case "volume.mute":
      return p.muted ? "Выключить звук" : "Включить звук";
    case "browser.open_url":
      return `Открыть ${p.url}`;
    case "explorer.open":
      return `Открыть папку «${FOLDERS[p.folder] ?? p.folder ?? "Проводник"}»`;
    case "profile.silent":
      return p.enabled ? "Включить режим тишины" : "Выключить режим тишины";
    case "mode.set":
      return `Режим ${p.mode}`;
    default:
      return STEP_LABEL[step.action] ?? step.action;
  }
}

function StepEditor({ step, onChange, onRemove }: {
  step: ScenarioStep;
  onChange: (s: ScenarioStep) => void;
  onRemove: () => void;
}) {
  const { apps } = useArc();
  const p = step.params;
  const setParam = (key: string, value: unknown) => onChange({ ...step, params: { ...p, [key]: value } });
  return (
    <div className="step">
      <select className="select" value={step.action}
              onChange={(e) => {
                const action = e.target.value;
                const params = action === "app.launch" ? { app_id: apps[0]?.id ?? "" } : defaultParams(action);
                onChange({ action, params });
              }}>
        {Object.entries(STEP_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <div className="step__params">
        {step.action === "app.launch" && (
          <select className="select" value={p.app_id ?? ""} onChange={(e) => setParam("app_id", e.target.value)}>
            {apps.filter((a) => !a.run_as_admin).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        )}
        {step.action === "volume.set" && (
          <input className="input" type="number" min={0} max={100} value={p.level}
                 onChange={(e) => setParam("level", Number(e.target.value))} />
        )}
        {step.action === "volume.change" && (
          <input className="input" type="number" min={-100} max={100} value={p.delta}
                 onChange={(e) => setParam("delta", Number(e.target.value))} />
        )}
        {step.action === "volume.mute" && (
          <Toggle checked={Boolean(p.muted)} onChange={(v) => setParam("muted", v)} label="Выключить звук" />
        )}
        {step.action === "profile.silent" && (
          <Toggle checked={Boolean(p.enabled)} onChange={(v) => setParam("enabled", v)} label="Включить режим тишины" />
        )}
        {step.action === "browser.open_url" && (
          <input className="input" value={p.url} onChange={(e) => setParam("url", e.target.value)} />
        )}
        {step.action === "explorer.open" && (
          <select className="select" value={p.folder ?? ""} onChange={(e) => setParam("folder", e.target.value)}>
            {Object.entries(FOLDERS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        )}
        {step.action === "mode.set" && (
          <select className="select" value={p.mode} onChange={(e) => setParam("mode", e.target.value)}>
            <option value="LOCAL">LOCAL</option>
            <option value="ONLINE">ONLINE</option>
          </select>
        )}
      </div>
      <button className="btn btn--sm btn--danger" onClick={onRemove} title="Удалить шаг"><IconTrash size={14} /></button>
    </div>
  );
}

function ScenarioEditor({ scenario, onClose, onSaved }: {
  scenario: Scenario | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { notify } = useArc();
  const [name, setName] = useState(scenario?.name ?? "");
  const [aliases, setAliases] = useState(scenario?.aliases.join(", ") ?? "");
  const [enabled, setEnabled] = useState(scenario?.enabled ?? true);
  const [steps, setSteps] = useState<ScenarioStep[]>(scenario?.steps ?? [{ action: "volume.set", params: { level: 50 } }]);
  const [error, setError] = useState("");

  const save = async () => {
    const body = { name: name.trim(), aliases: aliases.split(",").map((a) => a.trim()).filter(Boolean), steps, enabled };
    try {
      if (scenario) await put(`/api/scenarios/${scenario.id}`, body);
      else await post("/api/scenarios", body);
      notify("ok", `Сценарий «${body.name}» сохранён`);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Dialog title={scenario ? `Сценарий: ${scenario.name}` : "Новый сценарий"} onClose={onClose} wide
            footer={
              <>
                <button className="btn btn--ghost" onClick={onClose}>Отмена</button>
                <button className="btn btn--solid" onClick={() => void save()} disabled={!name.trim() || !steps.length}>
                  Сохранить
                </button>
              </>
            }>
      {error && <div className="banner banner--danger">{error}</div>}
      <div className="form-grid">
        <Field label="Название">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
        </Field>
        <Field label="Фразы для запуска" hint="Через запятую: игровой режим, поиграем">
          <input className="input" value={aliases} onChange={(e) => setAliases(e.target.value)} />
        </Field>
      </div>
      <Toggle checked={enabled} onChange={setEnabled} label="Сценарий включён" />
      <div className="mono-label" style={{ margin: "12px 0 6px" }}>Шаги (только безопасные действия категории A)</div>
      <div className="steps">
        {steps.map((step, i) => (
          <StepEditor key={i} step={step}
                      onChange={(s) => setSteps((all) => all.map((x, j) => (j === i ? s : x)))}
                      onRemove={() => setSteps((all) => all.filter((_, j) => j !== i))} />
        ))}
      </div>
      <button className="btn btn--sm" onClick={() => setSteps((all) => [...all, { action: "window.minimize_all", params: {} }])}
              disabled={steps.length >= 20}>
        <IconPlus size={14} /> Добавить шаг
      </button>
    </Dialog>
  );
}

export function Scenarios() {
  const { apps, notify } = useArc();
  const [items, setItems] = useState<Scenario[]>([]);
  const [editing, setEditing] = useState<Scenario | null | "new">(null);
  const load = useCallback(async () => {
    try {
      setItems((await get<{ scenarios: Scenario[] }>("/api/scenarios")).scenarios);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  }, [notify]);
  useEffect(() => {
    void load();
  }, [load]);
  const appName = (id: string) => apps.find((a) => a.id === id)?.name ?? "удалённое приложение";

  const run = async (s: Scenario) => {
    try {
      const r = await post<CommandResponse>(`/api/scenarios/${s.id}/run`);
      notify(r.status === "done" ? "ok" : "error", r.message);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };
  const remove = async (s: Scenario) => {
    try {
      await del(`/api/scenarios/${s.id}`);
      await load();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="screen">
      <div className="page-title">
        <h1>Сценарии</h1>
        <span className="dim">Режимы из нескольких действий: «рабочий режим», «игровой режим», «режим концентрации»</span>
      </div>
      <div className="btn-row" style={{ marginBottom: 12 }}>
        <button className="btn btn--solid" onClick={() => setEditing("new")}><IconPlus size={16} /> Новый сценарий</button>
      </div>
      <div className="cards">
        {items.length === 0 && <div className="empty">Сценариев пока нет</div>}
        {items.map((s) => (
          <Panel key={s.id} title={s.name} tag={s.enabled ? "включён" : "выключен"}>
            <div className="dim">Фразы: {s.aliases.length ? s.aliases.map((a) => `«${a}»`).join(", ") : "—"}</div>
            <ol className="scenario-steps">
              {s.steps.map((step, i) => <li key={i}>{describeStep(step, appName)}</li>)}
            </ol>
            <div className="btn-row">
              <button className="btn btn--sm" onClick={() => void run(s)} disabled={!s.enabled}><IconPlay size={14} /> Запустить</button>
              <button className="btn btn--sm" onClick={() => setEditing(s)}><IconEdit size={14} /> Изменить</button>
              <button className="btn btn--sm btn--danger" onClick={() => void remove(s)}><IconTrash size={14} /> Удалить</button>
            </div>
          </Panel>
        ))}
      </div>
      {editing && <ScenarioEditor scenario={editing === "new" ? null : editing} onClose={() => setEditing(null)}
                                  onSaved={() => void load()} />}
    </div>
  );
}
