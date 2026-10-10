import { useEffect, useState } from "react";

import { Field, Panel, Toggle } from "../components/ui";
import { useArc } from "../lib/store";
import type { Settings as SettingsT } from "../lib/types";

/** Text input that saves on blur / Enter instead of on every keystroke. */
function LazyInput({ value, onCommit, ...rest }: {
  value: string | number;
  onCommit: (value: string) => void;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  const commit = () => draft !== String(value) && onCommit(draft);
  return (
    <input className="input" value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commit}
           onKeyDown={(e) => e.key === "Enter" && commit()} {...rest} />
  );
}

export function Settings() {
  const { settings, updateSettings, ai, refreshAi } = useArc();
  const [info, setInfo] = useState<{ version: string; electron: string; userData: string } | null>(null);
  useEffect(() => {
    window.arc?.appInfo().then(setInfo).catch(() => undefined);
  }, []);
  if (!settings) return <div className="empty">Ожидание ядра…</div>;
  const s = settings;
  const save = (section: keyof SettingsT, patch: Record<string, unknown>) => void updateSettings({ [section]: patch });

  return (
    <div className="screen">
      <div className="page-title">
        <h1>Настройки</h1>
        <span className="dim">Сохраняются автоматически</span>
      </div>
      <div className="grid-2">
        <Panel title="Общие">
          <Toggle checked={s.general.autostart} onChange={(v) => save("general", { autostart: v })}
                  label="Запускать вместе с Windows" hint="A.R.C. стартует свёрнутым в трей" />
          <Toggle checked={s.general.start_minimized} onChange={(v) => save("general", { start_minimized: v })}
                  label="Запускать свёрнутым в трей" />
          <div className="form-grid" style={{ marginTop: 8 }}>
            <Field label="Слово активации" hint="Обязательно для голосовых команд в режиме прослушивания">
              <LazyInput value={s.general.wake_word} maxLength={30}
                         onCommit={(v) => v.trim() && save("general", { wake_word: v.trim() })} />
            </Field>
            <Field label="Порог уверенности распознавания" hint="Голосовые команды ниже порога игнорируются">
              <input className="input" type="range" min={0.3} max={0.95} step={0.05} value={s.general.min_confidence}
                     onChange={(e) => save("general", { min_confidence: Number(e.target.value) })} />
              <span className="dim">{Math.round(s.general.min_confidence * 100)}%</span>
            </Field>
          </div>
          <Toggle checked={s.general.require_wake_word_for_voice}
                  onChange={(v) => save("general", { require_wake_word_for_voice: v })}
                  label="Требовать слово активации для голоса"
                  hint="Защита от выполнения случайно услышанной фоновой речи" />
        </Panel>
        <Panel title="Интерфейс">
          <div className="form-grid">
            <Field label="Цветовая тема">
              <select className="select" value={s.ui.theme} data-testid="theme-select"
                      onChange={(e) => save("ui", { theme: e.target.value })}>
                <option value="amber">Янтарь (по умолчанию)</option>
                <option value="phosphor">Фосфор</option>
                <option value="ice">Лёд</option>
              </select>
            </Field>
            <Field label={`Масштаб: ${Math.round(s.ui.scale * 100)}%`}>
              <input className="input" type="range" min={0.75} max={1.5} step={0.05} value={s.ui.scale}
                     onChange={(e) => save("ui", { scale: Number(e.target.value) })} />
            </Field>
          </div>
          <Toggle checked={s.ui.animations} onChange={(v) => save("ui", { animations: v })} label="Анимация" />
          <Toggle checked={s.ui.scanlines} onChange={(v) => save("ui", { scanlines: v })} label="Эффект ЭЛТ (сканлайны)" />
        </Panel>
      </div>
      <div className="grid-2">
        <Panel title="Сеть: LOCAL / ONLINE" tag={s.network.mode}>
          <Toggle checked={s.network.online_allowed} onChange={(v) => save("network", { online_allowed: v })}
                  label="Разрешить онлайн-функции"
                  hint="Выключение полностью запрещает режим ONLINE и запросы в интернет" />
          <Toggle checked={s.network.mode === "ONLINE"} disabled={!s.network.online_allowed}
                  onChange={(v) => save("network", { mode: v ? "ONLINE" : "LOCAL" })}
                  label="Режим ONLINE" hint="В режиме LOCAL A.R.C. не обращается к интернету" />
          <Field label="Поисковая система" hint="https-адрес с {query}">
            <LazyInput value={s.network.search_url} onCommit={(v) => save("network", { search_url: v })} />
          </Field>
        </Panel>
        <Panel title="Устройства">
          <Toggle checked={s.devices.microphone_enabled} onChange={(v) => save("devices", { microphone_enabled: v })}
                  label="Микрофон" hint="Модуль голоса (этап 2) не будет открывать микрофон, если выключено" />
          <Toggle checked={s.devices.camera_enabled} onChange={(v) => save("devices", { camera_enabled: v })}
                  label="Камера" hint="Модуль жестов (этап 3) не будет открывать камеру, если выключено" />
          <Toggle checked={s.devices.local_ai_enabled} onChange={(v) => save("devices", { local_ai_enabled: v })}
                  label="Локальный ИИ (Ollama)" />
        </Panel>
      </div>
      <Panel title="Локальная модель (Ollama)" tag={ai ? ai.state : "—"}>
        <div className="form-grid">
          <Field label="Адрес сервера" hint="Адрес вне этого компьютера считается внешним сервисом (нужен ONLINE)">
            <LazyInput value={s.ai.ollama_url} onCommit={(v) => save("ai", { ollama_url: v })} />
          </Field>
          <Field label="Модель" hint={ai?.models?.length ? `Установлены: ${ai.models.join(", ")}` : "ollama pull qwen2.5-coder:7b"}>
            <LazyInput value={s.ai.model} onCommit={(v) => v.trim() && save("ai", { model: v.trim() })} />
          </Field>
          <Field label="Температура">
            <LazyInput type="number" min={0} max={2} step={0.1} value={s.ai.temperature}
                       onCommit={(v) => save("ai", { temperature: Number(v) })} />
          </Field>
          <Field label="Тайм-аут ответа, с">
            <LazyInput type="number" min={1} max={600} value={s.ai.timeout_s}
                       onCommit={(v) => save("ai", { timeout_s: Number(v) })} />
          </Field>
        </div>
        <div className="btn-row" style={{ marginTop: 10 }}>
          <button className="btn" onClick={() => void refreshAi(true)} data-testid="ai-check">Проверить подключение</button>
          <span className={ai?.state === "ready" ? "ok-text" : "dim"}>{ai?.message}</span>
        </div>
        <p className="faint">
          На этапе 1 A.R.C. только проверяет доступность модели; разбор сложных фраз моделью добавляется на этапе 4.
          Модели не загружаются автоматически.
        </p>
      </Panel>
      {info && (
        <p className="faint">
          A.R.C. {info.version} · Electron {info.electron} · данные интерфейса: {info.userData}
        </p>
      )}
    </div>
  );
}
