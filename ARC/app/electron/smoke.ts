/**
 * `A.R.C. --smoke-test=<file>`: starts the backend and the renderer without showing a window,
 * runs a command end-to-end (renderer → IPC → backend) and writes a JSON report. Used by CI.
 */
import { BrowserWindow } from "electron";
import fs from "node:fs";

import type { BackendManager } from "./backend";

interface SmokeOptions {
  backend: BackendManager;
  window: BrowserWindow;
  out: string;
  log: (line: string) => void;
}

function loaded(win: BrowserWindow): Promise<void> {
  if (!win.webContents.isLoading()) return Promise.resolve();
  return new Promise((resolve) => win.webContents.once("did-finish-load", () => resolve()));
}

export async function runSmokeTest({ backend, window, out, log }: SmokeOptions): Promise<number> {
  const report: Record<string, unknown> = { started: new Date().toISOString() };
  let ok = false;
  try {
    report.backendReady = await backend.waitReady(90000);
    report.backendStatus = backend.getStatus();
    if (report.backendReady) {
      report.health = (await backend.request("GET", "/api/health")).body;
      report.command = (await backend.request("POST", "/api/command", { text: "который час" })).body;
    }
    await loaded(window);
    // The renderer marks its root with the backend state it sees through IPC.
    report.renderer = await window.webContents.executeJavaScript(`
      new Promise((resolve) => {
        let tries = 0;
        const timer = setInterval(() => {
          const root = document.querySelector('[data-testid="arc-root"]');
          const state = root && root.getAttribute('data-backend');
          if (state === 'ready' || ++tries > 300) {
            clearInterval(timer);
            resolve({ mounted: !!root, backend: state, title: document.title,
                      buttons: document.querySelectorAll('button').length });
          }
        }, 100);
      })`);
    report.ipcCommand = await window.webContents.executeJavaScript(
      `window.arc.api('POST', '/api/command', { text: 'сколько свободного места на диске' })`,
    );
    report.ipcForbidden = await window.webContents.executeJavaScript(`window.arc.api('POST', '/api/shutdown')`);
    const command = report.command as { status?: string } | undefined;
    const renderer = report.renderer as { mounted?: boolean; backend?: string };
    const ipc = report.ipcCommand as { status?: number; body?: { status?: string } };
    const forbidden = report.ipcForbidden as { status?: number };
    ok = Boolean(
      report.backendReady &&
        command?.status === "done" &&
        renderer?.mounted &&
        renderer.backend === "ready" &&
        ipc?.status === 200 &&
        ipc.body?.status === "done" &&
        forbidden?.status === 403,
    );
  } catch (err) {
    report.error = String(err);
  }
  report.passed = ok;
  report.finished = new Date().toISOString();
  try {
    fs.writeFileSync(out, JSON.stringify(report, null, 2), "utf-8");
  } catch (err) {
    log(`smoke report write failed: ${String(err)}`);
  }
  log(`smoke test ${ok ? "passed" : "FAILED"}`);
  return ok ? 0 : 1;
}
