import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError, get, post, put } from "./api";
import type {
  AiStatus,
  AppEntry,
  ArcState,
  BackendStatus,
  CommandResponse,
  HistoryItem,
  Settings,
  SystemStats,
  VoiceStatus,
} from "./types";

export interface Toast {
  id: number;
  kind: "info" | "error" | "ok";
  text: string;
}

export interface ArcContextValue {
  backend: BackendStatus;
  state: ArcState | null;
  settings: Settings | null;
  stats: SystemStats | null;
  ai: AiStatus | null;
  apps: AppEntry[];
  history: HistoryItem[];
  conversation: CommandResponse[];
  voice: VoiceStatus | null;
  voiceAction(action: "start" | "stop" | "toggle"): Promise<void>;
  setContinuous(enabled: boolean): Promise<void>;
  busy: boolean;
  toasts: Toast[];
  sendCommand(text: string): Promise<CommandResponse | null>;
  confirm(id: string, approve: boolean, acknowledge?: boolean): Promise<void>;
  undo(): Promise<void>;
  repeat(): Promise<void>;
  setEmergency(engaged: boolean): Promise<void>;
  launchApp(id: string): Promise<void>;
  updateSettings(patch: Record<string, Record<string, unknown>>): Promise<Settings | null>;
  refreshApps(): Promise<void>;
  refreshHistory(): Promise<void>;
  refreshAi(force?: boolean): Promise<void>;
  refreshState(): Promise<void>;
  notify(kind: Toast["kind"], text: string): void;
  dismissToast(id: number): void;
}

const ArcContext = createContext<ArcContextValue | null>(null);

export function useArc(): ArcContextValue {
  const value = useContext(ArcContext);
  if (!value) throw new Error("useArc outside ArcProvider");
  return value;
}

const INITIAL_BACKEND: BackendStatus = { state: "starting", message: "Подключение к ядру…", restarts: 0 };

export function applyUiSettings(ui: Settings["ui"]): void {
  const root = document.documentElement;
  root.dataset.theme = ui.theme;
  root.dataset.anim = ui.animations ? "on" : "off";
  root.dataset.scanlines = ui.scanlines ? "on" : "off";
}

export function ArcProvider({ children }: { children: ReactNode }) {
  const [backend, setBackend] = useState<BackendStatus>(INITIAL_BACKEND);
  const [state, setState] = useState<ArcState | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [ai, setAi] = useState<AiStatus | null>(null);
  const [apps, setApps] = useState<AppEntry[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [conversation, setConversation] = useState<CommandResponse[]>([]);
  const [voice, setVoice] = useState<VoiceStatus | null>(null);
  const lastTranscriptTs = useRef(0);
  const [busy, setBusy] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);
  const ready = backend.state === "ready";

  const notify = useCallback((kind: Toast["kind"], text: string) => {
    const id = ++toastId.current;
    setToasts((items) => [...items.slice(-3), { id, kind, text }]);
    window.setTimeout(() => setToasts((items) => items.filter((t) => t.id !== id)), kind === "error" ? 7000 : 4000);
  }, []);

  const dismissToast = useCallback((id: number) => setToasts((items) => items.filter((t) => t.id !== id)), []);

  const guard = useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T | null> => {
      try {
        return await fn();
      } catch (err) {
        notify("error", err instanceof ApiError || err instanceof Error ? err.message : String(err));
        return null;
      }
    },
    [notify],
  );

  // ---------------------------------------------------------------- backend status
  useEffect(() => {
    if (!window.arc) {
      setBackend({ state: "failed", message: "Нет моста preload: запустите приложение через Electron", restarts: 0 });
      return;
    }
    window.arc.backendStatus().then(setBackend).catch(() => undefined);
    const offStatus = window.arc.onBackendStatus(setBackend);
    const offEvent = window.arc.onEvent((event) => {
      if (event.type === "emergency-stop") notify("error", "Аварийная остановка активирована горячей клавишей");
      if (event.type === "voice-error") notify("error", String((event as { detail?: string }).detail ?? "Голос недоступен"));
    });
    return () => {
      offStatus();
      offEvent();
    };
  }, [notify]);

  // ---------------------------------------------------------------- loaders
  const refreshState = useCallback(async () => {
    try {
      setState(await get<ArcState>("/api/state"));
    } catch {
      /* status bar shows backend state */
    }
  }, []);
  const refreshApps = useCallback(async () => {
    const data = await guard(() => get<AppEntry[]>("/api/apps"));
    if (data) setApps(data);
  }, [guard]);
  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await get<HistoryItem[]>("/api/history?limit=30"));
    } catch {
      /* ignore */
    }
  }, []);
  const refreshAi = useCallback(async (force = false) => {
    try {
      setAi(await get<AiStatus>(force ? "/api/ai/status?force=true" : "/api/ai/status"));
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    void refreshState();
    void refreshApps();
    void refreshHistory();
    void refreshAi();
    get<Settings>("/api/settings")
      .then((s) => {
        setSettings(s);
        applyUiSettings(s.ui);
      })
      .catch(() => undefined);
    const stateTimer = window.setInterval(refreshState, 1500);
    const statsTimer = window.setInterval(async () => {
      if (document.visibilityState !== "visible") return;
      try {
        setStats(await get<SystemStats>("/api/system/stats"));
      } catch {
        /* ignore */
      }
    }, 2000);
    const aiTimer = window.setInterval(() => void refreshAi(), 20000);
    const historyTimer = window.setInterval(refreshHistory, 10000);
    return () => {
      window.clearInterval(stateTimer);
      window.clearInterval(statsTimer);
      window.clearInterval(aiTimer);
      window.clearInterval(historyTimer);
    };
  }, [ready, refreshState, refreshApps, refreshHistory, refreshAi]);

  // ---------------------------------------------------------------- voice
  const voiceActive = Boolean(voice && (voice.capturing || voice.state === "processing" || voice.state === "speaking"));
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const status = await get<VoiceStatus>("/api/voice/status");
        if (cancelled) return;
        setVoice(status);
        const t = status.last_transcript;
        if (t && t.ts > lastTranscriptTs.current) {
          // a voice command was handled by the backend: refresh what the UI shows
          if (lastTranscriptTs.current) {
            void refreshState();
            void refreshHistory();
            get<HistoryItem[]>("/api/history?limit=1")
              .then((items) => {
                const h = items[0];
                if (h && h.source === "voice")
                  setConversation((all) => [...all.slice(-29), {
                    id: `voice-${h.id}`, ts: h.ts, input: h.input, source: "voice", status: h.status,
                    message: h.message, intent: h.intent, action: h.action, risk: null, data: {},
                    confirmation: null, clarify: null, dry_run: h.status === "dry_run",
                  }]);
              })
              .catch(() => undefined);
          }
          lastTranscriptTs.current = t.ts;
        }
      } catch {
        /* backend banner covers this */
      }
    };
    void poll();
    const timer = window.setInterval(poll, voiceActive ? 120 : 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [ready, voiceActive, refreshState, refreshHistory]);

  const voiceAction = useCallback(
    async (action: "start" | "stop" | "toggle") => {
      const status = await guard(() => post<VoiceStatus>("/api/voice/ptt", { action }));
      if (status) setVoice(status);
    },
    [guard],
  );

  const setContinuous = useCallback(
    async (enabled: boolean) => {
      const status = await guard(() => post<VoiceStatus>("/api/voice/listen", { enabled }));
      if (status) setVoice(status);
    },
    [guard],
  );

  // ---------------------------------------------------------------- actions
  const record = useCallback(
    (response: CommandResponse | null) => {
      if (!response) return;
      setConversation((items) => [...items.slice(-29), response]);
      void refreshState();
      void refreshHistory();
    },
    [refreshState, refreshHistory],
  );

  const sendCommand = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return null;
      setBusy(true);
      try {
        const response = await guard(() => post<CommandResponse>("/api/command", { text: trimmed, source: "text" }));
        record(response);
        if (response?.action === "mode.set" || response?.action === "profile.silent") {
          const s = await guard(() => get<Settings>("/api/settings"));
          if (s) setSettings(s);
        }
        return response;
      } finally {
        setBusy(false);
      }
    },
    [guard, record],
  );

  const confirm = useCallback(
    async (id: string, approve: boolean, acknowledge = false) => {
      record(await guard(() => post<CommandResponse>("/api/confirm", { id, approve, acknowledge })));
    },
    [guard, record],
  );

  const undo = useCallback(async () => record(await guard(() => post<CommandResponse>("/api/undo"))), [guard, record]);
  const repeat = useCallback(async () => record(await guard(() => post<CommandResponse>("/api/repeat"))), [guard, record]);

  const setEmergency = useCallback(
    async (engaged: boolean) => {
      record(await guard(() => post<CommandResponse>("/api/emergency-stop", { engaged })));
    },
    [guard, record],
  );

  const launchApp = useCallback(
    async (id: string) => {
      record(await guard(() => post<CommandResponse>(`/api/apps/${id}/launch`)));
      void refreshApps();
    },
    [guard, record, refreshApps],
  );

  const updateSettings = useCallback(
    async (patch: Record<string, Record<string, unknown>>) => {
      const previous = settings;
      const updated = await guard(() => put<Settings>("/api/settings", patch));
      if (!updated) return null;
      setSettings(updated);
      applyUiSettings(updated.ui);
      if (window.arc) {
        if (!previous || previous.ui.scale !== updated.ui.scale) await window.arc.setZoom(updated.ui.scale);
        if (!previous || previous.general.autostart !== updated.general.autostart)
          await window.arc.setAutostart(updated.general.autostart);
        if (!previous || previous.general.start_minimized !== updated.general.start_minimized)
          await window.arc.setStartMinimized(updated.general.start_minimized);
      }
      void refreshState();
      if (patch.ai || patch.devices || patch.network) void refreshAi(true);
      return updated;
    },
    [guard, settings, refreshState, refreshAi],
  );

  const value = useMemo<ArcContextValue>(
    () => ({
      backend,
      state,
      settings,
      stats,
      ai,
      apps,
      history,
      conversation,
      voice,
      voiceAction,
      setContinuous,
      busy,
      toasts,
      sendCommand,
      confirm,
      undo,
      repeat,
      setEmergency,
      launchApp,
      updateSettings,
      refreshApps,
      refreshHistory,
      refreshAi,
      refreshState,
      notify,
      dismissToast,
    }),
    [backend, state, settings, stats, ai, apps, history, conversation, voice, voiceAction, setContinuous, busy, toasts, sendCommand, confirm, undo, repeat,
     setEmergency, launchApp, updateSettings, refreshApps, refreshHistory, refreshAi, refreshState, notify, dismissToast],
  );
  return <ArcContext.Provider value={value}>{children}</ArcContext.Provider>;
}

export { api };
