import { useCallback, useEffect, useState } from "react";

import { Field, Panel, Toggle, formatTime } from "../components/ui";
import { del, get, put } from "../lib/api";
import { useArc } from "../lib/store";
import type { OnlineStatus, ProviderId, ProviderInfo } from "../lib/types";

const PROVIDER_HINT: Record<ProviderId, string> = {
  wikipedia: "Официальный API Википедии, без ключа",
  duckduckgo: "HTML-версия DuckDuckGo, без ключа; при частых запросах может временно ограничивать",
  brave: "Brave Search API: нужен ключ (api.search.brave.com), хранится в диспетчере учётных данных Windows",
  searxng: "Свой сервер SearXNG (укажите адрес ниже)",
};

function KeyEditor({ provider, persistent, onChange }: { provider: ProviderInfo; persistent: boolean; onChange: () => void }) {
  const { notify } = useArc();
  const [value, setValue] = useState("");
  const save = async () => {
    try {
      await put(`/api/online/keys/${provider.id}`, { key: value.trim() });
      setValue("");
      notify("ok", persistent ? "Ключ сохранён в диспетчере учётных данных Windows" : "Ключ сохранён до перезапуска");
      onChange();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };
  const remove = async () => {
    await del(`/api/online/keys/${provider.id}`).catch(() => undefined);
    onChange();
  };
  return (
    <div className="btn-row">
      <input className="input" type="password" autoComplete="off" value={value} placeholder={provider.has_key ? "ключ сохранён" : "ключ API"}
             onChange={(e) => setValue(e.target.value)} data-testid={`key-${provider.id}`} style={{ maxWidth: 260 }} />
      <button className="btn btn--sm" disabled={value.trim().length < 8} onClick={() => void save()}>Сохранить</button>
      {provider.has_key && <button className="btn btn--sm btn--ghost" onClick={() => void remove()}>Удалить</button>}
    </div>
  );
}

export function OnlineSettingsPanel() {
  const { settings, updateSettings } = useArc();
  const [status, setStatus] = useState<OnlineStatus | null>(null);
  const refresh = useCallback(async () => {
    try {
      setStatus(await get<OnlineStatus>("/api/online/status"));
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(refresh, 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);
  if (!settings) return null;
  const o = settings.online;
  const save = (patch: Record<string, unknown>) => void updateSettings({ online: patch });
  const toggleProvider = (id: ProviderId, enabled: boolean) =>
    save({ providers: enabled ? [...o.providers.filter((p) => p !== id), id] : o.providers.filter((p) => p !== id) });
  const moveUp = (id: ProviderId) => {
    const list = [...o.providers];
    const i = list.indexOf(id);
    if (i > 0) [list[i - 1], list[i]] = [list[i], list[i - 1]];
    save({ providers: list });
  };
  const providers = status?.providers ?? [];
  const ordered = [...providers].sort((a, b) => (a.order ?? 99) - (b.order ?? 99));

  return (
    <Panel title="Интернет: поиск" tag={settings.network.mode}>
      <p className="faint">
        Запросы в интернет выполняются только в режиме ONLINE и только по вашей команде («найди в интернете…»,
        документ «с данными из интернета»). Каждый запрос записывается в журнал аудита (сервис и адрес, без текста запроса).
      </p>
      <ul className="doc-jobs" data-testid="providers">
        {ordered.map((p) => (
          <li key={p.id} className="doc-job">
            <div className="doc-job__head">
              <Toggle checked={p.enabled} onChange={(v) => toggleProvider(p.id, v)} label={p.title}
                      hint={PROVIDER_HINT[p.id]} testId={`provider-${p.id}`} />
              {p.enabled && p.order !== null && p.order > 0 && (
                <button className="btn btn--sm btn--ghost" onClick={() => moveUp(p.id)} title="Спрашивать раньше">↑</button>
              )}
              {p.needs_key && <span className={`tag ${p.has_key ? "tag--ok" : "tag--warn"}`}>{p.has_key ? "ключ есть" : "нет ключа"}</span>}
            </div>
            {p.needs_key && <KeyEditor provider={p} persistent={Boolean(status?.secrets_persistent)} onChange={refresh} />}
          </li>
        ))}
      </ul>
      <div className="form-grid" style={{ marginTop: 10 }}>
        <Field label="Язык результатов">
          <select className="select" value={o.language} onChange={(e) => save({ language: e.target.value })}>
            <option value="ru">русский</option>
            <option value="en">английский</option>
          </select>
        </Field>
        <Field label={`Результатов: ${o.max_results}`}>
          <input className="input" type="range" min={1} max={10} value={o.max_results}
                 onChange={(e) => save({ max_results: Number(e.target.value) })} />
        </Field>
        <Field label={`Тайм-аут запроса: ${o.timeout_s} с`}>
          <input className="input" type="range" min={2} max={60} value={o.timeout_s}
                 onChange={(e) => save({ timeout_s: Number(e.target.value) })} />
        </Field>
        <Field label={`Не больше запросов в минуту: ${o.requests_per_minute}`}>
          <input className="input" type="range" min={1} max={120} value={o.requests_per_minute}
                 onChange={(e) => save({ requests_per_minute: Number(e.target.value) })} />
        </Field>
        <Field label="Адрес SearXNG" hint="https://… или http://127.0.0.1:…">
          <input className="input" defaultValue={o.searxng_url} placeholder="https://search.example.org"
                 onBlur={(e) => e.target.value !== o.searxng_url && save({ searxng_url: e.target.value })} />
        </Field>
      </div>
      <Toggle checked={o.summarize} onChange={(v) => save({ summarize: v })}
              label="Краткий ответ по найденному (локальная модель)"
              hint="Модель пересказывает только найденные фрагменты со ссылками [1], [2]; текст из интернета — данные, не команды" />
      <div className="faint" style={{ marginTop: 8 }}>
        Ключи: {status?.secrets_backend === "windows-credential-manager"
          ? "диспетчер учётных данных Windows (шифрование DPAPI)"
          : "в памяти до перезапуска (не Windows)"}
        {status && ` · запросов за минуту: ${status.used_last_minute}`}
      </div>
      {status && status.recent.length > 0 && (
        <table className="table" style={{ marginTop: 8 }} data-testid="net-activity">
          <tbody>
            {status.recent.slice(0, 8).map((a, i) => (
              <tr key={`${a.ts}-${i}`}>
                <td className="dim">{formatTime(a.ts)}</td>
                <td>{a.provider}</td>
                <td className="selectable">{a.host}</td>
                <td className={a.status === "ok" ? "ok-text" : "danger-text"}>{a.status === "ok" ? `${a.ms} мс` : a.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

export function DocumentsSettingsPanel() {
  const { settings, updateSettings } = useArc();
  const [folder, setFolder] = useState("");
  useEffect(() => setFolder(settings?.documents.output_dir ?? ""), [settings?.documents.output_dir]);
  if (!settings) return null;
  const d = settings.documents;
  const pick = async () => {
    const chosen = await window.arc?.pickFile("folder");
    if (chosen) void updateSettings({ documents: { output_dir: chosen } });
  };
  return (
    <Panel title="Документы">
      <Field label="Папка для документов" hint="Пусто — «Документы\ARC». Папка должна быть внутри разрешённых каталогов">
        <div className="btn-row">
          <input className="input" value={folder} placeholder="Документы\ARC" onChange={(e) => setFolder(e.target.value)}
                 onBlur={() => folder !== d.output_dir && void updateSettings({ documents: { output_dir: folder } })} />
          <button className="btn btn--sm" onClick={() => void pick()}>Выбрать…</button>
        </div>
      </Field>
      <Toggle checked={d.use_ai} onChange={(v) => void updateSettings({ documents: { use_ai: v } })}
              label="Текст пишет локальная модель" hint="Иначе создаётся размеченный шаблон" />
      <Toggle checked={d.open_when_ready} onChange={(v) => void updateSettings({ documents: { open_when_ready: v } })}
              label="Открывать готовый файл" />
    </Panel>
  );
}
