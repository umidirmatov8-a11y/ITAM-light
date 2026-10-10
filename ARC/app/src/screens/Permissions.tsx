import { useEffect, useState } from "react";

import { IconFolder, IconStop, IconTrash } from "../components/Icons";
import { Field, Panel, RiskBadge, Toggle } from "../components/ui";
import { get } from "../lib/api";
import { useArc } from "../lib/store";
import type { ActionSpecView } from "../lib/types";

export const MODULE_LABEL: Record<string, string> = {
  apps: "Запуск приложений",
  volume: "Громкость и звук",
  windows: "Управление окнами",
  system_info: "Системная информация",
  files: "Файлы и папки",
  processes: "Завершение процессов",
  power: "Питание (выключение, перезагрузка)",
  browser: "Открытие сайтов",
  web_search: "Поиск в интернете",
  scenarios: "Сценарии",
  modes: "Режимы (LOCAL/ONLINE, тишина)",
};

export function Permissions() {
  const { settings, updateSettings, state, setEmergency, notify } = useArc();
  const [actions, setActions] = useState<ActionSpecView[]>([]);

  useEffect(() => {
    get<ActionSpecView[]>("/api/actions").then(setActions).catch((err) => notify("error", String(err.message ?? err)));
  }, [notify]);

  if (!settings) return <div className="empty">Ожидание ядра…</div>;
  const safety = settings.safety;

  const addDir = async () => {
    const dir = await window.arc?.pickFile("folder");
    if (!dir || safety.allowed_dirs.includes(dir)) return;
    await updateSettings({ safety: { allowed_dirs: [...safety.allowed_dirs, dir] } });
  };
  const removeDir = (dir: string) => updateSettings({ safety: { allowed_dirs: safety.allowed_dirs.filter((d) => d !== dir) } });
  const estop = state?.emergency_stop ?? false;

  return (
    <div className="screen">
      <div className="page-title">
        <h1>Разрешения</h1>
        <span className="dim">Что A.R.C. может делать, в каких каталогах и с каким подтверждением</span>
      </div>
      <div className="grid-2">
        <Panel title="Аварийная остановка" alert={estop}>
          <p className="dim">
            Мгновенно блокирует все действия автоматизации и сбрасывает ожидающие подтверждения.
            Горячая клавиша: <b>Ctrl+Alt+End</b> (работает, даже когда окно скрыто).
          </p>
          <button className={`btn btn--danger ${estop ? "btn--solid" : ""}`} onClick={() => void setEmergency(!estop)}>
            <IconStop size={16} /> {estop ? "Снять аварийную остановку" : "Остановить автоматизацию"}
          </button>
        </Panel>
        <Panel title="Режим безопасности">
          <Toggle checked={safety.dry_run} onChange={(v) => void updateSettings({ safety: { dry_run: v } })}
                  testId="toggle-dry-run" label="Тестовый режим (имитация операций B и C)"
                  hint="Создание папок, завершение процессов, выключение — только записываются в журнал" />
          <div className="form-grid" style={{ marginTop: 8 }}>
            <Field label="Время на подтверждение, с">
              <input className="input" type="number" min={10} max={600} value={safety.confirmation_ttl_s}
                     onChange={(e) => void updateSettings({ safety: { confirmation_ttl_s: Number(e.target.value) } })} />
            </Field>
            <Field label="Тайм-аут операции, с">
              <input className="input" type="number" min={1} max={300} value={safety.action_timeout_s}
                     onChange={(e) => void updateSettings({ safety: { action_timeout_s: Number(e.target.value) } })} />
            </Field>
          </div>
        </Panel>
      </div>
      <div className="grid-2">
        <Panel title="Модули">
          <div className="modules">
            {Object.entries(MODULE_LABEL).map(([key, label]) => (
              <Toggle key={key} checked={safety.modules[key] ?? false} label={label}
                      onChange={(v) => void updateSettings({ safety: { modules: { ...safety.modules, [key]: v } } })} />
            ))}
          </div>
        </Panel>
        <Panel title="Разрешённые каталоги" tag={`${safety.allowed_dirs.length}`}>
          <p className="dim">Поиск, открытие файлов и создание папок возможны только внутри этих каталогов.</p>
          {safety.allowed_dirs.length === 0 ? (
            <div className="empty">Файловые операции отключены: каталоги не заданы</div>
          ) : (
            <ul className="dir-list">
              {safety.allowed_dirs.map((dir) => (
                <li key={dir}>
                  <IconFolder size={16} />
                  <span className="cell-path" title={dir}>{dir}</span>
                  <button className="btn btn--sm btn--danger" onClick={() => void removeDir(dir)} title="Убрать">
                    <IconTrash size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button className="btn btn--sm" onClick={() => void addDir()}><IconFolder size={14} /> Добавить каталог</button>
        </Panel>
      </div>
      <Panel title="Каталог операций" tag={`${actions.length}`}>
        <p className="dim">
          A.R.C. выполняет только эти операции с проверенными параметрами. Произвольные команды оболочки, сформированные
          речью, документами или языковой моделью, не выполняются.
        </p>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Риск</th><th>Операция</th><th>Код</th><th>Модуль</th><th>Жестом</th><th>Нужен ONLINE</th></tr></thead>
            <tbody>
              {actions.map((a) => (
                <tr key={a.name}>
                  <td><RiskBadge risk={a.risk} /></td>
                  <td>{a.title}</td>
                  <td><code className="dim">{a.name}</code></td>
                  <td className={safety.modules[a.module] ? "" : "danger-text"}>
                    {MODULE_LABEL[a.module] ?? a.module}{safety.modules[a.module] ? "" : " (выкл.)"}
                  </td>
                  <td>{a.gesture_allowed && a.risk === "A" ? "да" : "нет"}</td>
                  <td>{a.requires_online ? "да" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
