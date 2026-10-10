import { defineConfig, type Plugin } from "vitest/config";
import react from "@vitejs/plugin-react";

// The React Fast Refresh preamble is an inline script; allow it only for the dev server.
const devCsp = (): Plugin => ({
  name: "arc-dev-csp",
  apply: "serve",
  transformIndexHtml: (html) => html.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'"),
});

export default defineConfig({
  plugins: [react(), devCsp()],
  base: "./",
  build: { outDir: "dist", emptyOutDir: true, target: "chrome130", sourcemap: false },
  server: { port: 5183, strictPort: true, host: "127.0.0.1" },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: ["tests/setup.ts"],
  },
});
