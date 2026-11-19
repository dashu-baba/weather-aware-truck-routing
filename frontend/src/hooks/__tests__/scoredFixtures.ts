import type { Checkpoint, PlanResult, ScoredRoute } from '../../api/types';
import { result, route } from './fixtures';

export function checkpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    mile: 0, lat: 30, lon: -100, elapsed_s: 0, eta: '2026-11-20T08:00:00Z', segment_mi: 0,
    weather: { time: '2026-11-20T08:00', wind_mph: 36, gust_mph: 42, rain_in: 0.12, snow_in: 0 },
    risk: 0, levels: { wind: 2, rain: 1, snow: 0 }, reasons: [],
    ...overrides,
  };
}

export const checkpoints = [
  checkpoint(),
  checkpoint({ mile: 5, lat: 35, lon: -95, elapsed_s: 5, segment_mi: 5, risk: 1 }),
  checkpoint({ mile: 20, lat: 40, lon: -80, elapsed_s: 20, segment_mi: 15, risk: 3 }),
  checkpoint({ mile: 30, lat: 50, lon: -70, elapsed_s: 30, segment_mi: 10, risk: 4 }),
  checkpoint({ mile: 40, lat: 60, lon: -60, elapsed_s: 40, segment_mi: 10, risk: 2 }),
];

export const scoredRoute: ScoredRoute = {
  ...route,
  geometry: [[-100, 30], [-90, 40], [-80, 40], [-60, 60]],
  times: [0, 10, 20, 40],
  by_interval: {
    '25': {
      checkpoints,
      score: { no_travel_mi: 10, severe_mi: 15, high_mi: 10, avg_risk: 2.625, duration_s: 49000, max_risk: 4, drivable: false },
    },
    '50': {
      checkpoints: [checkpoint(), checkpoint({ elapsed_s: 40, mile: 40, segment_mi: 40, risk: 2 })],
      score: { no_travel_mi: 0, severe_mi: 0, high_mi: 40, avg_risk: 2, duration_s: 49000, max_risk: 2, drivable: true },
    },
  },
};

export const scoredResult: PlanResult = {
  ...result,
  routes: [scoredRoute, { ...scoredRoute, id: 'B', label: 'Route B' }],
  recommendation: {
    '25': { best: 'B', order: ['B', 'A'], reason: 'fewer Severe miles', all_blocked: true },
    '50': { best: 'A', order: ['A', 'B'], reason: 'shorter travel time', all_blocked: false },
  },
};
