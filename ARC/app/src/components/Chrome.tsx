import type { ReactNode } from "react";

import { useArc } from "../lib/store";
import {
  IconApps,
  IconClose,
  IconCompact,
  IconDiag,
  IconHome,
  IconLog,
  IconMaximize,
  IconMinimize,
  IconScenario,
  IconSettings,
  IconShield,
} from "./Icons";

export type Screen = "home" | "apps" | "scenarios" | "log" | "permissions" | "settings" | "diagnostics";

const NAV: Array<{ id: Screen; label: string; icon: ReactNode }> = [
  { id: "home", label: "Пульт", icon: <IconHome /> },
  { id: "apps", label: "Прилож.", icon: <IconApps /> },
  { id: "scenarios", label: "Сценарии", icon: <IconScenario /> },
  { id: "log", label: "Журнал", icon: <IconLog /> },
  { id: "permissions", label: "Доступ", icon: <IconShield /> },
  { id: "settings", label: "Настр.", icon: <IconSettings /> },
  { id: "diagnostics", label: "Диагн.", icon: <IconDiag /> },
];

export function NavRail({ screen, onChange }: { screen: Screen; onChange: (s: Screen) => void }) {
  return (
    <nav className="rail" aria-label="Разделы">
      {NAV.map((item) => (
        <button key={item.id} aria-current={screen === item.id ? "page" : undefined} onClick={() => onChange(item.id)}
                title={item.label} data-testid={`nav-${item.id}`}>
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  );
}

export function TitleBar() {
  const { backend, state } = useArc();
  const win = (action: "minimize" | "maximize" | "close" | "compact") => window.arc?.window(action);
  const backendTone = backend.state === "ready" ? "ok" : backend.state === "failed" ? "danger" : "busy";
  return (
    <header className="titlebar">
      <div className="titlebar__brand">
        <b>A.R.C.</b>
        <span className="mono-label">Adaptive Responsive Computer</span>
      </div>
      <div className="titlebar__status">
        {state?.emergency_stop && <span className="tag tag--danger">E-STOP</span>}
        {state?.dry_run && <span className="tag tag--warn" title="Операции B/C имитируются">Тестовый режим</span>}
        {state?.simulated && <span className="tag tag--warn" title="Системные действия не выполняются">Имитация</span>}
        {state && (
          <span className={`tag ${state.mode === "ONLINE" ? "tag--accent" : "tag--ok"}`} data-testid="mode-indicator">
            {state.mode}
          </span>
        )}
        <span className="tag" title={backend.message}>
          <span className={`led led--${backendTone}`} /> ядро
        </span>
      </div>
      <div className="titlebar__buttons">
        <button onClick={() => win("compact")} title="Компактный виджет" aria-label="Компактный виджет"><IconCompact size={16} /></button>
        <button onClick={() => win("minimize")} title="Свернуть" aria-label="Свернуть"><IconMinimize size={16} /></button>
        <button onClick={() => win("maximize")} title="Развернуть" aria-label="Развернуть"><IconMaximize size={14} /></button>
        <button className="close" onClick={() => win("close")} title="Скрыть в трей" aria-label="Скрыть в трей"><IconClose size={16} /></button>
      </div>
    </header>
  );
}
