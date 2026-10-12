/**
 * BackendManager: starts the Python backend, reads its readiness line, proxies HTTP requests
 * with the session token, restarts it after a crash and stops it on exit.
 */
import { ChildProcess, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import readline from "node:readline";

export type BackendState = "stopped" | "starting" | "ready" | "restarting" | "failed";

export interface BackendStatus {
  state: BackendState;
  message: string;
  restarts: number;
  port?: number;
}

export interface BackendCommand {
  command: string;
  args: string[];
  cwd: string;
}

export interface ApiResult {
  status: number;
  body: unknown;
}

const RESTART_DELAYS_MS = [1000, 2000, 4000, 8000, 16000];
const READY_TIMEOUT_MS = 60000;

export function resolveBackendCommand(opts: { packaged: boolean; resourcesPath: string; appPath: string }): BackendCommand {
  if (opts.packaged) {
    const dir = path.join(opts.resourcesPath, "backend");
    const exe = process.platform === "win32" ? "arc-backend.exe" : "arc-backend";
    return { command: path.join(dir, exe), args: [], cwd: dir };
  }
  const backendDir = path.resolve(opts.appPath, "..", "backend");
  const venvPython = process.platform === "win32"
    ? path.join(backendDir, ".venv", "Scripts", "python.exe")
    : path.join(backendDir, ".venv", "bin", "python");
  const python = process.env.ARC_PYTHON || (fs.existsSync(venvPython) ? venvPython : process.platform === "win32" ? "python" : "python3");
  const extra = process.env.ARC_BACKEND_MOCK === "1" ? ["--mock"] : [];
  return { command: python, args: ["-m", "arc_backend", ...extra], cwd: backendDir };
}

export class BackendManager extends EventEmitter {
  private proc: ChildProcess | null = null;
  private port = 0;
  private readonly token = randomBytes(32).toString("base64url");
  private restarts = 0;
  private stopping = false;
  private status: BackendStatus = { state: "stopped", message: "", restarts: 0 };
  private restartTimer: NodeJS.Timeout | null = null;
  private readyWaiters: Array<(ok: boolean) => void> = [];
  private stderrTail: string[] = [];

  constructor(private readonly cmd: BackendCommand, private readonly log: (line: string) => void = () => {}) {
    super();
  }

  getStatus(): BackendStatus {
    return { ...this.status };
  }

  start(): void {
    if (this.proc) return;
    this.stopping = false;
    this.setStatus(this.restarts ? "restarting" : "starting", "Запуск ядра A.R.C.…");
    if (path.isAbsolute(this.cmd.command) && !fs.existsSync(this.cmd.command)) {
      this.setStatus("failed", `Не найден исполняемый файл ядра: ${this.cmd.command}`);
      return;
    }
    const args = [...this.cmd.args, "--parent-pid", String(process.pid)];
    this.log(`spawn ${this.cmd.command} ${args.join(" ")}`);
    let proc: ChildProcess;
    try {
      proc = spawn(this.cmd.command, args, {
        cwd: this.cmd.cwd,
        env: { ...process.env, ARC_API_TOKEN: this.token, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
        // Not in Electron's job object: programs started by A.R.C. must survive A.R.C. exiting.
        detached: process.platform === "win32",
      });
    } catch (err) {
      this.setStatus("failed", `Не удалось запустить ядро: ${String(err)}`);
      return;
    }
    this.proc = proc;
    this.stderrTail = [];
    const timeout = setTimeout(() => {
      if (this.status.state !== "ready") {
        this.log("backend readiness timeout");
        proc.kill();
      }
    }, READY_TIMEOUT_MS);

    readline.createInterface({ input: proc.stdout! }).on("line", (line) => {
      try {
        const msg = JSON.parse(line);
        if (msg.event === "ready" && typeof msg.port === "number") {
          clearTimeout(timeout);
          this.port = msg.port;
          this.setStatus("ready", "Ядро работает", msg.port);
          // a backend that stayed up for a minute gets a fresh restart budget
          setTimeout(() => {
            if (this.status.state === "ready" && this.proc === proc) this.restarts = 0;
          }, 60000).unref();
          this.readyWaiters.splice(0).forEach((resolve) => resolve(true));
        } else if (msg.event === "error") {
          this.setStatus("failed", String(msg.message ?? "ошибка ядра"));
        }
      } catch {
        this.log(`backend: ${line}`);
      }
    });
    readline.createInterface({ input: proc.stderr! }).on("line", (line) => {
      this.stderrTail.push(line);
      if (this.stderrTail.length > 30) this.stderrTail.shift();
      this.log(`backend[err]: ${line}`);
    });
    proc.on("error", (err) => {
      this.log(`backend spawn error: ${err.message}`);
    });
    proc.on("exit", (code, signal) => {
      clearTimeout(timeout);
      this.log(`backend exited code=${code} signal=${signal}`);
      this.proc = null;
      this.port = 0;
      if (this.stopping) {
        this.setStatus("stopped", "Ядро остановлено");
        return;
      }
      this.scheduleRestart(code);
    });
  }

  private scheduleRestart(code: number | null): void {
    const tail = this.stderrTail.slice(-3).join(" | ");
    if (this.restarts >= RESTART_DELAYS_MS.length) {
      this.setStatus("failed", `Ядро аварийно завершилось (код ${code}). ${tail}`.trim());
      this.readyWaiters.splice(0).forEach((resolve) => resolve(false));
      return;
    }
    const delay = RESTART_DELAYS_MS[this.restarts];
    this.restarts += 1;
    this.setStatus("restarting", `Ядро перезапускается (${this.restarts}/${RESTART_DELAYS_MS.length})…`);
    this.restartTimer = setTimeout(() => {
      this.restartTimer = null;
      this.start();
    }, delay);
  }

  /** Manual restart from the diagnostics screen. */
  async restart(): Promise<void> {
    await this.stop();
    this.restarts = 0;
    this.start();
  }

  waitReady(timeoutMs = READY_TIMEOUT_MS): Promise<boolean> {
    if (this.status.state === "ready") return Promise.resolve(true);
    if (this.status.state === "failed") return Promise.resolve(false);
    return new Promise((resolve) => {
      const timer = setTimeout(() => resolve(false), timeoutMs);
      this.readyWaiters.push((ok) => {
        clearTimeout(timer);
        resolve(ok);
      });
    });
  }

  request(method: string, apiPath: string, body?: unknown, timeoutMs = 30000): Promise<ApiResult> {
    if (this.status.state !== "ready" || !this.port) {
      return Promise.resolve({ status: 503, body: { error: "backend_unavailable", detail: this.status.message } });
    }
    const payload = body === undefined ? undefined : Buffer.from(JSON.stringify(body), "utf-8");
    return new Promise((resolve) => {
      const req = http.request(
        {
          host: "127.0.0.1",
          port: this.port,
          method,
          path: apiPath,
          timeout: timeoutMs,
          headers: {
            "X-ARC-Token": this.token,
            Accept: "application/json",
            ...(payload ? { "Content-Type": "application/json", "Content-Length": payload.length } : {}),
          },
        },
        (res) => {
          const chunks: Buffer[] = [];
          res.on("data", (chunk) => chunks.push(chunk));
          res.on("end", () => {
            const text = Buffer.concat(chunks).toString("utf-8");
            let parsed: unknown = text;
            try {
              parsed = text ? JSON.parse(text) : null;
            } catch {
              /* keep text */
            }
            resolve({ status: res.statusCode ?? 0, body: parsed });
          });
        },
      );
      req.on("timeout", () => req.destroy(new Error("timeout")));
      req.on("error", (err) => resolve({ status: 0, body: { error: "network", detail: err.message } }));
      if (payload) req.write(payload);
      req.end();
    });
  }

  async stop(): Promise<void> {
    this.stopping = true;
    if (this.restartTimer) {
      clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
    const proc = this.proc;
    if (!proc) return;
    const exited = new Promise<void>((resolve) => proc.once("exit", () => resolve()));
    await this.request("POST", "/api/shutdown", undefined, 3000).catch(() => undefined);
    const timer = new Promise<void>((resolve) => setTimeout(resolve, 4000));
    await Promise.race([exited, timer]);
    if (this.proc) {
      this.log("backend did not exit in time, killing");
      this.proc.kill();
      await Promise.race([exited, new Promise((r) => setTimeout(r, 2000))]);
    }
  }

  private setStatus(state: BackendState, message: string, port?: number): void {
    this.status = { state, message, restarts: this.restarts, port };
    this.emit("status", this.getStatus());
  }
}
