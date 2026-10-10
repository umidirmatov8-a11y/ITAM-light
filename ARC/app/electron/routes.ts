/**
 * Backend routes the renderer may call through IPC. Anything else is rejected in the main
 * process, so a compromised renderer cannot reach endpoints such as /api/shutdown.
 */
export type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

const ID = "[A-Za-z0-9_-]{1,64}";

export const ALLOWED_ROUTES: ReadonlyArray<readonly [HttpMethod, RegExp]> = [
  ["GET", /^\/api\/health$/],
  ["GET", /^\/api\/state$/],
  ["POST", /^\/api\/command$/],
  ["POST", /^\/api\/confirm$/],
  ["POST", /^\/api\/undo$/],
  ["POST", /^\/api\/repeat$/],
  ["POST", /^\/api\/emergency-stop$/],
  ["GET", /^\/api\/actions$/],
  ["GET", /^\/api\/settings$/],
  ["PUT", /^\/api\/settings$/],
  ["GET", /^\/api\/folders$/],
  ["GET", /^\/api\/apps$/],
  ["POST", /^\/api\/apps$/],
  ["POST", /^\/api\/apps\/discover$/],
  ["PUT", new RegExp(`^/api/apps/${ID}$`)],
  ["DELETE", new RegExp(`^/api/apps/${ID}$`)],
  ["POST", new RegExp(`^/api/apps/${ID}/launch$`)],
  ["GET", /^\/api\/scenarios$/],
  ["POST", /^\/api\/scenarios$/],
  ["PUT", new RegExp(`^/api/scenarios/${ID}$`)],
  ["DELETE", new RegExp(`^/api/scenarios/${ID}$`)],
  ["POST", new RegExp(`^/api/scenarios/${ID}/run$`)],
  ["GET", /^\/api\/history(\?limit=\d{1,4})?$/],
  ["DELETE", /^\/api\/history$/],
  ["GET", /^\/api\/audit(\?limit=\d{1,4})?$/],
  ["DELETE", /^\/api\/audit$/],
  ["GET", /^\/api\/audit\/export\?format=(json|csv)$/],
  ["GET", /^\/api\/system\/stats$/],
  ["GET", /^\/api\/ai\/status(\?force=true)?$/],
  ["GET", /^\/api\/diagnostics$/],
];

export function isAllowedRoute(method: string, path: string): boolean {
  if (typeof method !== "string" || typeof path !== "string" || path.length > 300) return false;
  return ALLOWED_ROUTES.some(([m, re]) => m === method && re.test(path));
}
