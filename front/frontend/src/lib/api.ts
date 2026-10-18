import { useAuthStore } from '@/stores/auth';
import { useSystemStore } from '@/stores/system';
import type { ApiErrorBody } from '@/types/api';

export const API_BASE: string = import.meta.env.VITE_API_BASE || '/api/v1';

export class ApiError extends Error {
  status: number;
  code: string;
  detail?: Record<string, unknown>;
  constructor(status: number, code: string, message: string, detail?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;
interface Options {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  form?: FormData;
  query?: Query;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

export function buildUrl(path: string, query?: Query) {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  if (!query) return url;
  const qs = Object.entries(query)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  return qs ? `${url}${url.includes('?') ? '&' : '?'}${qs}` : url;
}

export function authHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parseError(res: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null;
  try { body = (await res.json()) as ApiErrorBody; } catch { /* non-json */ }
  const code = body?.error?.code ?? `HTTP_${res.status}`;
  const message = body?.error?.message ?? res.statusText ?? '요청 실패';
  return new ApiError(res.status, code, message, body?.error?.detail);
}

export async function rawRequest(path: string, opts: Options = {}): Promise<Response> {
  const headers: Record<string, string> = { ...authHeaders(), ...(opts.headers ?? {}) };
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body); }

  const res = await fetch(buildUrl(path, opts.query), { method: opts.method ?? 'GET', headers, body, signal: opts.signal });
  if (!res.ok) {
    const err = await parseError(res);
    if (err.status === 401) useAuthStore.getState().logout();
    if (err.status === 503 && (err.code === 'LLM_UNAVAILABLE' || err.code === 'OCR_UNAVAILABLE')) {
      useSystemStore.getState().setAiDown(err.code === 'LLM_UNAVAILABLE' ? 'LLM' : 'OCR');
    }
    throw err;
  }
  return res;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const res = await rawRequest(path, opts);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export async function downloadFile(path: string, filename: string, query?: Query) {
  const res = await rawRequest(path, { query });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return `${e.message} (${e.code})`;
  if (e instanceof Error) return e.message;
  return String(e);
}
