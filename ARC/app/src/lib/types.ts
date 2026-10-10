// Contracts mirrored from the Python backend (arc_backend/models.py, storage/settings.py, apps/registry.py).

export type Status =
  | "done"
  | "dry_run"
  | "needs_confirmation"
  | "clarify"
  | "denied"
  | "not_found"
  | "unknown"
  | "unavailable"
  | "cancelled"
  | "ignored"
  | "error"
  | "reply";

export type Risk = "A" | "B" | "C";

export interface ConfirmationInfo {
  id: string;
  action: string;
  title: string;
  description: string;
  risk: Risk;
  expires_at: number;
  requires_acknowledge: boolean;
}

export interface CommandResponse {
  id: string;
  ts: number;
  input: string;
  source: string;
  status: Status;
  message: string;
  intent: string | null;
  action: string | null;
  risk: Risk | null;
  data: Record<string, any>;
  confirmation: ConfirmationInfo | null;
  clarify: { question: string; options: string[] } | null;
  dry_run: boolean;
}

export interface ModuleState {
  state: string;
  message: string;
}

export interface ArcState {
  emergency_stop: boolean;
  dialog: { question: string; options: string[] } | null;
  pending_confirmation: ConfirmationInfo | null;
  can_undo: boolean;
  can_repeat: boolean;
  last_response: CommandResponse | null;
  mode: "LOCAL" | "ONLINE";
  online_allowed: boolean;
  devices: { microphone_enabled: boolean; camera_enabled: boolean; local_ai_enabled: boolean };
  silent: boolean;
  dry_run: boolean;
  simulated: boolean;
  voice: { state: VoiceStateName; message: string; ptt: boolean; continuous: boolean };
  camera: ModuleState;
}

export interface Settings {
  general: {
    language: string;
    wake_word: string;
    autostart: boolean;
    start_minimized: boolean;
    require_wake_word_for_voice: boolean;
    min_confidence: number;
  };
  network: { mode: "LOCAL" | "ONLINE"; online_allowed: boolean; search_url: string };
  devices: { microphone_enabled: boolean; camera_enabled: boolean; local_ai_enabled: boolean };
  ai: { ollama_url: string; model: string; temperature: number; timeout_s: number };
  safety: {
    dry_run: boolean;
    allowed_dirs: string[];
    confirmation_ttl_s: number;
    modules: Record<string, boolean>;
    action_timeout_s: number;
  };
  ui: { theme: "amber" | "phosphor" | "ice"; scale: number; animations: boolean; scanlines: boolean };
  profile: { silent: boolean };
  voice: VoiceSettings;
}

export interface VoiceSettings {
  mode: "ptt" | "continuous";
  stt_model: string;
  stt_device: "auto" | "cpu" | "cuda";
  input_device: string | null;
  tts_engine: "sapi" | "piper" | "off";
  tts_voice: string;
  tts_rate: number;
  tts_volume: number;
  vad_sensitivity: number;
  silence_ms: number;
  max_utterance_s: number;
}

export type VoiceStateName =
  | "disabled"
  | "not_installed"
  | "idle"
  | "listening"
  | "continuous"
  | "hearing"
  | "processing"
  | "speaking"
  | "error";

export interface VoiceStatus {
  state: VoiceStateName;
  message: string;
  mode: "ptt" | "continuous";
  ptt: boolean;
  continuous: boolean;
  capturing: boolean;
  levels: number[];
  stt: { model: string; installed: boolean; device: string | null; loaded: boolean };
  tts: { engine: string; warning: string | null };
  last_transcript: { text: string; confidence: number; duration_s: number; elapsed_s: number; ts: number; explicit: boolean } | null;
}

export interface VoiceModel {
  id: string;
  title: string;
  kind: "stt" | "tts_runtime" | "tts_voice";
  size_mb: number;
  description: string;
  license: string;
  supported: boolean;
  installed: boolean;
  download: { state: "downloading" | "done" | "error" | "cancelled"; done_mb: number; total_mb: number; progress: number; message: string } | null;
}

export type LaunchType = "exe" | "lnk" | "uwp" | "protocol";
export type AppKind = "app" | "game" | "system";

export interface AppEntry {
  id: string;
  name: string;
  kind: AppKind;
  category: string;
  launch_type: LaunchType;
  target: string;
  args: string[];
  working_dir: string;
  aliases: string[];
  process_name: string;
  source: string;
  run_as_admin: boolean;
  enabled: boolean;
  pinned: boolean;
  created_at: number;
  updated_at: number;
  last_launched: number | null;
}

export interface ScenarioStep {
  action: string;
  params: Record<string, any>;
}

export interface Scenario {
  id: string;
  name: string;
  aliases: string[];
  steps: ScenarioStep[];
  enabled: boolean;
}

export interface HistoryItem {
  id: number;
  ts: number;
  source: string;
  input: string;
  intent: string | null;
  action: string | null;
  status: Status;
  message: string;
}

export interface AuditItem {
  id: number;
  ts: number;
  action: string;
  params: Record<string, any>;
  risk: string;
  source: string;
  decision: string;
  status: string;
  message: string;
  dry_run: boolean;
}

export interface SystemStats {
  cpu: number;
  ram: { percent: number; used_gb: number; total_gb: number };
  gpu: { name: string; load: number; mem_used_mb: number; mem_total_mb: number; temp_c: number } | null;
  ts: number;
}

export interface AiStatus {
  state: "ready" | "model_missing" | "offline" | "disabled" | "blocked";
  message: string;
  model: string;
  url: string;
  models: string[];
}

export interface ActionSpecView {
  name: string;
  title: string;
  module: string;
  risk: Risk;
  gesture_allowed: boolean;
  requires_online: boolean;
  params: string[];
}

export interface BackendStatus {
  state: "stopped" | "starting" | "ready" | "restarting" | "failed";
  message: string;
  restarts: number;
  port?: number;
}

export interface DiagnosticsReport {
  checks: { name: string; state: "ok" | "warn" | "info" | "error"; detail: string }[];
  data_dir: string;
  ts: number;
}

export interface ApiReply {
  status: number;
  body: any;
}

export interface ArcBridge {
  api(method: string, path: string, body?: unknown): Promise<ApiReply>;
  backendStatus(): Promise<BackendStatus>;
  restartBackend(): Promise<BackendStatus>;
  appInfo(): Promise<{ version: string; platform: string; packaged: boolean; electron: string; userData: string; autostart: boolean }>;
  window(action: "minimize" | "maximize" | "close" | "compact" | "expand" | "quit"): Promise<void>;
  setZoom(factor: number): Promise<number>;
  setAutostart(enabled: boolean): Promise<boolean>;
  setStartMinimized(enabled: boolean): Promise<void>;
  pickFile(kind: "exe" | "folder"): Promise<string | null>;
  saveFile(filename: string, content: string): Promise<string | null>;
  showInFolder(path: string): Promise<void>;
  onBackendStatus(listener: (status: BackendStatus) => void): () => void;
  onEvent(listener: (event: { type: string }) => void): () => void;
}

declare global {
  interface Window {
    arc: ArcBridge;
  }
}
