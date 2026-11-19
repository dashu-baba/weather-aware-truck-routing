import { describe, expect, it } from 'vitest';
import { checkpointFeatures, pointAtTime, routeLines, routePieces } from './geometry';
import type { Position } from '../api/types';
import { scoredResult, scoredRoute } from '../hooks/__tests__/scoredFixtures';
import { route } from '../hooks/__tests__/fixtures';

it('ports full routes to GeoJSON without swapping longitude/latitude', () => {
  const lines = routeLines([route]);
  expect(lines.features[0]).toEqual({
    type: 'Feature', properties: { id: 'A' },
    geometry: { type: 'LineString', coordinates: [[-96.797, 32.7767], [-84.388, 33.749]] },
  });
  expect(routeLines([])).toEqual({ type: 'FeatureCollection', features: [] });
});


describe('pointAtTime', () => {
  it.each<[number, Position]>([
    [-10, [-100, 30]], [0, [-100, 30]], [5, [-95, 35]], [10, [-90, 40]],
    [15, [-85, 40]], [30, [-70, 50]], [40, [-60, 60]], [100, [-60, 60]],
  ])('locates elapsed %i seconds without swapping longitude and latitude', (elapsed, expected) => {
    expect(pointAtTime(scoredRoute, elapsed)).toEqual(expected);
  });

  it('handles a one-point route and equal adjacent times without division by zero', () => {
    expect(pointAtTime({ ...scoredRoute, geometry: [[-100, 30]], times: [0] }, 100)).toEqual([-100, 30]);
    expect(pointAtTime({ ...scoredRoute, times: [0, 10, 10, 30] }, 10)).toEqual([-80, 40]);
  });

  it('rejects missing or misaligned geometry/times', () => {
    expect(() => pointAtTime({ ...scoredRoute, geometry: [] }, 0)).toThrow('aligned');
    expect(() => pointAtTime({ ...scoredRoute, times: [0] }, 0)).toThrow('aligned');
  });
});

describe('route pieces and checkpoints', () => {
  it('splits at interpolated checkpoint times, preserving interior vertices and the END checkpoint risk', () => {
    const pieces = routePieces({ ...scoredResult, routes: [scoredRoute] }, 25).features;
    expect(pieces).toHaveLength(4);
    expect(pieces.map(piece => piece.properties?.risk)).toEqual([1, 3, 4, 2]);
    expect(pieces.map(piece => piece.geometry.coordinates)).toEqual([
      [[-100, 30], [-95, 35]],
      [[-95, 35], [-90, 40], [-80, 40]],
      [[-80, 40], [-70, 50]],
      [[-70, 50], [-60, 60]],
    ]);
    expect(pieces.every(piece => piece.properties?.id === 'A')).toBe(true);
  });

  it('uses the selected interval and does not mutate the result', () => {
    const before = structuredClone(scoredResult);
    const pieces = routePieces(scoredResult, 50).features;
    expect(pieces).toHaveLength(2);
    expect(pieces[0].geometry.coordinates).toEqual(scoredRoute.geometry);
    expect(pieces.map(piece => piece.properties)).toEqual([{ id: 'A', risk: 2 }, { id: 'B', risk: 2 }]);
    expect(scoredResult).toEqual(before);
    expect(routePieces(scoredResult, 99).features).toEqual([]);
  });

  it('builds explicit [lon, lat] points and indexes them separately for each route', () => {
    const features = checkpointFeatures(scoredResult, 25).features;
    expect(features).toHaveLength(10);
    expect(features[1]).toEqual({ type: 'Feature', properties: { id: 'A', idx: 1, risk: 1 }, geometry: { type: 'Point', coordinates: [-95, 35] } });
    expect(features[5].properties).toEqual({ id: 'B', idx: 0, risk: 0 });
    expect(checkpointFeatures(scoredResult, 50).features).toHaveLength(4);
    expect(checkpointFeatures(scoredResult, 99).features).toEqual([]);
  });
});
