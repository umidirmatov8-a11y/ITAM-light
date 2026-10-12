import { vi } from "vitest";

import type { ArcBridge, ArcState, CommandResponse, Settings, VisionStatus, VoiceStatus } from "../src/lib/types";

export const settings: Settings = {
  general: { language: "ru", wake_word: "арк", autostart: false, start_minimized: false, require_wake_word_for_voice: true, min_confidence: 0.6 },
  network: { mode: "LOCAL", online_allowed: true, search_url: "https://duckduckgo.com/?q={query}" },
  online: { providers: ["wikipedia", "duckduckgo"], language: "ru", max_results: 5, timeout_s: 10,
            requests_per_minute: 20, summarize: true, searxng_url: "" },
  documents: { output_dir: "", use_ai: true, open_when_ready: false, max_sections: 8 },
  devices: { microphone_enabled: true, camera_enabled: false, local_ai_enabled: true },
  ai: { ollama_url: "http://127.0.0.1:11434", model: "qwen2.5-coder:7b", temperature: 0.2, timeout_s: 60,
        understand_commands: true, answer_questions: true, confirm_actions: false, num_ctx: 4096 },
  safety: { dry_run: true, allowed_dirs: ["C:\\Users\\u\\Desktop"], confirmation_ttl_s: 60, modules: { apps: true }, action_timeout_s: 15 },
  ui: { theme: "amber", scale: 1, animations: false, scanlines: false },
  profile: { silent: false },
  voice: { mode: "ptt", stt_model: "whisper-small", stt_device: "auto", input_device: null, tts_engine: "sapi",
           tts_voice: "", tts_rate: 1, tts_volume: 80, vad_sensitivity: 0.5, silence_ms: 800, max_utterance_s: 12 },
  vision: { camera_index: 0, mirror: true, fps: 15, confidence: 0.7, hold_ms: 600, cooldown_ms: 1500, min_interval_ms: 800,
            zone: [0.65, 0, 1, 0.4], zone_hold_ms: 1500, calibration: null,
            bindings: { fist: { enabled: true, action: "gestures.cancel", params: {} },
                        victory: { enabled: false, action: "volume.mute", params: { muted: true } } } },
};

export const visionStatus: VisionStatus = {
  state: "idle", message: "Жесты выключены", running: false, paused: false, fps: 0, brightness: null, dark: false,
  gesture: "none", gesture_title: "—", raw_gesture: "none", confidence: 0, fingers: {}, progress: 0, landmarks: null,
  zone: [0.65, 0, 1, 0.4], events: [], preview: false, calibration: null, calibrating: null, model_installed: true,
};

export const voiceStatus: VoiceStatus = {
  state: "idle", message: "Готов", mode: "ptt", ptt: false, continuous: false, capturing: false,
  levels: [], stt: { model: "whisper-small", installed: true, device: "cpu", loaded: false },
  tts: { engine: "sapi", warning: null }, last_transcript: null,
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
  voice: { state: "idle", message: "Готов", ptt: false, continuous: false },
  camera: { state: "idle", message: "Жесты выключены", running: false, paused: false },
  online_active: 0,
  documents_active: 0,
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
    if (path === "/api/voice/status") return { status: 200, body: voiceStatus };
    if (path === "/api/vision/status") return { status: 200, body: visionStatus };
    if (path === "/api/vision/actions") return { status: 200, body: {
      actions: { "gestures.cancel": "Отменить", "volume.mute": "Звук вкл/выкл", "window.minimize_all": "Свернуть все окна" },
      gestures: { fist: "Кулак", victory: "Два пальца (V)" } } };
    if (path === "/api/scenarios") return { status: 200, body: { scenarios: [], allowed_actions: [] } };
    if (path === "/api/voice/devices") return { status: 200, body: { inputs: [{ index: 1, name: "USB Mic", default: true }], voices: [], cuda: false } };
    if (path === "/api/voice/models") return { status: 200, body: { free_mb: 50000, dir: "C:/models", models: [
      { id: "whisper-small", title: "Whisper small", kind: "stt", size_mb: 484, description: "", license: "MIT", supported: true, installed: false, download: null },
    ] } };
    if (path === "/api/documents") return { status: 200, body: { jobs: [], recent: [], folder: "C:\\Users\\u\\Documents\\ARC", folder_error: "" } };
    if (path === "/api/online/status") return { status: 200, body: { active: 0, recent: [], used_last_minute: 0, mode: "LOCAL",
      online_allowed: true, secrets_backend: "windows-credential-manager", secrets_persistent: true, providers: [
        { id: "wikipedia", title: "Википедия", needs_key: false, has_key: null, enabled: true, order: 0 },
        { id: "brave", title: "Brave Search API", needs_key: true, has_key: false, enabled: false, order: null }] } };
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
