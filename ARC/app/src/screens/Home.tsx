import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import { ArcCore, CoreState } from "../components/ArcCore";
import { Gauge } from "../components/Gauge";
import {
  IconCam,
  IconChip,
  IconFolder,
  IconMic,
  IconNet,
  IconRepeat,
  IconSend,
  IconStop,
  IconUndo,
} from "../components/Icons";
import { Oscilloscope } from "../components/Oscilloscope";
import { formatTime, Panel, RiskBadge, STATUS_LABEL, statusTone } from "../components/ui";
import { useArc } from "../lib/store";
import type { CommandResponse } from "../lib/types";

const AI_LABEL: Record<string, string> = {
  ready: "готова",
  model_missing: "нет модели",
  offline: "не запущена",
  disabled: "выключено",
  blocked: "заблокировано",
};

function StatusRow({ icon, name, value, tone, children }: {
  icon: React.ReactNode;
  name: string;
  value: string;
  tone: "ok" | "warn" | "danger" | "accent" | "off";
  children?: React.ReactNode;
}) {
  return (
    <div className="status-row">
      <span className="status-row__icon">{icon}</span>
      <span className="status-row__name">{name}</span>
      <span className={`status-row__value status-row__value--${tone}`}>
        <span className={`led ${tone === "off" ? "" : `led--${tone}`}`} /> {value}
      </span>
      {children && <span className="status-row__ctl">{children}</span>}
    </div>
  );
}

function StatusPanel() {
  const { state, ai, settings, updateSettings } = useArc();
  if (!state || !settings) return <Panel title="Состояние"><div className="empty">Ожидание ядра…</div></Panel>;
  const mic = settings.devices.microphone_enabled;
  const cam = settings.devices.camera_enabled;
  const aiOn = settings.devices.local_ai_enabled;
  return (
    <Panel title="Состояние" testId="status-panel">
      <StatusRow icon={<IconMic size={16} />} name="Микрофон" tone={mic ? "warn" : "off"}
                 value={mic ? "модуль не установлен" : "выключен"}>
        <button className="btn btn--sm" onClick={() => updateSettings({ devices: { microphone_enabled: !mic } })}
                title={state.voice.message} data-testid="toggle-mic">{mic ? "Откл." : "Вкл."}</button>
      </StatusRow>
      <StatusRow icon={<IconCam size={16} />} name="Камера" tone={cam ? "warn" : "off"}
                 value={cam ? "модуль не установлен" : "выключена"}>
        <button className="btn btn--sm" onClick={() => updateSettings({ devices: { camera_enabled: !cam } })}
                title={state.camera.message} data-testid="toggle-camera">{cam ? "Откл." : "Вкл."}</button>
      </StatusRow>
      <StatusRow icon={<IconNet size={16} />} name="Сеть" tone={state.mode === "ONLINE" ? "accent" : "ok"}
                 value={state.mode === "ONLINE" ? "ONLINE" : "LOCAL"}>
        <button className="btn btn--sm" data-testid="toggle-mode" disabled={!state.online_allowed && state.mode === "LOCAL"}
                title={state.online_allowed ? "Переключить режим" : "Онлайн-функции выключены в настройках"}
                onClick={() => updateSettings({ network: { mode: state.mode === "ONLINE" ? "LOCAL" : "ONLINE" } })}>
          {state.mode === "ONLINE" ? "→ LOCAL" : "→ ONLINE"}
        </button>
      </StatusRow>
      <StatusRow icon={<IconChip size={16} />} name="Локальный ИИ"
                 tone={!aiOn ? "off" : ai?.state === "ready" ? "ok" : "warn"}
                 value={ai ? `${AI_LABEL[ai.state] ?? ai.state}` : "проверка…"}>
        <button className="btn btn--sm" onClick={() => updateSettings({ devices: { local_ai_enabled: !aiOn } })}
                title={ai?.message} data-testid="toggle-ai">{aiOn ? "Откл." : "Вкл."}</button>
      </StatusRow>
      {ai && aiOn && <div className="status-note faint" title={ai.message}>{ai.model} · {ai.message}</div>}
    </Panel>
  );
}

function SystemPanel() {
  const { stats } = useArc();
  const gpu = stats?.gpu;
  return (
    <Panel title="Телеметрия" tag={stats ? formatTime(stats.ts) : "—"}>
      <div className="gauges">
        <Gauge label="CPU" value={stats ? stats.cpu : null} />
        <Gauge label="RAM" value={stats ? stats.ram.percent : null}
               detail={stats ? `${stats.ram.used_gb}/${stats.ram.total_gb} ГБ` : undefined} />
        <Gauge label="GPU" value={gpu ? gpu.load : null}
               detail={gpu ? `${Math.round(gpu.mem_used_mb / 1024 * 10) / 10}/${Math.round(gpu.mem_total_mb / 1024)} ГБ · ${gpu.temp_c}°` : "нет данных"} />
      </div>
    </Panel>
  );
}

function QuickApps() {
  const { apps, launchApp } = useArc();
  const pinned = apps.filter((a) => a.pinned && a.enabled).slice(0, 8);
  const recent = apps
    .filter((a) => !a.pinned && a.enabled && a.last_launched)
    .sort((a, b) => (b.last_launched ?? 0) - (a.last_launched ?? 0))
    .slice(0, Math.max(0, 6 - pinned.length));
  const list = [...pinned, ...recent];
  return (
    <Panel title="Быстрый запуск" tag={`${pinned.length} закреплено`}>
      {list.length === 0 ? (
        <div className="empty">Закрепите приложения в разделе «Приложения»</div>
      ) : (
        <div className="quick-apps">
          {list.map((app) => (
            <button key={app.id} className="quick-app" onClick={() => void launchApp(app.id)}
                    title={`${app.name}${app.run_as_admin ? " (администратор)" : ""}`} data-testid="quick-app">
              <span className="quick-app__glyph">{app.name.slice(0, 2).toUpperCase()}</span>
              <span className="quick-app__name">{app.name}</span>
              {app.pinned && <span className="quick-app__pin" aria-label="закреплено">●</span>}
            </button>
          ))}
        </div>
      )}
    </Panel>
  );
}

function ResponseBlock({ response, latest }: { response: CommandResponse; latest: boolean }) {
  const { sendCommand } = useArc();
  const tone = statusTone(response.status);
  const files: Array<{ path: string; name: string; is_dir: boolean }> = response.data?.files ?? [];
  return (
    <div className={`exchange ${latest ? "exchange--latest" : ""}`}>
      {response.input && <div className="exchange__in"><span className="prompt">&gt;</span> {response.input}</div>}
      <div className="exchange__out">
        <span className={`tag ${tone ? `tag--${tone}` : ""}`}>{STATUS_LABEL[response.status] ?? response.status}</span>
        {response.risk && <RiskBadge risk={response.risk} />}
        <span className="exchange__msg selectable">{response.message}</span>
      </div>
      {latest && response.clarify && response.clarify.options.length > 0 && (
        <div className="btn-row exchange__options">
          {response.clarify.options.map((option, index) => (
            <button key={option} className="btn btn--sm" onClick={() => void sendCommand(option)}>
              {index + 1}. {option}
            </button>
          ))}
        </div>
      )}
      {files.length > 0 && (
        <ul className="files">
          {files.slice(0, 8).map((f) => (
            <li key={f.path}>
              <span className="cell-path" title={f.path}>{f.path}</span>
              <button className="btn btn--sm btn--ghost" onClick={() => window.arc?.showInFolder(f.path)}
                      title="Показать в проводнике"><IconFolder size={14} /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Terminal() {
  const { conversation, sendCommand, busy, backend } = useArc();
  const [text, setText] = useState("");
  const [recall, setRecall] = useState(-1);
  const logRef = useRef<HTMLDivElement>(null);
  const inputs = useMemo(() => conversation.map((c) => c.input).filter(Boolean).reverse(), [conversation]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [conversation.length]);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!text.trim() || busy) return;
    const value = text;
    setText("");
    setRecall(-1);
    await sendCommand(value);
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowUp" && inputs.length) {
      e.preventDefault();
      const next = Math.min(recall + 1, inputs.length - 1);
      setRecall(next);
      setText(inputs[next]);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = recall - 1;
      setRecall(Math.max(-1, next));
      setText(next >= 0 ? inputs[next] : "");
    }
  };

  return (
    <Panel title="Терминал" tag={busy ? "обработка" : "текстовый ввод"} className="terminal" testId="terminal">
      <div className="terminal__log" ref={logRef} aria-live="polite">
        {conversation.length === 0 ? (
          <div className="terminal__hello faint">
            A.R.C. готов. Введите команду, например: <span className="dim">открой проводник</span>,{" "}
            <span className="dim">увеличь громкость на 20 процентов</span>, <span className="dim">что ты умеешь</span>.
          </div>
        ) : (
          conversation.map((r, i) => <ResponseBlock key={r.id} response={r} latest={i === conversation.length - 1} />)
        )}
      </div>
      <form className="terminal__input" onSubmit={submit}>
        <span className="prompt">&gt;</span>
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey}
               placeholder={backend.state === "ready" ? "Введите команду…" : "Ядро недоступно"}
               disabled={backend.state !== "ready"} aria-label="Команда" data-testid="command-input" maxLength={1000}
               autoFocus />
        <button className="btn btn--solid" type="submit" disabled={!text.trim() || busy || backend.state !== "ready"}
                data-testid="command-send" aria-label="Выполнить"><IconSend size={16} /></button>
      </form>
    </Panel>
  );
}

function ControlPanel() {
  const { state, undo, repeat, setEmergency } = useArc();
  const estop = state?.emergency_stop ?? false;
  return (
    <Panel title="Управление" alert={estop}>
      <div className="control-grid">
        <button className="btn" onClick={() => void undo()} disabled={!state?.can_undo} data-testid="btn-undo">
          <IconUndo size={16} /> Отменить
        </button>
        <button className="btn" onClick={() => void repeat()} disabled={!state?.can_repeat} data-testid="btn-repeat">
          <IconRepeat size={16} /> Повторить
        </button>
        <button className={`btn btn--danger ${estop ? "btn--solid" : ""} control-grid__wide`} data-testid="btn-estop"
                onClick={() => void setEmergency(!estop)} title="Ctrl+Alt+End">
          <IconStop size={16} /> {estop ? "Снять аварийную остановку" : "Аварийная остановка"}
        </button>
      </div>
    </Panel>
  );
}

function HistoryPanel() {
  const { history } = useArc();
  return (
    <Panel title="Последние действия" className="history-panel" tag={`${history.length}`}>
      {history.length === 0 ? (
        <div className="empty">История пуста</div>
      ) : (
        <ol className="history">
          {history.slice(0, 30).map((h) => {
            const tone = statusTone(h.status);
            return (
              <li key={h.id} className="history__item">
                <span className="history__time faint">{formatTime(h.ts)}</span>
                <span className={`led ${tone ? `led--${tone === "accent" ? "accent" : tone}` : ""}`} />
                <span className="history__text">
                  <span className="history__input">{h.input || h.action || "—"}</span>
                  <span className="history__msg faint">{h.message}</span>
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}

export function Home() {
  const { state, backend, busy, conversation } = useArc();
  const last = conversation[conversation.length - 1] ?? state?.last_response ?? null;
  let core: CoreState = "idle";
  let coreLabel = "ОЖИДАНИЕ";
  if (backend.state !== "ready") {
    core = "offline";
    coreLabel = backend.state === "failed" ? "ЯДРО НЕДОСТУПНО" : "ЗАПУСК";
  } else if (state?.emergency_stop) {
    core = "alert";
    coreLabel = "АВАРИЙНЫЙ СТОП";
  } else if (busy) {
    core = "busy";
    coreLabel = "ОБРАБОТКА";
  } else if (state?.pending_confirmation || state?.dialog) {
    core = "attention";
    coreLabel = state?.pending_confirmation ? "ПОДТВЕРЖДЕНИЕ" : "УТОЧНЕНИЕ";
  }
  return (
    <div className="home">
      <div className="home__left">
        <StatusPanel />
        <SystemPanel />
        <QuickApps />
      </div>
      <div className="home__center">
        <div className="core-stage">
          <ArcCore state={core} mode={state?.mode ?? "LOCAL"} label={coreLabel} />
          <div className="voice">
            <button className="voice__btn" disabled aria-disabled="true" data-testid="voice-button"
                    title={state?.voice.message ?? "Голосовой модуль подключается на этапе 2"}>
              <IconMic size={22} />
              <span>ГОЛОС</span>
            </button>
            <div className="voice__note faint">{state?.voice.message ?? "Голосовой модуль подключается на этапе 2"}</div>
          </div>
        </div>
        <Panel title="Сигнал" className="scope-panel" tag={busy ? "активность" : "микрофон не подключён"}>
          <Oscilloscope active={busy} label={busy ? "ОБРАБОТКА КОМАНДЫ" : "НЕТ СИГНАЛА"} />
          <div className="last-line">
            <span className="mono-label">Последняя команда</span>
            <span className="last-line__text selectable" data-testid="last-command">{last?.input || "—"}</span>
          </div>
          <div className="last-line">
            <span className="mono-label">Ответ A.R.C.</span>
            <span className="last-line__text glow selectable" data-testid="last-response">{last?.message || "—"}</span>
          </div>
        </Panel>
        <Terminal />
      </div>
      <div className="home__right">
        <ControlPanel />
        <HistoryPanel />
      </div>
    </div>
  );
}

