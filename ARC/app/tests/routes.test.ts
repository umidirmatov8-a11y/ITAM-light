import { describe, expect, it } from "vitest";

import { isAllowedRoute, routeTimeoutMs } from "../electron/routes";

describe("IPC route allowlist", () => {
  it("allows the routes the UI needs", () => {
    expect(isAllowedRoute("POST", "/api/command")).toBe(true);
    expect(isAllowedRoute("GET", "/api/history?limit=30")).toBe(true);
    expect(isAllowedRoute("PUT", "/api/apps/abc123")).toBe(true);
    expect(isAllowedRoute("POST", "/api/apps/abc_1-2/launch")).toBe(true);
    expect(isAllowedRoute("GET", "/api/audit/export?format=csv")).toBe(true);
    expect(isAllowedRoute("POST", "/api/voice/ptt")).toBe(true);
    expect(isAllowedRoute("DELETE", "/api/voice/models/whisper-small")).toBe(true);
    expect(isAllowedRoute("POST", "/api/vision/calibrate")).toBe(true);
    expect(isAllowedRoute("GET", "/api/vision/preview")).toBe(true);
    expect(isAllowedRoute("PUT", "/api/online/keys/brave")).toBe(true);
    expect(isAllowedRoute("POST", "/api/documents/abc123/open")).toBe(true);
  });

  it("gives commands enough time for the local model and online search", () => {
    expect(routeTimeoutMs("POST", "/api/command")).toBe(180_000);
    expect(routeTimeoutMs("POST", "/api/confirm")).toBe(180_000);
    expect(routeTimeoutMs("GET", "/api/state")).toBe(30_000);
    expect(routeTimeoutMs("GET", "/api/command")).toBe(30_000);
  });

  it("rejects everything else", () => {
    expect(isAllowedRoute("POST", "/api/shutdown")).toBe(false);
    expect(isAllowedRoute("DELETE", "/api/voice/models/../../settings")).toBe(false);
    expect(isAllowedRoute("POST", "/api/vision/preview")).toBe(false);
    expect(isAllowedRoute("GET", "/api/command")).toBe(false);
    expect(isAllowedRoute("DELETE", "/api/settings")).toBe(false);
    expect(isAllowedRoute("GET", "/api/online/keys/brave")).toBe(false);
    expect(isAllowedRoute("POST", "/api/documents/../settings/open")).toBe(false);
    expect(isAllowedRoute("PUT", "/api/apps/../settings")).toBe(false);
    expect(isAllowedRoute("GET", "/api/audit/export?format=exe")).toBe(false);
    expect(isAllowedRoute("GET", "/api/history?limit=1;drop")).toBe(false);
    expect(isAllowedRoute("GET", "http://evil/api/state")).toBe(false);
    expect(isAllowedRoute("GET", "/api/state" + "x".repeat(400))).toBe(false);
    expect(isAllowedRoute(undefined as unknown as string, "/api/state")).toBe(false);
  });
});
