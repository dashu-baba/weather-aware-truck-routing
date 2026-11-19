import type { FeatureCollection, LineString } from 'geojson';
import type { RouteEntry } from '../api/types';

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
