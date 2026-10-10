// Development launcher: Vite dev server + compiled main process + Electron (backend from ../backend/.venv).
import { spawn, spawnSync } from "node:child_process";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const bin = (name) => path.join(root, "node_modules", ".bin", process.platform === "win32" ? `${name}.cmd` : name);
const URL = "http://127.0.0.1:5183/";

const tsc = spawnSync(bin("tsc"), ["-p", "tsconfig.electron.json"], { cwd: root, stdio: "inherit", shell: process.platform === "win32" });
if (tsc.status !== 0) process.exit(tsc.status ?? 1);

const vite = spawn(bin("vite"), [], { cwd: root, stdio: "inherit", shell: process.platform === "win32" });

function waitForVite(tries = 100) {
  return new Promise((resolve, reject) => {
    const attempt = (n) => {
      http.get(URL, (res) => { res.resume(); resolve(); }).on("error", () => {
        if (n <= 0) reject(new Error("Vite did not start"));
        else setTimeout(() => attempt(n - 1), 200);
      });
    };
    attempt(tries);
  });
}

await waitForVite();
const electron = spawn(bin("electron"), [".", ...process.argv.slice(2)], {
  cwd: root,
  stdio: "inherit",
  shell: process.platform === "win32",
  env: { ...process.env, ARC_DEV_URL: URL },
});
electron.on("exit", (code) => {
  vite.kill();
  process.exit(code ?? 0);
});
