import { describe, expect, it } from "vitest";

import { isAllowedRoute } from "../electron/routes";

describe("IPC route allowlist", () => {
  it("allows the routes the UI needs", () => {
    expect(isAllowedRoute("POST", "/api/command")).toBe(true);
    expect(isAllowedRoute("GET", "/api/history?limit=30")).toBe(true);
    expect(isAllowedRoute("PUT", "/api/apps/abc123")).toBe(true);
    expect(isAllowedRoute("POST", "/api/apps/abc_1-2/launch")).toBe(true);
    expect(isAllowedRoute("GET", "/api/audit/export?format=csv")).toBe(true);
  });

  it("rejects everything else", () => {
    expect(isAllowedRoute("POST", "/api/shutdown")).toBe(false);
    expect(isAllowedRoute("GET", "/api/command")).toBe(false);
    expect(isAllowedRoute("DELETE", "/api/settings")).toBe(false);
    expect(isAllowedRoute("PUT", "/api/apps/../settings")).toBe(false);
    expect(isAllowedRoute("GET", "/api/audit/export?format=exe")).toBe(false);
    expect(isAllowedRoute("GET", "/api/history?limit=1;drop")).toBe(false);
    expect(isAllowedRoute("GET", "http://evil/api/state")).toBe(false);
    expect(isAllowedRoute("GET", "/api/state" + "x".repeat(400))).toBe(false);
    expect(isAllowedRoute(undefined as unknown as string, "/api/state")).toBe(false);
  });
});
