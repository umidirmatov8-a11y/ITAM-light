import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from 'react';

// ---------- Уведомления ----------
type Toast = { id: number; text: string; kind: 'ok' | 'error' | 'info' };
const ToastCtx = createContext<(text: string, kind?: Toast['kind']) => void>(() => undefined);
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, kind: Toast['kind'] = 'ok') => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, text, kind }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), kind === 'error' ? 8000 : 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status">
        {items.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}

// ---------- Загрузка данных ----------
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const reload = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const d = await fn();
      if (my === seq.current) { setData(d); setError(null); }
    } catch (e: any) {
      if (my === seq.current) setError(e.message);
    } finally {
      if (my === seq.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}

/** Обёртка действия: блокировка кнопки + уведомление об ошибке. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = useCallback(async <T,>(fn: () => Promise<T>, okText?: string): Promise<T | undefined> => {
    setBusy(true);
    try {
      const r = await fn();
      if (okText) toast(okText, 'ok');
      return r;
    } catch (e: any) {
      toast(e.message, 'error');
      return undefined;
    } finally {
      setBusy(false);
    }
  }, [toast]);
  return { busy, run };
}

// ---------- Элементы ----------
export function Badge({ value, label }: { value?: string | null; label?: Record<string, string> | string }) {
  if (!value) return <span className="muted">—</span>;
  const text = typeof label === 'string' ? label : label?.[value] ?? value;
  return <span className={`badge ${value}`}>{text}</span>;
}

export function Modal({ title, onClose, children, footer, wide }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head"><h2>{title}</h2><button className="x" onClick={onClose} aria-label="Закрыть">×</button></div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Field({ label, required, hint, children, full }: { label: string; required?: boolean; hint?: string; children: ReactNode; full?: boolean }) {
  return (
    <div className={`field ${full ? 'full' : ''}`}>
      <label>{label}{required && <span className="req"> *</span>}</label>
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: Array<{ id: T; label: string; count?: number; hidden?: boolean }> }) {
  return (
    <div className="tabs" role="tablist">
      {items.filter((i) => !i.hidden).map((i) => (
        <button key={i.id} role="tab" aria-selected={value === i.id} className={value === i.id ? 'active' : ''} onClick={() => onChange(i.id)}>
          {i.label}{i.count !== undefined && <span className="cnt">{i.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Pager({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (o: number) => void }) {
  if (total <= limit) return <div className="pager muted small">Всего: {total}</div>;
  return (
    <div className="pager">
      <span className="muted small">{offset + 1}–{Math.min(offset + limit, total)} из {total}</span>
      <button className="btn small" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>‹ Назад</button>
      <button className="btn small" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Вперёд ›</button>
    </div>
  );
}

export function ErrorBox({ error }: { error?: string | null }) {
  return error ? <div className="alert error">{error}</div> : null;
}

export function Loading() {
  return <div className="empty">Загрузка…</div>;
}

export function PageHead({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-head">
      <div><h1>{title}</h1>{sub && <p>{sub}</p>}</div>
      {children && <div className="actions">{children}</div>}
    </div>
  );
}

export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function confirmAction(text: string): boolean {
  return window.confirm(text);
}
