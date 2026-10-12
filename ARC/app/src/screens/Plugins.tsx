import { useCallback, useEffect, useState } from "react";

import { Dialog, Field, Panel, Toggle } from "../components/ui";
import { del, get, post, put } from "../lib/api";
import { useArc } from "../lib/store";
import type { PluginInfo, PluginsView } from "../lib/types";
import { MODULE_LABEL } from "./Permissions";

const TRUST: Record<PluginInfo["trust"], { label: string; tone: string }> = {
  trusted: { label: "подписан", tone: "ok" },
  unsigned: { label: "без подписи", tone: "warn" },
  untrusted_key: { label: "неизвестный ключ", tone: "danger" },
  invalid: { label: "подпись не сходится", tone: "danger" },
};

function PluginCard({ plugin, onView }: { plugin: PluginInfo; onView: (v: PluginsView) => void }) {
  const { notify } = useArc();
  const call = async (fn: () => Promise<PluginsView>) => {
    try {
      onView(await fn());
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };
  const toggleModule = (module: string, on: boolean) => {
    const modules = on ? [...plugin.granted, module] : plugin.granted.filter((m) => m !== module);
    void call(() => put<PluginsView>(`/api/plugins/${plugin.id}/grants`, { modules }));
  };
  const trust = TRUST[plugin.trust];
  return (
    <li className="doc-job" data-testid={`plugin-${plugin.id}`}>
      <div className="doc-job__head">
        <Toggle checked={plugin.enabled} disabled={Boolean(plugin.blocked)} testId={`plugin-enable-${plugin.id}`}
                onChange={(v) => void call(() => post<PluginsView>(`/api/plugins/${plugin.id}/enable`, { enabled: v }))}
                label={<><b>{plugin.name}</b> <span className="dim">{plugin.version}{plugin.author && ` · ${plugin.author}`}</span></>}
                hint={plugin.description} />
        <span className={`tag tag--${trust.tone}`} title={plugin.key_id ? `ключ ${plugin.key_id}` : undefined}>
          {trust.label}{plugin.signer && `: ${plugin.signer}`}
        </span>
        <button className="btn btn--sm btn--ghost" onClick={() => void call(() => del<PluginsView>(`/api/plugins/${plugin.id}`))}>
          Удалить
        </button>
      </div>
      {plugin.blocked && <div className="danger-text">{plugin.blocked}</div>}
      <div className="faint">Разрешения, которые запрашивает модуль (каждое включается отдельно):</div>
      <div className="modules">
        {plugin.permissions.map((m) => (
          <Toggle key={m} checked={plugin.granted.includes(m)} onChange={(v) => toggleModule(m, v)}
                  label={MODULE_LABEL[m] ?? m} testId={`grant-${plugin.id}-${m}`} />
        ))}
      </div>
      <details>
        <summary className="dim">Команды ({plugin.commands.length})</summary>
        <ul className="plugin-commands">
          {plugin.commands.map((c, i) => (
            <li key={i}>
              «{c.phrases.join("», «")}» → <code>{c.actions.join(", ")}</code>
            </li>
          ))}
        </ul>
      </details>
    </li>
  );
}

export function Plugins() {
  const { notify, updateSettings } = useArc();
  const [view, setView] = useState<PluginsView | null>(null);
  const [keyName, setKeyName] = useState("");
  const [keyValue, setKeyValue] = useState("");
  const [askUnsigned, setAskUnsigned] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setView(await get<PluginsView>("/api/plugins"));
    } catch {
      /* backend banner */
    }
  }, []);
  useEffect(() => void refresh(), [refresh]);

  const install = async () => {
    const path = await window.arc?.pickFile("plugin");
    if (!path) return;
    try {
      const result = await post<PluginsView>("/api/plugins/import", { path });
      setView(result);
      notify("ok", "Модуль установлен. Он выключен: проверьте разрешения и включите его.");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };

  const addKey = async () => {
    try {
      setView(await post<PluginsView>("/api/plugins/keys", { name: keyName.trim(), public_key: keyValue.trim() }));
      setKeyName("");
      setKeyValue("");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };

  const setUnsigned = async (allow: boolean) => {
    setAskUnsigned(false);
    await updateSettings({ plugins: { allow_unsigned: allow } });
    void refresh();
  };

  return (
    <div className="screen" data-testid="plugins-screen">
      <div className="page-title">
        <h1>Модули</h1>
        <span className="dim">Дополнительные голосовые команды от других авторов</span>
      </div>
      <Panel title="Установленные" tag={view ? String(view.plugins.length) : "…"}>
        <p className="faint">
          Модуль — это описание фраз и действий из каталога A.R.C., а не программа: он не может выполнять код,
          выключать компьютер, менять режим LOCAL/ONLINE или разрешения. Встроенные команды важнее команд модулей.
          Опасные действия (категория B) по-прежнему требуют вашего подтверждения.
        </p>
        <div className="btn-row" style={{ marginBottom: 10 }}>
          <button className="btn btn--primary" onClick={() => void install()} data-testid="plugin-install">Установить модуль…</button>
        </div>
        {view?.errors.map((e) => <div key={e} className="danger-text">{e}</div>)}
        {!view?.plugins.length ? (
          <div className="empty">Модулей нет</div>
        ) : (
          <ul className="doc-jobs">{view.plugins.map((p) => <PluginCard key={p.id} plugin={p} onView={setView} />)}</ul>
        )}
      </Panel>
      <div className="grid-2">
        <Panel title="Доверенные ключи авторов">
          <p className="faint">Модуль устанавливается, только если он подписан ключом из этого списка.
            Публичный ключ автор публикует вместе с модулем — сверяйте его с источником.</p>
          {view?.trusted_keys.length ? (
            <table className="table">
              <tbody>
                {view.trusted_keys.map((k) => (
                  <tr key={k.id}>
                    <td>{k.name}</td>
                    <td className="dim selectable">{k.id}</td>
                    <td>
                      <button className="btn btn--sm btn--ghost"
                              onClick={async () => setView(await del<PluginsView>(`/api/plugins/keys/${k.id}`))}>Удалить</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="empty">Нет доверенных ключей</div>}
          <div className="form-grid" style={{ marginTop: 10 }}>
            <Field label="Автор">
              <input className="input" value={keyName} maxLength={80} onChange={(e) => setKeyName(e.target.value)}
                     data-testid="key-name" />
            </Field>
            <Field label="Публичный ключ (Ed25519, base64)">
              <input className="input" value={keyValue} maxLength={64} onChange={(e) => setKeyValue(e.target.value)}
                     data-testid="key-value" />
            </Field>
          </div>
          <button className="btn" disabled={!keyName.trim() || keyValue.trim().length < 40} onClick={() => void addKey()}
                  data-testid="key-add">Доверять ключу</button>
        </Panel>
        <Panel title="Неподписанные модули" tag={view?.allow_unsigned ? "разрешены" : "запрещены"}>
          <Toggle checked={Boolean(view?.allow_unsigned)} testId="allow-unsigned"
                  onChange={(v) => (v ? setAskUnsigned(true) : void setUnsigned(false))}
                  label="Разрешить неподписанные модули"
                  hint="Только для своих модулей во время разработки. Подлинность таких файлов не проверяется." />
        </Panel>
      </div>
      {askUnsigned && (
        <Dialog title="Разрешить неподписанные модули?" alert onClose={() => setAskUnsigned(false)}
                footer={<>
                  <button className="btn btn--ghost" onClick={() => setAskUnsigned(false)}>Отмена</button>
                  <button className="btn btn--solid btn--danger" onClick={() => void setUnsigned(true)}
                          data-testid="allow-unsigned-confirm">Разрешить</button>
                </>}>
          Неподписанный модуль мог быть изменён кем угодно. Он всё равно ограничен каталогом действий и выданными
          разрешениями, но устанавливайте только файлы, которые сделали сами.
        </Dialog>
      )}
    </div>
  );
}
