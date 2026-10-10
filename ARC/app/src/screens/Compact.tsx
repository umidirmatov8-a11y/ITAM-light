import { FormEvent, useState } from "react";

import { ArcCore } from "../components/ArcCore";
import { IconExpand, IconSend, IconStop } from "../components/Icons";
import { useArc } from "../lib/store";

/** Floating always-on-top widget: status, last answer, text command. */
export function Compact() {
  const { state, backend, busy, conversation, sendCommand, setEmergency } = useArc();
  const [text, setText] = useState("");
  const last = conversation[conversation.length - 1] ?? state?.last_response ?? null;
  const core = backend.state !== "ready" ? "offline" : state?.emergency_stop ? "alert" : busy ? "busy" : "idle";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    setText("");
    await sendCommand(value);
  };

  return (
    <div className="compact" data-testid="compact">
      <ArcCore state={core} mode={state?.mode ?? "LOCAL"} label="" />
      <div className="compact__main">
        <div className="compact__top">
          <span className={`tag ${state?.mode === "ONLINE" ? "tag--accent" : "tag--ok"}`}>{state?.mode ?? "…"}</span>
          {state?.emergency_stop && <span className="tag tag--danger">E-STOP</span>}
          <span style={{ flex: 1 }} />
          <button className="btn btn--sm btn--danger" title="Аварийная остановка"
                  onClick={() => void setEmergency(!state?.emergency_stop)}><IconStop size={14} /></button>
          <button className="btn btn--sm" title="Развернуть" onClick={() => window.arc?.window("expand")}>
            <IconExpand size={14} />
          </button>
        </div>
        <div className="compact__msg glow">{last?.message ?? "A.R.C. готов"}</div>
        <form onSubmit={submit}>
          <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Команда…"
                 disabled={backend.state !== "ready"} aria-label="Команда" />
          <button className="btn btn--sm btn--solid" type="submit" disabled={!text.trim()} aria-label="Выполнить">
            <IconSend size={14} />
          </button>
        </form>
      </div>
    </div>
  );
}
