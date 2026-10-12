import { useCallback, useEffect, useState } from "react";

import { HandView } from "../components/HandView";
import { Field, Panel, Toggle } from "../components/ui";
import { get, post } from "../lib/api";
import { useArc } from "../lib/store";
import type { GestureBinding, VisionSettings } from "../lib/types";
import { VISION_LABEL } from "./Home";

interface ActionsInfo {
  actions: Record<string, string>;
  gestures: Record<string, string>;
}

const FOLDERS: Record<string, string> = { desktop: "Рабочий стол", documents: "Документы", downloads: "Загрузки" };

/** Default parameters when an action with parameters is chosen for a gesture. */
export function defaultGestureParams(action: string, firstAppId?: string, firstScenarioId?: string): Record<string, any> {
  switch (action) {
    case "volume.mute":
      return { muted: true };
    case "volume.set":
      return { level: 50 };
    case "volume.change":
      return { delta: 10 };
    case "profile.silent":
      return { enabled: true };
    case "system.info":
      return { topic: "time" };
    case "explorer.open":
      return { folder: "documents" };
    case "app.launch":
      return firstAppId ? { app_id: firstAppId } : {};
    case "scenario.run":
      return firstScenarioId ? { scenario_id: firstScenarioId } : {};
    default:
      return {};
  }
}

function BindingParams({ binding, onChange, scenarios }: {
  binding: GestureBinding;
  onChange: (params: Record<string, any>) => void;
  scenarios: { id: string; name: string }[];
}) {
  const { apps } = useArc();
  const p = binding.params;
  switch (binding.action) {
    case "volume.mute":
      return <Toggle checked={Boolean(p.muted)} onChange={(v) => onChange({ muted: v })} label="выключить" />;
    case "volume.set":
      return <input className="input" type="number" min={0} max={100} value={p.level ?? 50}
                    onChange={(e) => onChange({ level: Number(e.target.value) })} />;
    case "volume.change":
      return <input className="input" type="number" min={-100} max={100} value={p.delta ?? 10}
                    onChange={(e) => onChange({ delta: Number(e.target.value) })} />;
    case "profile.silent":
      return <Toggle checked={Boolean(p.enabled)} onChange={(v) => onChange({ enabled: v })} label="включить" />;
    case "system.info":
      return (
        <select className="select" value={p.topic} onChange={(e) => onChange({ topic: e.target.value })}>
          {["time", "date", "disk", "memory", "cpu", "processes", "stats"].map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      );
    case "explorer.open":
      return (
        <select className="select" value={p.folder ?? ""} onChange={(e) => onChange(e.target.value ? { folder: e.target.value } : {})}>
          <option value="">Проводник</option>
          {Object.entries(FOLDERS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      );
    case "app.launch":
      return (
        <select className="select" value={p.app_id ?? ""} onChange={(e) => onChange({ app_id: e.target.value })}>
          {apps.filter((a) => !a.run_as_admin && a.enabled).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      );
    case "scenario.run":
      return (
        <select className="select" value={p.scenario_id ?? ""} onChange={(e) => onChange({ scenario_id: e.target.value })}>
          {scenarios.map((sc) => <option key={sc.id} value={sc.id}>{sc.name}</option>)}
        </select>
      );
    default:
      return <span className="faint">—</span>;
  }
}

export function GestureSettingsPanel() {
  const { settings, updateSettings, vision, visionCall, notify, apps } = useArc();
  const [info, setInfo] = useState<ActionsInfo | null>(null);
  const [cameras, setCameras] = useState<{ index: number; name: string; resolution: string }[] | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    get<ActionsInfo>("/api/vision/actions").then(setInfo).catch(() => undefined);
    get<{ scenarios: { id: string; name: string }[] }>("/api/scenarios").then((r) => setScenarios(r.scenarios)).catch(() => undefined);
  }, []);

  const previewOn = Boolean(vision?.preview && vision.running);
  useEffect(() => {
    if (!previewOn) {
      setPreview(null);
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const r = await get<{ image: string | null }>("/api/vision/preview");
        setPreview(r.image);
      } catch {
        /* ignore */
      }
    }, 300);
    return () => window.clearInterval(timer);
  }, [previewOn]);

  const probe = useCallback(async () => {
    try {
      setCameras((await get<{ cameras: { index: number; name: string; resolution: string }[] }>("/api/vision/cameras")).cameras);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  }, [notify]);

  if (!settings) return null;
  const v = settings.vision;
  const save = (patch: Partial<VisionSettings>) => void updateSettings({ vision: patch as Record<string, unknown> });
  const setBinding = (gesture: string, binding: GestureBinding) => save({ bindings: { ...v.bindings, [gesture]: binding } });
  const setup = async (enabled: boolean) => {
    try {
      if (enabled && !vision?.running) await visionCall("start");
      await post("/api/vision/setup", { enabled });
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <>
      <Panel title="Жесты: камера" tag={vision ? VISION_LABEL[vision.state] : "—"} testId="gesture-settings">
        <div className="btn-row">
          <Toggle checked={settings.devices.camera_enabled} label="Камера разрешена"
                  hint="Выключено — A.R.C. не открывает камеру ни при каких условиях"
                  onChange={(on) => void updateSettings({ devices: { camera_enabled: on } })} />
        </div>
        <div className="form-grid">
          <Field label="Камера">
            <div className="input-with-btn">
              <select className="select" value={v.camera_index} onChange={(e) => save({ camera_index: Number(e.target.value) })}>
                {(cameras ?? [{ index: v.camera_index, name: `Камера ${v.camera_index}`, resolution: "" }]).map((c) => (
                  <option key={c.index} value={c.index}>{c.name} {c.resolution}</option>
                ))}
              </select>
              <button className="btn btn--sm" onClick={() => void probe()} disabled={!settings.devices.camera_enabled}>
                Найти камеры
              </button>
            </div>
          </Field>
          <Field label={`Порог уверенности: ${Math.round(v.confidence * 100)}%`}>
            <input className="input" type="range" min={0.5} max={0.95} step={0.05} value={v.confidence}
                   onChange={(e) => save({ confidence: Number(e.target.value) })} />
          </Field>
          <Field label={`Удержание жеста: ${(v.hold_ms / 1000).toFixed(2)} с`}>
            <input className="input" type="range" min={200} max={2000} step={50} value={v.hold_ms}
                   onChange={(e) => save({ hold_ms: Number(e.target.value) })} />
          </Field>
          <Field label={`Повтор того же жеста не раньше: ${(v.cooldown_ms / 1000).toFixed(1)} с`}>
            <input className="input" type="range" min={500} max={6000} step={100} value={v.cooldown_ms}
                   onChange={(e) => save({ cooldown_ms: Number(e.target.value) })} />
          </Field>
          <Field label={`Пауза между командами: ${(v.min_interval_ms / 1000).toFixed(1)} с`}>
            <input className="input" type="range" min={200} max={5000} step={100} value={v.min_interval_ms}
                   onChange={(e) => save({ min_interval_ms: Number(e.target.value) })} />
          </Field>
          <Field label={`Удержание ладони в зоне: ${(v.zone_hold_ms / 1000).toFixed(1)} с`}>
            <input className="input" type="range" min={500} max={5000} step={100} value={v.zone_hold_ms}
                   onChange={(e) => save({ zone_hold_ms: Number(e.target.value) })} />
          </Field>
        </div>
        <Toggle checked={v.mirror} onChange={(m) => save({ mirror: m })} label="Зеркальное изображение"
                hint="Движение руки вправо видно справа, как в зеркале" />
        <div className="btn-row" style={{ marginTop: 10 }}>
          {vision?.running ? (
            <button className="btn btn--danger" onClick={() => void visionCall("stop")}>Выключить камеру</button>
          ) : (
            <button className="btn btn--solid" onClick={() => void visionCall("start")}
                    disabled={!vision || vision.state === "disabled" || vision.state === "not_installed"}>Включить жесты</button>
          )}
          <button className={`btn ${previewOn ? "btn--solid" : ""}`} onClick={() => void setup(!previewOn)}
                  disabled={!settings.devices.camera_enabled || vision?.state === "not_installed"} data-testid="camera-check">
            {previewOn ? "Закрыть проверку камеры" : "Проверка камеры"}
          </button>
          <button className="btn" onClick={() => void visionCall("calibrate")} disabled={!vision?.running}>Калибровка</button>
        </div>
        {vision?.message && <p className={vision.state === "error" ? "danger-text" : "dim"}>{vision.message}</p>}
        {vision?.calibrating && (
          <div className="banner">Калибровка {Math.round(vision.calibrating.progress * 100)}%: {vision.calibrating.message}</div>
        )}
        {v.calibration && (
          <p className="faint">
            Калибровка от {new Date(v.calibration.ts * 1000).toLocaleString("ru-RU")}: руки заметно дальше этого расстояния
            игнорируются; освещённость {Math.round(v.calibration.brightness)}/255.
          </p>
        )}
        {previewOn && (
          <div className="camera-check">
            {preview ? <img src={`data:image/jpeg;base64,${preview}`} alt="Изображение с камеры" /> : <div className="empty">Ожидание кадра…</div>}
            <div>
              <HandView landmarks={vision?.landmarks ?? null} zone={v.zone} size={200} />
              <div className="mono-label" style={{ marginTop: 6 }}>Распознано: {vision?.gesture_title}</div>
              <div className="faint">Сырой жест: {vision?.raw_gesture} · {Math.round((vision?.confidence ?? 0) * 100)}% · {vision?.fps} кадр/с</div>
              <div className="faint">{Object.entries(vision?.fingers ?? {}).map(([f, st]) => `${f}: ${st}`).join(" · ")}</div>
              <p className="faint">Изображение показывается только здесь, не сохраняется и автоматически закрывается через 2 минуты.</p>
            </div>
          </div>
        )}
      </Panel>

      <Panel title="Жесты: действия">
        <p className="dim">
          Жестам доступны только безопасные действия (категория A). Удаление, выключение, запуск от администратора и
          подтверждение опасных операций жестами невозможны.
        </p>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Жест</th><th>Вкл.</th><th>Действие</th><th>Параметры</th></tr></thead>
            <tbody>
              {info && Object.entries(info.gestures).map(([gesture, title]) => {
                const binding = v.bindings[gesture];
                if (!binding) return null;
                return (
                  <tr key={gesture}>
                    <td>{title}</td>
                    <td>
                      <Toggle checked={binding.enabled} label={<span className="sr-only">Включено</span>}
                              onChange={(enabled) => setBinding(gesture, { ...binding, enabled })} />
                    </td>
                    <td>
                      <select className="select" value={binding.action} data-testid={`binding-${gesture}`}
                              onChange={(e) => setBinding(gesture, {
                                ...binding, action: e.target.value,
                                params: defaultGestureParams(e.target.value, apps[0]?.id, scenarios[0]?.id),
                              })}>
                        {Object.entries(info.actions).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
                      </select>
                    </td>
                    <td>
                      <BindingParams binding={binding} scenarios={scenarios}
                                     onChange={(params) => setBinding(gesture, { ...binding, params })} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
