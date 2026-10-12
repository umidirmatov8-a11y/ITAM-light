import { useMemo, useState } from "react";

import { IconEdit, IconFolder, IconPin, IconPlay, IconPlus, IconSearch, IconTrash } from "../components/Icons";
import { Dialog, Field, formatDateTime, Panel, Toggle } from "../components/ui";
import { ApiError, del, post, put } from "../lib/api";
import { useArc } from "../lib/store";
import type { AppEntry, AppKind, LaunchType } from "../lib/types";

const KIND_LABEL: Record<AppKind, string> = { app: "Программа", game: "Игра", system: "Система" };
const TYPE_LABEL: Record<LaunchType, string> = { exe: "EXE", lnk: "Ярлык", uwp: "UWP", protocol: "Протокол" };
const SOURCE_LABEL: Record<string, string> = {
  manual: "вручную",
  builtin: "встроено",
  start_menu: "меню «Пуск»",
  steam: "Steam",
  epic: "Epic",
  uwp: "Store",
};

interface Draft {
  name: string;
  kind: AppKind;
  category: string;
  launch_type: LaunchType;
  target: string;
  args: string;
  working_dir: string;
  aliases: string;
  process_name: string;
  run_as_admin: boolean;
  enabled: boolean;
  pinned: boolean;
}

const EMPTY: Draft = {
  name: "",
  kind: "app",
  category: "",
  launch_type: "exe",
  target: "",
  args: "",
  working_dir: "",
  aliases: "",
  process_name: "",
  run_as_admin: false,
  enabled: true,
  pinned: false,
};

/** Splits a command line into arguments, honouring double quotes (as Windows does). */
export function splitArgs(line: string): string[] {
  const out: string[] = [];
  let current = "";
  let quoted = false;
  let started = false;
  for (const ch of line) {
    if (ch === '"') {
      quoted = !quoted;
      started = true;
    } else if (/\s/.test(ch) && !quoted) {
      if (started) out.push(current);
      current = "";
      started = false;
    } else {
      current += ch;
      started = true;
    }
  }
  if (started) out.push(current);
  return out;
}

export function joinArgs(args: string[]): string {
  return args.map((a) => (/\s/.test(a) || a === "" ? `"${a}"` : a)).join(" ");
}

function toDraft(app: AppEntry): Draft {
  return {
    name: app.name,
    kind: app.kind,
    category: app.category,
    launch_type: app.launch_type,
    target: app.target,
    args: joinArgs(app.args),
    working_dir: app.working_dir,
    aliases: app.aliases.join(", "),
    process_name: app.process_name,
    run_as_admin: app.run_as_admin,
    enabled: app.enabled,
    pinned: app.pinned,
  };
}

function toPayload(d: Draft) {
  return {
    name: d.name.trim(),
    kind: d.kind,
    category: d.category.trim(),
    launch_type: d.launch_type,
    target: d.target.trim(),
    args: splitArgs(d.args),
    working_dir: d.working_dir.trim(),
    aliases: d.aliases.split(",").map((a) => a.trim()).filter(Boolean),
    process_name: d.process_name.trim(),
    run_as_admin: d.run_as_admin,
    enabled: d.enabled,
    pinned: d.pinned,
  };
}

function AppEditor({ app, onClose }: { app: AppEntry | null; onClose: () => void }) {
  const { refreshApps, notify } = useArc();
  const [draft, setDraft] = useState<Draft>(app ? toDraft(app) : EMPTY);
  const [error, setError] = useState("");
  const [untrusted, setUntrusted] = useState("");
  const [saving, setSaving] = useState(false);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const browse = async () => {
    const file = await window.arc?.pickFile("exe");
    if (!file) return;
    const lower = file.toLowerCase();
    const name = file.split(/[\\/]/).pop()!.replace(/\.(exe|lnk)$/i, "");
    setDraft((d) => ({
      ...d,
      target: file,
      launch_type: lower.endsWith(".lnk") ? "lnk" : "exe",
      name: d.name || name,
      process_name: lower.endsWith(".exe") ? file.split(/[\\/]/).pop()! : d.process_name,
    }));
  };

  const save = async (confirmUntrusted = false) => {
    setSaving(true);
    setError("");
    try {
      const payload = toPayload(draft);
      if (app) await put(`/api/apps/${app.id}`, payload);
      else await post("/api/apps", { ...payload, confirm_untrusted: confirmUntrusted });
      notify("ok", app ? `«${payload.name}» сохранено` : `«${payload.name}» добавлено в реестр`);
      await refreshApps();
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.code === "untrusted_location") setUntrusted(err.message);
      else setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const targetHint: Record<LaunchType, string> = {
    exe: "Полный путь к .exe, например C:\\Program Files\\Telegram Desktop\\Telegram.exe",
    lnk: "Полный путь к ярлыку .lnk",
    uwp: "AppUserModelID, например Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
    protocol: "steam://rungameid/1091500, com.epicgames.launcher://…, ms-settings: …",
  };

  return (
    <Dialog title={app ? `Редактирование: ${app.name}` : "Новое приложение"} onClose={onClose} wide
            footer={
              <>
                <button className="btn btn--ghost" onClick={onClose}>Отмена</button>
                <button className="btn btn--solid" onClick={() => void save()} disabled={saving || !draft.name || !draft.target}
                        data-testid="app-save">Сохранить</button>
              </>
            }>
      {untrusted ? (
        <div className="banner">
          <span>{untrusted}</span>
          <button className="btn btn--sm" onClick={() => void save(true)}>Добавить всё равно</button>
          <button className="btn btn--sm btn--ghost" onClick={() => setUntrusted("")}>Назад</button>
        </div>
      ) : null}
      {error && <div className="banner banner--danger">{error}</div>}
      <div className="form-grid">
        <Field label="Название">
          <input className="input" value={draft.name} onChange={(e) => set("name", e.target.value)} maxLength={120}
                 data-testid="app-name" />
        </Field>
        <Field label="Тип записи">
          <select className="select" value={draft.kind} onChange={(e) => set("kind", e.target.value as AppKind)}>
            {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Категория">
          <input className="input" value={draft.category} onChange={(e) => set("category", e.target.value)} maxLength={60}
                 placeholder="Работа, Игры, Мессенджеры…" />
        </Field>
        <Field label="Способ запуска">
          <select className="select" value={draft.launch_type}
                  onChange={(e) => set("launch_type", e.target.value as LaunchType)}>
            {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
      </div>
      <div className="field-row">
        <Field label="Цель запуска" hint={targetHint[draft.launch_type]}>
          <div className="input-with-btn">
            <input className="input" value={draft.target} onChange={(e) => set("target", e.target.value)}
                   data-testid="app-target" />
            {(draft.launch_type === "exe" || draft.launch_type === "lnk") && (
              <button className="btn" type="button" onClick={() => void browse()}><IconFolder size={16} /> Обзор</button>
            )}
          </div>
        </Field>
      </div>
      <div className="form-grid">
        <Field label="Голосовые псевдонимы" hint="Через запятую: телега, телеграм">
          <input className="input" value={draft.aliases} onChange={(e) => set("aliases", e.target.value)} />
        </Field>
        <Field label="Аргументы" hint='Например: --profile "Work"'>
          <input className="input" value={draft.args} onChange={(e) => set("args", e.target.value)}
                 disabled={draft.launch_type !== "exe"} />
        </Field>
        <Field label="Рабочий каталог">
          <input className="input" value={draft.working_dir} onChange={(e) => set("working_dir", e.target.value)}
                 disabled={draft.launch_type !== "exe"} />
        </Field>
        <Field label="Имя процесса" hint="Для статуса «уже запущено» и закрытия, например Telegram.exe">
          <input className="input" value={draft.process_name} onChange={(e) => set("process_name", e.target.value)} />
        </Field>
      </div>
      <div className="btn-row" style={{ gap: 24, marginTop: 8 }}>
        <Toggle checked={draft.enabled} onChange={(v) => set("enabled", v)} label="Разрешено запускать" />
        <Toggle checked={draft.pinned} onChange={(v) => set("pinned", v)} label="Быстрый запуск на пульте" />
        <Toggle checked={draft.run_as_admin} onChange={(v) => set("run_as_admin", v)} disabled={draft.launch_type !== "exe"}
                label="От имени администратора" hint="Категория C: каждый запуск подтверждается и вызывает UAC" />
      </div>
    </Dialog>
  );
}

export function Apps() {
  const { apps, refreshApps, launchApp, notify } = useArc();
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | AppKind>("all");
  const [category, setCategory] = useState("all");
  const [editing, setEditing] = useState<AppEntry | null | "new">(null);
  const [removing, setRemoving] = useState<AppEntry | null>(null);
  const [discovering, setDiscovering] = useState(false);

  const categories = useMemo(() => Array.from(new Set(apps.map((a) => a.category).filter(Boolean))).sort(), [apps]);
  const filtered = apps.filter((a) => {
    const q = query.trim().toLowerCase();
    const matches = !q || a.name.toLowerCase().includes(q) || a.aliases.some((x) => x.toLowerCase().includes(q));
    return matches && (kind === "all" || a.kind === kind) && (category === "all" || a.category === category);
  });

  const discover = async () => {
    setDiscovering(true);
    try {
      const report = await post<{ added: string[]; skipped: number; by_source: Record<string, number>; errors: string[] }>(
        "/api/apps/discover",
      );
      const sources = Object.entries(report.by_source).map(([k, v]) => `${SOURCE_LABEL[k] ?? k}: ${v}`).join(", ");
      notify("ok", report.added.length ? `Добавлено ${report.added.length} (${sources})` : "Новых программ не найдено");
      await refreshApps();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    } finally {
      setDiscovering(false);
    }
  };

  const patch = async (app: AppEntry, change: Partial<AppEntry>) => {
    try {
      await put(`/api/apps/${app.id}`, change);
      await refreshApps();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async () => {
    if (!removing) return;
    try {
      await del(`/api/apps/${removing.id}`);
      notify("ok", `«${removing.name}» удалено из реестра A.R.C. (программа не удалена)`);
      await refreshApps();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : String(err));
    }
    setRemoving(null);
  };

  return (
    <div className="screen">
      <div className="page-title">
        <h1>Приложения</h1>
        <span className="dim">Реестр программ и игр, которые A.R.C. может запускать по команде</span>
      </div>
      <Panel>
        <div className="toolbar">
          <div className="input-with-icon">
            <IconSearch size={16} />
            <input className="input" placeholder="Поиск по названию и псевдонимам" value={query}
                   onChange={(e) => setQuery(e.target.value)} />
          </div>
          <select className="select toolbar__select" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
            <option value="all">Все типы</option>
            {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="select toolbar__select" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="all">Все категории</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <span className="toolbar__spacer" />
          <button className="btn" onClick={() => void discover()} disabled={discovering} data-testid="apps-discover">
            <IconSearch size={16} /> {discovering ? "Поиск…" : "Найти установленные"}
          </button>
          <button className="btn btn--solid" onClick={() => setEditing("new")} data-testid="apps-add">
            <IconPlus size={16} /> Добавить
          </button>
        </div>
        {filtered.length === 0 ? (
          <div className="empty">{apps.length ? "Ничего не найдено" : "Реестр пуст. Нажмите «Найти установленные»."}</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Тип</th>
                  <th>Запуск</th>
                  <th>Псевдонимы</th>
                  <th>Источник</th>
                  <th>Последний запуск</th>
                  <th title="Разрешено">Вкл.</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtered.map((app) => (
                  <tr key={app.id} className={app.enabled ? "" : "row--disabled"}>
                    <td>
                      <div className="app-cell">
                        <b>{app.name}</b>
                        {app.run_as_admin && <span className="tag tag--danger">admin</span>}
                        {app.category && <span className="faint">{app.category}</span>}
                      </div>
                    </td>
                    <td>{KIND_LABEL[app.kind]}</td>
                    <td>
                      <span className="tag">{TYPE_LABEL[app.launch_type]}</span>
                      <div className="cell-path" title={app.target}>{app.target}</div>
                    </td>
                    <td className="dim">{app.aliases.join(", ") || "—"}</td>
                    <td className="faint">{SOURCE_LABEL[app.source] ?? app.source}</td>
                    <td className="faint">{app.last_launched ? formatDateTime(app.last_launched) : "—"}</td>
                    <td>
                      <Toggle checked={app.enabled} onChange={(v) => void patch(app, { enabled: v })}
                              label={<span className="sr-only">Разрешено</span>} />
                    </td>
                    <td>
                      <div className="row-actions">
                        <button className="btn btn--sm" onClick={() => void launchApp(app.id)} disabled={!app.enabled}
                                title="Запустить"><IconPlay size={14} /></button>
                        <button className={`btn btn--sm ${app.pinned ? "btn--solid" : ""}`} title="Быстрый запуск"
                                onClick={() => void patch(app, { pinned: !app.pinned })}><IconPin size={14} /></button>
                        <button className="btn btn--sm" onClick={() => setEditing(app)} title="Изменить">
                          <IconEdit size={14} />
                        </button>
                        <button className="btn btn--sm btn--danger" onClick={() => setRemoving(app)}
                                title="Удалить из реестра"><IconTrash size={14} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {editing && <AppEditor app={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {removing && (
        <Dialog title="Удалить из реестра" onClose={() => setRemoving(null)}
                footer={
                  <>
                    <button className="btn btn--ghost" onClick={() => setRemoving(null)}>Отмена</button>
                    <button className="btn btn--danger btn--solid" onClick={() => void remove()}>Удалить запись</button>
                  </>
                }>
          <p>
            Запись «{removing.name}» будет удалена из реестра A.R.C. Сама программа и её файлы <b>не удаляются</b>.
          </p>
        </Dialog>
      )}
    </div>
  );
}
