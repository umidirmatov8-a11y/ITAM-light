import { useState } from "react";

import { NavRail, Screen, TitleBar } from "./components/Chrome";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { Toasts } from "./components/ui";
import { ArcProvider, useArc } from "./lib/store";
import { Apps } from "./screens/Apps";
import { Compact } from "./screens/Compact";
import { Diagnostics } from "./screens/Diagnostics";
import { Home } from "./screens/Home";
import { Log } from "./screens/Log";
import { Permissions } from "./screens/Permissions";
import { Scenarios } from "./screens/Scenarios";
import { Settings } from "./screens/Settings";

function BackendBanner() {
  const { backend } = useArc();
  if (backend.state === "ready") return null;
  const failed = backend.state === "failed";
  return (
    <div className={`banner ${failed ? "banner--danger" : ""}`} role="status" data-testid="backend-banner">
      <span className={`led ${failed ? "led--danger" : "led--busy"}`} />
      <span className="selectable">{backend.message || "Подключение к ядру…"}</span>
      {failed && (
        <button className="btn btn--sm" onClick={() => void window.arc?.restartBackend()}>Перезапустить ядро</button>
      )}
    </div>
  );
}

function Shell() {
  const { backend, state } = useArc();
  const [screen, setScreen] = useState<Screen>("home");
  const pending = state?.pending_confirmation ?? null;
  return (
    <div className="app" data-testid="arc-root" data-backend={backend.state}>
      <TitleBar />
      <div className="body">
        <NavRail screen={screen} onChange={setScreen} />
        <main className="content">
          <BackendBanner />
          {screen === "home" && <Home />}
          {screen === "apps" && <Apps />}
          {screen === "scenarios" && <Scenarios />}
          {screen === "log" && <Log />}
          {screen === "permissions" && <Permissions />}
          {screen === "settings" && <Settings />}
          {screen === "diagnostics" && <Diagnostics />}
        </main>
      </div>
      {pending && <ConfirmDialog key={pending.id} info={pending} />}
      <Toasts />
    </div>
  );
}

function CompactShell() {
  const { backend } = useArc();
  return (
    <div data-testid="arc-root" data-backend={backend.state} style={{ height: "100%" }}>
      <Compact />
    </div>
  );
}

export function App({ compact = false }: { compact?: boolean }) {
  return <ArcProvider>{compact ? <CompactShell /> : <Shell />}</ArcProvider>;
}
