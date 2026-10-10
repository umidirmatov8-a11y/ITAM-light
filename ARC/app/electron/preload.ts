/** The only bridge between the sandboxed renderer and the main process. */
import { contextBridge, ipcRenderer } from "electron";

type Listener = (payload: unknown) => void;

function subscribe(channel: string, listener: Listener): () => void {
  const handler = (_event: unknown, payload: unknown) => listener(payload);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
}

contextBridge.exposeInMainWorld("arc", {
  api: (method: string, path: string, body?: unknown) => ipcRenderer.invoke("arc:api", { method, path, body }),
  backendStatus: () => ipcRenderer.invoke("arc:backend-status"),
  restartBackend: () => ipcRenderer.invoke("arc:backend-restart"),
  appInfo: () => ipcRenderer.invoke("arc:app-info"),
  window: (action: "minimize" | "maximize" | "close" | "compact" | "expand" | "quit") =>
    ipcRenderer.invoke("arc:window", action),
  setZoom: (factor: number) => ipcRenderer.invoke("arc:set-zoom", factor),
  setAutostart: (enabled: boolean) => ipcRenderer.invoke("arc:set-autostart", enabled),
  setStartMinimized: (enabled: boolean) => ipcRenderer.invoke("arc:set-start-minimized", enabled),
  pickFile: (kind: "exe" | "folder") => ipcRenderer.invoke("arc:pick-file", kind),
  saveFile: (filename: string, content: string) => ipcRenderer.invoke("arc:save-file", { filename, content }),
  showInFolder: (path: string) => ipcRenderer.invoke("arc:show-in-folder", path),
  onBackendStatus: (listener: Listener) => subscribe("arc:backend-status", listener),
  onEvent: (listener: Listener) => subscribe("arc:event", listener),
});
