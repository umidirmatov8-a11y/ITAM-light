import { useEffect, useState } from "react";

import { useArc } from "../lib/store";
import type { ConfirmationInfo } from "../lib/types";
import { Dialog, RiskBadge } from "./ui";

/** Confirmation for category B/C actions. Category C needs an explicit acknowledgement. */
export function ConfirmDialog({ info }: { info: ConfirmationInfo }) {
  const { confirm } = useArc();
  const [ack, setAck] = useState(false);
  const [now, setNow] = useState(Date.now() / 1000);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setAck(false);
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 500);
    return () => window.clearInterval(timer);
  }, [info.id]);

  const left = Math.max(0, Math.round(info.expires_at - now));
  const critical = info.risk === "C";
  const run = async (approve: boolean) => {
    setBusy(true);
    try {
      await confirm(info.id, approve, ack);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog title={critical ? "Критическое действие" : "Подтверждение действия"} alert={critical}
            onClose={() => void run(false)}
            footer={
              <>
                <button className="btn btn--ghost" onClick={() => void run(false)} disabled={busy}>Отмена</button>
                <button className={`btn btn--solid ${critical ? "btn--danger" : ""}`} data-testid="confirm-approve"
                        onClick={() => void run(true)} disabled={busy || left === 0 || (critical && !ack)}>
                  Подтвердить
                </button>
              </>
            }>
      <div className="confirm">
        <div className="confirm__row">
          <RiskBadge risk={info.risk} />
          <div>
            <div className="confirm__title">{info.title}</div>
            <div className="confirm__desc selectable">{info.description}</div>
          </div>
        </div>
        <p className="dim">
          {critical
            ? "Категория C: критическая операция. Голосом и жестами её подтвердить нельзя."
            : "Категория B: действие изменяет состояние системы. Можно подтвердить здесь или голосом («да»)."}
        </p>
        {critical && (
          <label className="toggle">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} data-testid="confirm-ack" />
            <span className="toggle__track" />
            <span>Я понимаю последствия: {info.description}</span>
          </label>
        )}
        <div className={`confirm__timer ${left <= 10 ? "danger-text" : "faint"}`}>
          {left > 0 ? `Запрос действителен ещё ${left} с` : "Время подтверждения истекло"}
        </div>
      </div>
    </Dialog>
  );
}
