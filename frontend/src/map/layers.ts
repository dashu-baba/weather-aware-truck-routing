import type { Map } from 'maplibre-gl';

// Ported from the POC's initial full-route layer; weather risk layers come in phase 4.
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
        'A', '#1f5eff', 'B', '#0f9d8a', 'C', '#b04fd1', '#888'],
      'line-width': 7,
      'line-opacity': 0.85,
    },
  });
}
