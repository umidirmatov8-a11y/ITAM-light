import type { ApiReply } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

function errorMessage(reply: ApiReply): string {
  const body = reply.body;
  if (body && typeof body === "object") {
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) {
      const first = body.detail[0];
      return `${(first.loc ?? []).slice(1).join(".")}: ${first.msg}`;
    }
  }
  if (reply.status === 0 || reply.status === 503) return "Ядро A.R.C. недоступно";
  return `Ошибка ${reply.status}`;
}

export async function api<T = any>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  if (!window.arc) throw new ApiError(0, "Интерфейс запущен вне A.R.C. (нет моста preload)");
  const reply = await window.arc.api(method, path, body);
  if (reply.status >= 200 && reply.status < 300) return reply.body as T;
  throw new ApiError(reply.status, errorMessage(reply), reply.body?.error);
}

export const get = <T = any>(path: string) => api<T>("GET", path);
export const post = <T = any>(path: string, body?: unknown) => api<T>("POST", path, body ?? {});
export const put = <T = any>(path: string, body: unknown) => api<T>("PUT", path, body);
export const del = <T = any>(path: string) => api<T>("DELETE", path);
