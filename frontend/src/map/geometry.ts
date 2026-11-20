import type { FeatureCollection, LineString, Point } from 'geojson';
import type { PlanResult, Position, RouteEntry } from '../api/types';

// Ported from poc_reference/app.js. API geometry is already [longitude, latitude].
export function routeLines(routes: RouteEntry[]): FeatureCollection<LineString> {
  return {
    type: 'FeatureCollection',
    features: routes.map(route => ({
      type: 'Feature',
      properties: { id: route.id },
      geometry: { type: 'LineString', coordinates: route.geometry },
    })),
  };
}

// Ported from the POC: binary-search elapsed seconds and interpolate in [lon, lat].
export function pointAtTime(route: RouteEntry, elapsed: number): Position {
  const { geometry, times } = route;
  if (!geometry.length || geometry.length !== times.length) {
    throw new Error('Route geometry and times must be nonempty and aligned.');
  }
  if (elapsed <= times[0]) return geometry[0];
  if (elapsed >= times[times.length - 1]) return geometry[geometry.length - 1];

  let lo = 0;
  let hi = times.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= elapsed) lo = mid;
    else hi = mid;
  }
  const fraction = (elapsed - times[lo]) / Math.max(1e-9, times[hi] - times[lo]);
  return [
    geometry[lo][0] + (geometry[hi][0] - geometry[lo][0]) * fraction,
    geometry[lo][1] + (geometry[hi][1] - geometry[lo][1]) * fraction,
  ];
}

export function routePieces(result: PlanResult, interval: number): FeatureCollection<LineString> {
  const features: FeatureCollection<LineString>['features'] = [];
  for (const route of result.routes) {
    const checkpoints = route.by_interval[String(interval)]?.checkpoints ?? [];
    for (let index = 1; index < checkpoints.length; index++) {
      const from = checkpoints[index - 1].elapsed_s;
      const to = checkpoints[index].elapsed_s;
      const coordinates = [pointAtTime(route, from)];
      route.times.forEach((time, vertex) => {
        if (time > from && time < to) coordinates.push(route.geometry[vertex]);
      });
      coordinates.push(pointAtTime(route, to));
      // Each checkpoint's risk covers the miles since the preceding checkpoint.
      features.push({
        type: 'Feature',
        properties: { id: route.id, risk: checkpoints[index].risk },
        geometry: { type: 'LineString', coordinates },
      });
    }
  }
  return { type: 'FeatureCollection', features };
}

export function checkpointFeatures(result: PlanResult, interval: number): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: result.routes.flatMap(route =>
      (route.by_interval[String(interval)]?.checkpoints ?? []).map((checkpoint, index) => ({
        type: 'Feature' as const,
        properties: { id: route.id, idx: index, risk: checkpoint.risk },
        geometry: { type: 'Point' as const, coordinates: [checkpoint.lon, checkpoint.lat] },
      }))),
  };
}

// Room around the routes when zooming to them, so the legend (top right) and the time bar (bottom) never cover
// the start and end pins. Narrow maps get an even margin instead.
export function fitPadding(width: number): { top: number; right: number; bottom: number; left: number } {
  if (width >= 900) return { top: 80, right: 260, bottom: 130, left: 60 };
  if (width >= 600) return { top: 70, right: 200, bottom: 120, left: 40 };
  return { top: 60, right: 30, bottom: 110, left: 30 };
}
