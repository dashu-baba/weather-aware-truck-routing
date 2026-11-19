import type { ExpressionSpecification, Map } from 'maplibre-gl';
import { RISK_COLORS, ROUTE_COLORS } from './palette';

// Ported from the POC. Sources and layers are installed once, when the map loads.
export function addRouteLayers(map: Map): void {
  map.addSource('route-casing', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  });
  map.addLayer({
    id: 'route-casing',
    type: 'line',
    source: 'route-casing',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ['match', ['get', 'id'],
        'A', ROUTE_COLORS.A, 'B', ROUTE_COLORS.B, 'C', ROUTE_COLORS.C, '#888'],
      'line-width': 7,
      'line-opacity': 0.85,
    },
  });
}

export function addResultLayers(map: Map): void {
  const riskColor: ExpressionSpecification = ['match', ['get', 'risk'],
    0, RISK_COLORS[0], 1, RISK_COLORS[1], 2, RISK_COLORS[2],
    3, RISK_COLORS[3], 4, RISK_COLORS[4], '#999'];
  for (const id of ['route-risk', 'checkpoints']) {
    map.addSource(id, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  map.addLayer({
    id: 'route-risk', type: 'line', source: 'route-risk',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': riskColor },
  });
  map.addLayer({
    id: 'checkpoints', type: 'circle', source: 'checkpoints',
    paint: { 'circle-color': riskColor, 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5 },
  });
}

// Focus changes only expressions, never GeoJSON, map bounds, or network requests.
export function applyRouteFocus(map: Pick<Map, 'setPaintProperty' | 'setLayoutProperty'>, focusId: string | null): void {
  const focused: ExpressionSpecification = ['==', ['get', 'id'], focusId ?? ''];
  const noFocus = focusId === null;
  map.setPaintProperty('route-casing', 'line-width', ['case', focused, 11, 7]);
  map.setPaintProperty('route-casing', 'line-opacity', ['case', focused, 0.85, noFocus ? 0.85 : 0.25]);
  map.setLayoutProperty('route-casing', 'line-sort-key', ['case', focused, 1, 0]);
  map.setPaintProperty('route-risk', 'line-width', ['case', focused, 5, 3]);
  map.setPaintProperty('route-risk', 'line-opacity', ['case', focused, 1, noFocus ? 1 : 0.45]);
  map.setLayoutProperty('route-risk', 'line-sort-key', ['case', focused, 1, 0]);
  map.setPaintProperty('checkpoints', 'circle-radius', ['case', focused, 5, 3]);
  map.setPaintProperty('checkpoints', 'circle-opacity', ['case', focused, 1, noFocus ? 1 : 0.5]);
  map.setPaintProperty('checkpoints', 'circle-stroke-opacity', ['case', focused, 1, noFocus ? 1 : 0.5]);
  map.setLayoutProperty('checkpoints', 'circle-sort-key', ['case', focused, 1, 0]);
}
