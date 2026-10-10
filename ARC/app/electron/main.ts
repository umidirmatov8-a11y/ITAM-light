/**
 * A.R.C. main process: windows, tray, global shortcuts, IPC bridge, backend lifecycle.
 */
import {
  app,
  BrowserWindow,
  dialog,
  globalShortcut,
  ipcMain,
  IpcMainInvokeEvent,
  Menu,
  nativeImage,
  session,
  shell,
  Tray,
} from "electron";
import fs from "node:fs";
import path from "node:path";

import { BackendManager, resolveBackendCommand } from "./backend";
import { isAllowedRoute } from "./routes";
import { runSmokeTest } from "./smoke";

const DEV_URL = process.env.ARC_DEV_URL || "";
const smokeArg = process.argv.find((a) => a.startsWith("--smoke-test"));
const startHidden = process.argv.includes("--hidden");

interface Prefs {
  startMinimized: boolean;
  zoom: number;
  bounds?: { x: number; y: number; width: number; height: number };
}

let mainWindow: BrowserWindow | null = null;
let compactWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let quitting = false;
let backendStopped = false;

// ------------------------------------------------------------------ logging & prefs
const logDir = () => path.join(app.getPath("userData"), "logs");

function log(line: string): void {
  try {
    fs.mkdirSync(logDir(), { recursive: true });
    const file = path.join(logDir(), "main.log");
    if (fs.existsSync(file) && fs.statSync(file).size > 1_000_000) fs.renameSync(file, file + ".1");
    fs.appendFileSync(file, `${new Date().toISOString()} ${line}\n`);
  } catch {
    /* logging must never crash the app */
  }
}

const prefsFile = () => path.join(app.getPath("userData"), "prefs.json");

function loadPrefs(): Prefs {
  try {
    const data = JSON.parse(fs.readFileSync(prefsFile(), "utf-8"));
    return {
      startMinimized: Boolean(data.startMinimized),
      zoom: typeof data.zoom === "number" && data.zoom >= 0.75 && data.zoom <= 1.5 ? data.zoom : 1,
      bounds: data.bounds,
    };
  } catch {
    return { startMinimized: false, zoom: 1 };
  }
}

function savePrefs(patch: Partial<Prefs>): void {
  const prefs = { ...loadPrefs(), ...patch };
  try {
    fs.mkdirSync(path.dirname(prefsFile()), { recursive: true });
    fs.writeFileSync(prefsFile(), JSON.stringify(prefs, null, 2));
  } catch (err) {
    log(`prefs save failed: ${String(err)}`);
  }
}

// ------------------------------------------------------------------ backend
const backend = new BackendManager(
  resolveBackendCommand({ packaged: app.isPackaged, resourcesPath: process.resourcesPath, appPath: app.getAppPath() }),
  log,
);
backend.on("status", (status) => {
  for (const win of [mainWindow, compactWindow]) {
    if (win && !win.isDestroyed()) win.webContents.send("arc:backend-status", status);
  }
  updateTrayMenu();
});

// ------------------------------------------------------------------ windows
function assetPath(name: string): string {
  return path.join(app.getAppPath(), "assets", name);
}

function rendererUrl(hash = ""): { url?: string; file?: string; hash: string } {
  if (DEV_URL) return { url: DEV_URL + (hash ? `#${hash}` : ""), hash };
  return { file: path.join(app.getAppPath(), "dist", "index.html"), hash };
}

function load(win: BrowserWindow, hash = ""): void {
  const target = rendererUrl(hash);
  if (target.url) void win.loadURL(target.url);
  else void win.loadFile(target.file!, hash ? { hash } : undefined);
}

const webPreferences = {
  preload: path.join(__dirname, "preload.js"),
  contextIsolation: true,
  sandbox: true,
  nodeIntegration: false,
  webSecurity: true,
  spellcheck: false,
  devTools: !app.isPackaged,
};

function createMainWindow(show: boolean): BrowserWindow {
  const prefs = loadPrefs();
  const win = new BrowserWindow({
    width: prefs.bounds?.width ?? 1320,
    height: prefs.bounds?.height ?? 840,
    x: prefs.bounds?.x,
    y: prefs.bounds?.y,
    minWidth: 980,
    minHeight: 660,
    show: false,
    frame: false,
    backgroundColor: "#0b0b09",
    title: "A.R.C.",
    icon: assetPath("icon.png"),
    webPreferences,
  });
  win.once("ready-to-show", () => {
    win.webContents.setZoomFactor(prefs.zoom);
    if (show) win.show();
  });
  win.on("close", (event) => {
    savePrefs({ bounds: win.getBounds() });
    if (!quitting) {
      event.preventDefault();
      win.hide();
    }
  });
  load(win);
  return win;
}

function createCompactWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 380,
    height: 132,
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    show: false,
    backgroundColor: "#0b0b09",
    title: "A.R.C. — виджет",
    webPreferences,
  });
  win.on("close", (event) => {
    if (!quitting) {
      event.preventDefault();
      win.hide();
    }
  });
  win.once("ready-to-show", () => win.webContents.setZoomFactor(loadPrefs().zoom));
  load(win, "compact");
  return win;
}

function showMain(): void {
  if (!mainWindow) return;
  compactWindow?.hide();
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function toggleMain(): void {
  if (mainWindow?.isVisible() && mainWindow.isFocused()) mainWindow.hide();
  else showMain();
}

function showCompact(): void {
  if (!compactWindow || compactWindow.isDestroyed()) compactWindow = createCompactWindow();
  mainWindow?.hide();
  compactWindow.show();
}

// ------------------------------------------------------------------ tray & shortcuts
async function emergencyStop(): Promise<void> {
  const result = await backend.request("POST", "/api/emergency-stop", { engaged: true });
  log(`emergency stop via shortcut/tray: ${result.status}`);
  for (const win of [mainWindow, compactWindow]) {
    if (win && !win.isDestroyed()) win.webContents.send("arc:event", { type: "emergency-stop" });
  }
}

function updateTrayMenu(): void {
  if (!tray) return;
  const status = backend.getStatus();
  tray.setToolTip(`A.R.C. — ${status.state === "ready" ? "готов" : status.message}`);
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Показать A.R.C.", click: showMain },
      { label: "Компактный виджет", click: showCompact },
      { type: "separator" },
      { label: "Аварийная остановка (Ctrl+Alt+End)", click: () => void emergencyStop() },
      { type: "separator" },
      { label: `Ядро: ${status.state}`, enabled: false },
      { label: "Выход", click: () => app.quit() },
    ]),
  );
}

function createTray(): void {
  const image = nativeImage.createFromPath(assetPath("tray.png"));
  tray = new Tray(image.isEmpty() ? nativeImage.createEmpty() : image);
  tray.on("click", showMain);
  updateTrayMenu();
}

function registerShortcuts(): void {
  const shortcuts: Array<[string, () => void]> = [
    ["Control+Alt+A", toggleMain],
    ["Control+Alt+End", () => void emergencyStop()],
  ];
  for (const [accelerator, handler] of shortcuts) {
    if (!globalShortcut.register(accelerator, handler)) log(`shortcut ${accelerator} is taken by another program`);
  }
}

// ------------------------------------------------------------------ IPC
function trustedSender(event: IpcMainInvokeEvent): boolean {
  const url = event.senderFrame?.url ?? "";
  if (DEV_URL) return url.startsWith(DEV_URL);
  const expected = "file:///" + path.join(app.getAppPath(), "dist", "index.html").replace(/\\/g, "/").replace(/^\/+/, "");
  return decodeURI(url.split("#")[0]).toLowerCase() === decodeURI(expected).toLowerCase();
}

function handle(channel: string, fn: (event: IpcMainInvokeEvent, arg: any) => unknown): void {
  ipcMain.handle(channel, async (event, arg) => {
    if (!trustedSender(event)) {
      log(`rejected IPC ${channel} from ${event.senderFrame?.url}`);
      throw new Error("untrusted sender");
    }
    return fn(event, arg);
  });
}

function registerIpc(): void {
  handle("arc:api", async (_e, arg: { method: string; path: string; body?: unknown }) => {
    if (!arg || !isAllowedRoute(arg.method, arg.path)) {
      return { status: 403, body: { error: "route_not_allowed" } };
    }
    return backend.request(arg.method, arg.path, arg.body);
  });
  handle("arc:backend-status", () => backend.getStatus());
  handle("arc:backend-restart", async () => {
    await backend.restart();
    return backend.getStatus();
  });
  handle("arc:app-info", () => ({
    version: app.getVersion(),
    platform: process.platform,
    packaged: app.isPackaged,
    electron: process.versions.electron,
    userData: app.getPath("userData"),
    autostart: app.getLoginItemSettings().openAtLogin,
  }));
  handle("arc:window", (event, action: string) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    switch (action) {
      case "minimize":
        win?.minimize();
        break;
      case "maximize":
        if (win?.isMaximized()) win.unmaximize();
        else win?.maximize();
        break;
      case "close":
        win?.close();
        break;
      case "compact":
        showCompact();
        break;
      case "expand":
        showMain();
        break;
      case "quit":
        app.quit();
        break;
    }
  });
  handle("arc:set-zoom", (_e, factor: number) => {
    const zoom = Math.min(1.5, Math.max(0.75, Number(factor) || 1));
    for (const win of [mainWindow, compactWindow]) win?.webContents.setZoomFactor(zoom);
    savePrefs({ zoom });
    return zoom;
  });
  handle("arc:set-autostart", (_e, enabled: boolean) => {
    if (app.isPackaged) {
      app.setLoginItemSettings({ openAtLogin: Boolean(enabled), path: process.execPath, args: ["--hidden"] });
    }
    return app.getLoginItemSettings().openAtLogin;
  });
  handle("arc:set-start-minimized", (_e, enabled: boolean) => savePrefs({ startMinimized: Boolean(enabled) }));
  handle("arc:pick-file", async (event, kind: "exe" | "folder") => {
    const win = BrowserWindow.fromWebContents(event.sender) ?? undefined;
    const options: Electron.OpenDialogOptions =
      kind === "folder"
        ? { title: "Выберите каталог", properties: ["openDirectory"] }
        : {
            title: "Выберите программу",
            properties: ["openFile"],
            filters: [{ name: "Программы и ярлыки", extensions: ["exe", "lnk"] }],
          };
    const result = win ? await dialog.showOpenDialog(win, options) : await dialog.showOpenDialog(options);
    return result.canceled ? null : result.filePaths[0];
  });
  handle("arc:save-file", async (event, arg: { filename: string; content: string }) => {
    const win = BrowserWindow.fromWebContents(event.sender) ?? undefined;
    const safeName = String(arg?.filename ?? "arc-export.txt").replace(/[\\/:*?"<>|]/g, "_");
    const options = { title: "Сохранить", defaultPath: path.join(app.getPath("documents"), safeName) };
    const result = win ? await dialog.showSaveDialog(win, options) : await dialog.showSaveDialog(options);
    if (result.canceled || !result.filePath) return null;
    fs.writeFileSync(result.filePath, String(arg.content ?? ""), "utf-8");
    return result.filePath;
  });
  handle("arc:show-in-folder", (_e, target: string) => {
    if (typeof target === "string" && path.isAbsolute(target) && fs.existsSync(target)) shell.showItemInFolder(target);
  });
}

// ------------------------------------------------------------------ hardening
function harden(): void {
  session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  app.on("web-contents-created", (_event, contents) => {
    contents.setWindowOpenHandler(() => ({ action: "deny" }));
    contents.on("will-navigate", (event, url) => {
      if (!(DEV_URL && url.startsWith(DEV_URL))) event.preventDefault();
    });
    contents.on("will-attach-webview", (event) => event.preventDefault());
  });
}

// ------------------------------------------------------------------ lifecycle
if (!smokeArg && !app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => showMain());

  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null);
    harden();
    registerIpc();
    log(`start v${app.getVersion()} packaged=${app.isPackaged} argv=${process.argv.slice(1).join(" ")}`);
    backend.start();
    if (smokeArg) {
      const out = smokeArg.includes("=") ? smokeArg.split("=").slice(1).join("=") : path.join(logDir(), "smoke.json");
      mainWindow = createMainWindow(false);
      const code = await runSmokeTest({ backend, window: mainWindow, out, log });
      quitting = true;
      await backend.stop();
      backendStopped = true;
      app.exit(code);
      return;
    }
    const hidden = startHidden || loadPrefs().startMinimized;
    mainWindow = createMainWindow(!hidden);
    createTray();
    registerShortcuts();
  });

  app.on("before-quit", (event) => {
    quitting = true;
    if (!backendStopped) {
      event.preventDefault();
      backend
        .stop()
        .catch((err) => log(`backend stop error: ${String(err)}`))
        .finally(() => {
          backendStopped = true;
          app.quit();
        });
    }
  });

  app.on("will-quit", () => globalShortcut.unregisterAll());
  app.on("window-all-closed", () => {
    /* stay in the tray */
  });
}
