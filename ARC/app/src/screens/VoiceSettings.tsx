import { useCallback, useEffect, useState } from "react";

import { IconTrash } from "../components/Icons";
import { Dialog, Field, Panel } from "../components/ui";
import { del, get, post } from "../lib/api";
import { useArc } from "../lib/store";
import type { VoiceModel } from "../lib/types";
import { VOICE_LABEL } from "./Home";

interface DevicesInfo {
  inputs: { index: number; name: string; default: boolean }[];
  voices: { name: string; language: string; russian: boolean }[];
  cuda: boolean;
}

interface ModelsInfo {
  models: VoiceModel[];
  free_mb: number;
  dir: string;
}

const KIND_TITLE: Record<VoiceModel["kind"], string> = {
  stt: "Распознавание речи (Whisper)",
  tts_runtime: "Синтез речи Piper",
  tts_voice: "Голоса Piper",
};

export function formatMb(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} ГБ` : `${Math.round(mb)} МБ`;
}

function ModelRow({ model, freeMb, onAsk, onCancel, onRemove }: {
  model: VoiceModel;
  freeMb: number;
  onAsk: (m: VoiceModel) => void;
  onCancel: (m: VoiceModel) => void;
  onRemove: (m: VoiceModel) => void;
}) {
  const job = model.download;
  const downloading = job?.state === "downloading";
  return (
    <div className="model-row" data-testid={`model-${model.id}`}>
      <div className="model-row__info">
        <b>{model.title}</b> <span className="faint">{formatMb(model.size_mb)}</span>
        <div className="faint">{model.description}</div>
        {downloading && (
          <div className="progress" role="progressbar" aria-valuenow={Math.round(job.progress * 100)}>
            <span style={{ width: `${Math.round(job.progress * 100)}%` }} />
            <em>{job.done_mb} / {job.total_mb} МБ</em>
          </div>
        )}
        {job && !downloading && job.state !== "done" && (
          <div className={job.state === "error" ? "danger-text" : "dim"}>{job.message}</div>
        )}
      </div>
      <div className="model-row__actions">
        {model.installed ? (
          <>
            <span className="tag tag--ok">установлена</span>
            <button className="btn btn--sm btn--danger" title="Удалить модель" onClick={() => onRemove(model)}>
              <IconTrash size={14} />
            </button>
          </>
        ) : downloading ? (
          <button className="btn btn--sm" onClick={() => onCancel(model)}>Отменить</button>
        ) : !model.supported ? (
          <span className="tag">только Windows</span>
        ) : (
          <button className="btn btn--sm" onClick={() => onAsk(model)} disabled={model.size_mb > freeMb}
                  data-testid={`download-${model.id}`}>
            Загрузить
          </button>
        )}
      </div>
    </div>
  );
}

export function VoiceSettingsPanel() {
  const { settings, updateSettings, notify, voice } = useArc();
  const [devices, setDevices] = useState<DevicesInfo | null>(null);
  const [models, setModels] = useState<ModelsInfo | null>(null);
  const [asking, setAsking] = useState<VoiceModel | null>(null);
  const [testing, setTesting] = useState(false);

  const loadModels = useCallback(async () => {
    try {
      setModels(await get<ModelsInfo>("/api/voice/models"));
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  }, [notify]);

  useEffect(() => {
    void loadModels();
    get<DevicesInfo>("/api/voice/devices").then(setDevices).catch(() => undefined);
  }, [loadModels]);

  const downloading = models?.models.some((m) => m.download?.state === "downloading") ?? false;
  useEffect(() => {
    if (!downloading) return;
    const timer = window.setInterval(() => void loadModels(), 700);
    return () => window.clearInterval(timer);
  }, [downloading, loadModels]);

  if (!settings) return null;
  const v = settings.voice;
  const save = (patch: Record<string, unknown>) => void updateSettings({ voice: patch });

  const startDownload = async () => {
    if (!asking) return;
    try {
      await post("/api/voice/models/download", { id: asking.id, confirm: true });
      notify("info", `Загрузка «${asking.title}» начата`);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
    setAsking(null);
    void loadModels();
  };
  const cancel = async (m: VoiceModel) => {
    await post("/api/voice/models/cancel", { id: m.id }).catch(() => undefined);
    void loadModels();
  };
  const remove = async (m: VoiceModel) => {
    try {
      await del(`/api/voice/models/${m.id}`);
      notify("ok", `Модель «${m.title}» удалена`);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
    void loadModels();
  };
  const testTts = async () => {
    setTesting(true);
    try {
      const r = await post<{ spoken: boolean; warning: string | null }>("/api/voice/tts-test");
      if (!r.spoken) notify("error", r.warning || "Озвучка выключена");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    } finally {
      setTesting(false);
    }
  };

  const sttModels = models?.models.filter((m) => m.kind === "stt") ?? [];
  const groups: VoiceModel["kind"][] = ["stt", "tts_runtime", "tts_voice"];

  return (
    <>
      <Panel title="Голос: распознавание" tag={voice ? (VOICE_LABEL[voice.state] ?? voice.state) : "—"} testId="voice-settings">
        <div className="form-grid">
          <Field label="Режим по умолчанию" hint="Постоянное прослушивание требует слова активации">
            <select className="select" value={v.mode} onChange={(e) => save({ mode: e.target.value })}>
              <option value="ptt">Нажать и говорить (Ctrl+Alt+Space)</option>
              <option value="continuous">Постоянное прослушивание</option>
            </select>
          </Field>
          <Field label="Модель распознавания">
            <select className="select" value={v.stt_model} onChange={(e) => save({ stt_model: e.target.value })}>
              {sttModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title} — {formatMb(m.size_mb)}{m.installed ? " ✓" : ""}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Вычисления" hint={devices ? (devices.cuda ? "CUDA найдена" : "CUDA не найдена: будет CPU (медленнее)") : ""}>
            <select className="select" value={v.stt_device} onChange={(e) => save({ stt_device: e.target.value })}>
              <option value="auto">Автоматически</option>
              <option value="cuda">Видеокарта NVIDIA (CUDA)</option>
              <option value="cpu">Процессор</option>
            </select>
          </Field>
          <Field label="Микрофон">
            <select className="select" value={v.input_device ?? ""} data-testid="input-device"
                    onChange={(e) => save({ input_device: e.target.value || null })}>
              <option value="">По умолчанию Windows</option>
              {devices?.inputs.map((d) => <option key={d.index} value={d.name}>{d.name}</option>)}
            </select>
          </Field>
          <Field label={`Чувствительность: ${Math.round(v.vad_sensitivity * 100)}%`}
                 hint="Выше — слышит тихую речь, но чаще реагирует на шум">
            <input className="input" type="range" min={0} max={1} step={0.05} value={v.vad_sensitivity}
                   onChange={(e) => save({ vad_sensitivity: Number(e.target.value) })} />
          </Field>
          <Field label={`Пауза конца фразы: ${(v.silence_ms / 1000).toFixed(1)} с`}>
            <input className="input" type="range" min={300} max={2000} step={100} value={v.silence_ms}
                   onChange={(e) => save({ silence_ms: Number(e.target.value) })} />
          </Field>
        </div>
        {devices && devices.inputs.length === 0 && (
          <div className="banner">Микрофон не найден. Текстовые команды работают как обычно.</div>
        )}
      </Panel>

      <Panel title="Голос: ответы">
        <div className="form-grid">
          <Field label="Озвучка ответов">
            <select className="select" value={v.tts_engine} onChange={(e) => save({ tts_engine: e.target.value, tts_voice: "" })}>
              <option value="sapi">Windows (встроенная, без загрузки)</option>
              <option value="piper">Piper (локальная нейросеть)</option>
              <option value="off">Не озвучивать</option>
            </select>
          </Field>
          <Field label="Голос" hint={v.tts_engine === "sapi" ? "Русский голос: «Параметры → Время и язык → Речь»" : ""}>
            <select className="select" value={v.tts_voice} onChange={(e) => save({ tts_voice: e.target.value })}
                    disabled={v.tts_engine === "off"}>
              <option value="">Автоматически (русский)</option>
              {v.tts_engine === "sapi" && devices?.voices.map((x) => (
                <option key={x.name} value={x.name}>{x.name}{x.russian ? " — RU" : ""}</option>
              ))}
              {v.tts_engine === "piper" && models?.models.filter((m) => m.kind === "tts_voice" && m.installed).map((m) => (
                <option key={m.id} value={m.id}>{m.title}</option>
              ))}
            </select>
          </Field>
          <Field label={`Скорость: ${v.tts_rate.toFixed(2)}×`}>
            <input className="input" type="range" min={0.5} max={2} step={0.05} value={v.tts_rate}
                   onChange={(e) => save({ tts_rate: Number(e.target.value) })} />
          </Field>
          <Field label={`Громкость: ${v.tts_volume}%`}>
            <input className="input" type="range" min={0} max={100} step={5} value={v.tts_volume}
                   onChange={(e) => save({ tts_volume: Number(e.target.value) })} />
          </Field>
        </div>
        <div className="btn-row" style={{ marginTop: 8 }}>
          <button className="btn" onClick={() => void testTts()} disabled={testing || v.tts_engine === "off"}>
            {testing ? "Говорю…" : "Проверить голос"}
          </button>
          {voice?.tts.warning && <span className="danger-text">{voice.tts.warning}</span>}
          {settings.profile.silent && <span className="dim">Режим тишины: голосовые ответы отключены</span>}
        </div>
      </Panel>

      <Panel title="Локальные модели" tag={models ? `свободно ${formatMb(models.free_mb)}` : "—"}>
        <p className="dim">
          Модели не загружаются автоматически. Загрузка — только по кнопке, после подтверждения размера.
          Файлы: <span className="selectable">{models?.dir}</span>
        </p>
        {groups.map((kind) => (
          <div key={kind} className="model-group">
            <div className="mono-label">{KIND_TITLE[kind]}</div>
            {models?.models.filter((m) => m.kind === kind).map((m) => (
              <ModelRow key={m.id} model={m} freeMb={models.free_mb} onAsk={setAsking} onCancel={cancel} onRemove={remove} />
            ))}
          </div>
        ))}
      </Panel>

      {asking && (
        <Dialog title="Загрузка модели" onClose={() => setAsking(null)}
                footer={
                  <>
                    <button className="btn btn--ghost" onClick={() => setAsking(null)}>Отмена</button>
                    <button className="btn btn--solid" onClick={() => void startDownload()} data-testid="confirm-download">
                      Загрузить {formatMb(asking.size_mb)}
                    </button>
                  </>
                }>
          <p><b>{asking.title}</b> — {asking.description}</p>
          <p>
            Размер: <b>{formatMb(asking.size_mb)}</b>. Свободно на диске: <b>{formatMb(models?.free_mb ?? 0)}</b>.
          </p>
          <p className="dim">
            Файлы будут загружены из интернета (HuggingFace / GitHub) один раз; распознавание и синтез затем работают
            полностью офлайн. Лицензия: {asking.license || "—"}.
          </p>
        </Dialog>
      )}
    </>
  );
}
