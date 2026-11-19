import type { Heatmap, PlanRequest, PlanResult, PlanStatus, RouteEntry } from '../../api/types';

export const request: PlanRequest = {
  origin: { label: 'Dallas, TX', lat: 32.7767, lon: -96.797 },
  destination: { label: 'Atlanta, GA', lat: 33.749, lon: -84.388 },
  departure: '2026-11-20T08:00:00Z',
  load_lb: 42000,
};

export const route: RouteEntry = {
  id: 'A', label: 'Route A', source: 'tomtom',
  summary: { distance_mi: 786, duration_s: 49000, departure: request.departure, arrival: '2026-11-20T21:36:40Z' },
  geometry: [[-96.797, 32.7767], [-84.388, 33.749]], times: [0, 49000],
};

export const result: PlanResult = {
  meta: {
    departure: request.departure, load_lb: 42000, gross_weight_kg: 34927,
    intervals: [10, 25, 50], default_interval: 25,
    levels: ['Low', 'Moderate', 'High', 'Severe', 'No Travel'], warnings: [],
    assumptions: { wind_metric: 'sustained', truck_tare_lb: 35000 },
  },
  origin: request.origin, destination: request.destination,
  routes: [{ ...route, by_interval: {} }],
  recommendation: { '25': { best: 'A', order: ['A'], reason: 'shorter travel time', all_blocked: false } },
};

export function plan(overrides: Partial<PlanStatus> = {}): PlanStatus {
  return {
    plan_id: 'test-plan', status: 'weather', routes: [route],
    progress: { stage: 'checkpoints_25', done: 20, total: 100, percent: 20, queued: false },
    partial: null, result: null, heatmap_url: null, error: null, poll_after_ms: 1500,
    ...overrides,
  };
}

export const donePlan = () => plan({ status: 'done', result, poll_after_ms: null, heatmap_url: '/api/plan/test-plan/heatmap' });
export const heatmap: Heatmap = {
  mode: 'hull', start: request.departure, hours: 1, polygon: [[-97, 32], [-96, 32], [-96, 33], [-97, 32]],
  grid: { lat0: 32, lon0: -97, step: 0.4, nrows: 1, ncols: 1 },
  vars: { risk: [[0]], wind: [[10]], gust: [[12]], rain: [[0]], snow: [[0]], u: [[0]], v: [[0]] },
};
