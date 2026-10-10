import { ReactNode, useEffect } from "react";

import { useArc } from "../lib/store";

export function Panel({ title, tag, children, className = "", alert = false, testId }: {
  title?: string;
  tag?: ReactNode;
  children: ReactNode;
  className?: string;
  alert?: boolean;
  testId?: string;
}) {
  return (
    <section className={`panel ${alert ? "panel--alert" : ""} ${className}`} data-testid={testId}>
      {title && (
        <header className="panel__head">
          <h2>{title}</h2>
          {tag && <span className="tag">{tag}</span>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Toggle({ checked, onChange, label, hint, disabled, testId }: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
  testId?: string;
}) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} disabled={disabled} data-testid={testId}
             onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle__track" />
      <span className="toggle__text">
        <span>{label}</span>
        {hint && <small>{hint}</small>}
      </span>
    </label>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

export function Dialog({ title, children, onClose, wide, footer, alert }: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  footer?: ReactNode;
  alert?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`dialog ${wide ? "dialog--wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <Panel title={title} alert={alert}>
          {children}
          {footer && <div className="dialog__foot">{footer}</div>}
        </Panel>
      </div>
    </div>
  );
}

export function Toasts() {
  const { toasts, dismissToast } = useArc();
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast--${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
          <span>{t.text}</span>
          <button onClick={() => dismissToast(t.id)} aria-label="Закрыть">×</button>
        </div>
      ))}
    </div>
  );
}

export function RiskBadge({ risk }: { risk: string | null | undefined }) {
  if (!risk || !["A", "B", "C"].includes(risk)) return <span className="faint">—</span>;
  const title = { A: "A — безопасное", B: "B — изменяет состояние", C: "C — критическое" }[risk];
  return <span className={`risk risk--${risk}`} title={title}>{risk}</span>;
}

export function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDateTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export const STATUS_LABEL: Record<string, string> = {
  done: "выполнено",
  dry_run: "тест",
  needs_confirmation: "подтвердить",
  clarify: "уточнение",
  denied: "запрещено",
  not_found: "не найдено",
  unknown: "не понято",
  unavailable: "недоступно",
  cancelled: "отменено",
  ignored: "пропущено",
  error: "ошибка",
  reply: "ответ",
  pending: "ожидает",
};

export function statusTone(status: string): "ok" | "warn" | "danger" | "accent" | "" {
  if (status === "done" || status === "reply") return "ok";
  if (status === "dry_run" || status === "needs_confirmation" || status === "clarify" || status === "pending") return "warn";
  if (status === "denied" || status === "error") return "danger";
  if (status === "not_found" || status === "unknown" || status === "unavailable") return "accent";
  return "";
}
