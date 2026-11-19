import type { Heatmap, PlanRequest, PlanStatus, ReversePlace, SearchPlace } from './types';

function errorText(value: unknown, prefix = ''): string {
  if (typeof value === 'string') return prefix ? `${prefix}: ${value}` : value;
  if (Array.isArray(value)) return value.map(item => errorText(item, prefix)).filter(Boolean).join('; ');
  if (value && typeof value === 'object') return Object.entries(value).map(([key, item]) => errorText(item, prefix ? `${prefix}.${key}` : key)).filter(Boolean).join('; ');
  return '';
}
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  constructor(status: number, payload: unknown) {
    const detail = status === 429 ? 'Too many requests — wait a minute and try again.' :
      errorText(payload && typeof payload === 'object' && 'detail' in payload ? payload.detail : payload) || `Request failed (${status}).`;
    super(detail); this.name = 'ApiError'; this.status = status; this.detail = detail;
  }
}
export function apiUrl(path: string): string {
  // The backend returns relative /api paths, including heatmap_url.
  if (!path.startsWith('/api/') || path.startsWith('//')) throw new Error('Expected a relative /api/ path.');
  return `${(import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')}${path}`;
}
async function request<T>(path: string, signal?: AbortSignal, body?: PlanRequest): Promise<T> {
  const response = await fetch(apiUrl(path), { signal, ...(body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
  if (!response.ok) {
    let payload: unknown;
    try { payload = await response.json(); } catch { payload = { detail: response.statusText }; }
    throw new ApiError(response.status, payload);
  }
  return response.json() as Promise<T>;
}
export const geocode = (q: string, signal?: AbortSignal) => request<SearchPlace[]>(`/api/geocode?q=${encodeURIComponent(q)}&typeahead=true`, signal);
export const reverseGeocode = (lat: number, lon: number, signal?: AbortSignal) => request<ReversePlace>(`/api/reverse?lat=${lat}&lon=${lon}`, signal);
export const postPlan = (body: PlanRequest, signal?: AbortSignal) => request<PlanStatus>('/api/plan', signal, body);
export const getPlan = (id: string, signal?: AbortSignal) => request<PlanStatus>(`/api/plan/${encodeURIComponent(id)}`, signal);
export const fetchHeatmap = (url: string, signal?: AbortSignal) => request<Heatmap>(url, signal);
