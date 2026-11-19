import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiUrl, fetchHeatmap, geocode, getPlan, postPlan, reverseGeocode } from './client';
import type { PlanRequest } from './types';
const body: PlanRequest = { origin: { label: 'A', lat: 1, lon: 2 }, destination: { label: 'B', lat: 3, lon: 4 }, departure: '2026-11-20T00:00:00Z', load_lb: 42000 };
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
describe('API client', () => {
  it.each([200, 202])('accepts POST %i', async status => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'weather' }), { status })));
    expect(await postPlan(body)).toEqual({ status: 'weather' });
  });
  it('prefixes every path, including heatmap', async () => {
    vi.stubEnv('VITE_API_URL', 'https://our-backend.example');
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}'))); vi.stubGlobal('fetch', fetch);
    await geocode('Dallas'); await reverseGeocode(1, 2); await postPlan(body); await getPlan('id'); await fetchHeatmap('/api/plan/id/heatmap');
    expect(fetch.mock.calls.map(call => call[0])).toEqual(['https://our-backend.example/api/geocode?q=Dallas&typeahead=true','https://our-backend.example/api/reverse?lat=1&lon=2','https://our-backend.example/api/plan','https://our-backend.example/api/plan/id','https://our-backend.example/api/plan/id/heatmap']);
    expect(() => apiUrl('https://elsewhere.example/api/plan')).toThrow();
  });
  it('joins DRF errors and preserves detail/status', () => {
    const error = new ApiError(400, { origin: { lat: ['Invalid latitude'] }, load_lb: ['Too heavy'] });
    expect(error.detail).toBe('origin.lat: Invalid latitude; load_lb: Too heavy'); expect(error.status).toBe(400);
    expect(new ApiError(502, { detail: 'Routing unavailable' }).message).toBe('Routing unavailable');
    expect(new ApiError(429, {}).detail).toBe('Too many requests — wait a minute and try again.');
  });
});
