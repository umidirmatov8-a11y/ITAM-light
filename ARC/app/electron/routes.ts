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
  ["GET", /^\/api\/voice\/status$/],
  ["POST", /^\/api\/voice\/ptt$/],
  ["POST", /^\/api\/voice\/listen$/],
  ["POST", /^\/api\/voice\/tts-test$/],
  ["GET", /^\/api\/voice\/devices$/],
  ["GET", /^\/api\/voice\/models$/],
  ["POST", /^\/api\/voice\/models\/download$/],
  ["POST", /^\/api\/voice\/models\/cancel$/],
  ["DELETE", /^\/api\/voice\/models\/[a-z0-9-]{1,64}$/],
  ["GET", /^\/api\/vision\/status$/],
  ["POST", /^\/api\/vision\/(start|stop|pause|setup|calibrate)$/],
  ["GET", /^\/api\/vision\/(preview|cameras|actions)$/],
  ["GET", /^\/api\/online\/status$/],
  ["PUT", /^\/api\/online\/keys\/[a-z0-9_-]{1,32}$/],
  ["DELETE", /^\/api\/online\/keys\/[a-z0-9_-]{1,32}$/],
  ["GET", /^\/api\/documents$/],
  ["POST", /^\/api\/documents$/],
  ["POST", new RegExp(`^/api/documents/${ID}/(cancel|open)$`)],
  ["POST", /^\/api\/open-url$/],
  ["GET", /^\/api\/plugins$/],
  ["POST", /^\/api\/plugins\/import$/],
  ["POST", /^\/api\/plugins\/keys$/],
  ["DELETE", /^\/api\/plugins\/keys\/[0-9a-f]{16}$/],
  ["POST", /^\/api\/plugins\/[a-z0-9-]{2,41}\/enable$/],
  ["PUT", /^\/api\/plugins\/[a-z0-9-]{2,41}\/grants$/],
  ["DELETE", /^\/api\/plugins\/[a-z0-9-]{2,41}$/],
  ["POST", /^\/api\/documents\/recent\/open$/],
];

/** Commands can wait for the local model or the internet; everything else answers quickly. */
const LONG_ROUTES: ReadonlyArray<RegExp> = [
  /^\/api\/(command|confirm|undo|repeat)$/,
  new RegExp(`^/api/scenarios/${ID}/run$`),
  /^\/api\/apps\/discover$/,
];

export function routeTimeoutMs(method: string, path: string): number {
  return method === "POST" && LONG_ROUTES.some((re) => re.test(path)) ? 180_000 : 30_000;
}

export function isAllowedRoute(method: string, path: string): boolean {
  if (typeof method !== "string" || typeof path !== "string" || path.length > 300) return false;
  return ALLOWED_ROUTES.some(([m, re]) => m === method && re.test(path));
}
