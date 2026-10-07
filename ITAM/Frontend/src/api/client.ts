import axios, { AxiosError } from 'axios';

/** Unified API error (backend envelope: { success:false, error:{ code, message, details } }). */
export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;
  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  xsrfCookieName: 'XSRF-TOKEN',
  xsrfHeaderName: 'X-XSRF-TOKEN',
  withXSRFToken: true,
  paramsSerializer: { indexes: null },
});

type Listener = (e: ApiError) => void;
const listeners: Listener[] = [];
export const onApiError = (l: Listener) => {
  listeners.push(l);
  return () => {
    listeners.splice(listeners.indexOf(l), 1);
  };
};

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError<any>) => {
    const status = error.response?.status ?? 0;
    let data = error.response?.data;
    if (data instanceof Blob) {
      try {
        data = JSON.parse(await data.text());
      } catch {
        data = undefined;
      }
    }
    const body = data?.error;
    const err = new ApiError(
      body?.code ?? (status === 0 ? 'NETWORK' : `HTTP_${status}`),
      body?.message ?? (status === 0 ? 'Сервер недоступен' : error.message),
      status,
      body?.details,
    );
    listeners.forEach((l) => l(err));
    return Promise.reject(err);
  },
);

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export const get = async <T,>(url: string, params?: Record<string, unknown>) => (await api.get<T>(url, { params: clean(params) })).data;
export const post = async <T,>(url: string, body?: unknown) => (await api.post<T>(url, body ?? {})).data;
export const put = async <T,>(url: string, body?: unknown) => (await api.put<T>(url, body ?? {})).data;
export const del = async <T,>(url: string) => (await api.delete<T>(url)).data;

export const upload = async <T,>(url: string, file: File, fields?: Record<string, string | boolean | undefined>) => {
  const form = new FormData();
  form.append('file', file);
  Object.entries(fields ?? {}).forEach(([k, v]) => v !== undefined && form.append(k, String(v)));
  return (await api.post<T>(url, form, { headers: { 'Content-Type': 'multipart/form-data' } })).data;
};

/** Downloads a file (GET or POST) and triggers the browser save dialog. */
export const download = async (url: string, params?: Record<string, unknown>, method: 'get' | 'post' = 'get', body?: unknown) => {
  const res = await api.request<Blob>({ url, method, params: clean(params), data: body, responseType: 'blob' });
  const cd = res.headers['content-disposition'] as string | undefined;
  let name = 'download';
  const m = cd && (/filename\*=UTF-8''([^;]+)/i.exec(cd) ?? /filename="?([^";]+)"?/i.exec(cd));
  if (m) name = decodeURIComponent(m[1]);
  const href = URL.createObjectURL(res.data);
  const a = document.createElement('a');
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 2000);
};

/** Opens a file inline (PDF/image) in a new tab via a blob URL (keeps cookies/session). */
export const openInline = async (url: string, params?: Record<string, unknown>) => {
  const res = await api.get<Blob>(url, { params: clean({ ...params, inline: true }), responseType: 'blob' });
  const href = URL.createObjectURL(res.data);
  window.open(href, '_blank', 'noopener');
  setTimeout(() => URL.revokeObjectURL(href), 60000);
};

export function clean(params?: Record<string, unknown>) {
  if (!params) return undefined;
  const out: Record<string, unknown> = {};
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return;
    out[k] = v;
  });
  return out;
}
