import { vi } from "vitest";

import type { ArcBridge, ArcState, CommandResponse, Settings } from "../src/lib/types";

export const settings: Settings = {
  general: { language: "ru", wake_word: "арк", autostart: false, start_minimized: false, require_wake_word_for_voice: true, min_confidence: 0.6 },
  network: { mode: "LOCAL", online_allowed: true, search_url: "https://duckduckgo.com/?q={query}" },
  devices: { microphone_enabled: true, camera_enabled: false, local_ai_enabled: true },
  ai: { ollama_url: "http://127.0.0.1:11434", model: "qwen2.5-coder:7b", temperature: 0.2, timeout_s: 60 },
  safety: { dry_run: true, allowed_dirs: ["C:\\Users\\u\\Desktop"], confirmation_ttl_s: 60, modules: { apps: true }, action_timeout_s: 15 },
  ui: { theme: "amber", scale: 1, animations: false, scanlines: false },
  profile: { silent: false },
};

export const state: ArcState = {
  emergency_stop: false,
  dialog: null,
  pending_confirmation: null,
  can_undo: false,
  can_repeat: false,
  last_response: null,
  mode: "LOCAL",
  online_allowed: true,
  devices: settings.devices,
  silent: false,
  dry_run: true,
  simulated: false,
  voice: { state: "not_installed", message: "Голосовой модуль подключается на этапе 2" },
  camera: { state: "not_installed", message: "Модуль жестов подключается на этапе 3" },
};

export function response(partial: Partial<CommandResponse>): CommandResponse {
  return {
    id: Math.random().toString(36).slice(2),
    ts: Date.now() / 1000,
    input: "",
    source: "text",
    status: "done",
    message: "",
    intent: null,
    action: null,
    risk: null,
    data: {},
    confirmation: null,
    clarify: null,
    dry_run: false,
    ...partial,
  };
}

type Handler = (method: string, path: string, body?: any) => any;

export function installBridge(handler: Handler = () => undefined) {
  const api = vi.fn(async (method: string, path: string, body?: unknown) => {
    const custom = handler(method, path, body);
    if (custom !== undefined) return { status: 200, body: custom };
    if (path === "/api/state") return { status: 200, body: state };
    if (path === "/api/settings") return { status: 200, body: settings };
    if (path === "/api/apps") return { status: 200, body: [] };
    if (path.startsWith("/api/history")) return { status: 200, body: [] };
    if (path.startsWith("/api/ai/status")) return { status: 200, body: { state: "offline", message: "Ollama недоступна", model: "m", url: "u", models: [] } };
    if (path === "/api/system/stats") return { status: 200, body: { cpu: 10, ram: { percent: 50, used_gb: 8, total_gb: 16 }, gpu: null, ts: 1 } };
    return { status: 404, body: { detail: "not mocked" } };
  });
  const bridge: ArcBridge = {
    api,
    backendStatus: vi.fn(async () => ({ state: "ready" as const, message: "ok", restarts: 0 })),
    restartBackend: vi.fn(),
    appInfo: vi.fn(async () => ({ version: "0.1.0", platform: "win32", packaged: false, electron: "x", userData: "u", autostart: false })),
    window: vi.fn(),
    setZoom: vi.fn(async (z: number) => z),
    setAutostart: vi.fn(async (v: boolean) => v),
    setStartMinimized: vi.fn(async () => undefined),
    pickFile: vi.fn(async () => null),
    saveFile: vi.fn(async () => null),
    showInFolder: vi.fn(async () => undefined),
    onBackendStatus: vi.fn(() => () => undefined),
    onEvent: vi.fn(() => () => undefined),
  };
  window.arc = bridge;
  return { bridge, api };
}
