import { expect, it } from 'vitest';
import { routeLines } from './geometry';
import { route } from '../hooks/__tests__/fixtures';

it('ports full routes to GeoJSON without swapping longitude/latitude', () => {
  const lines = routeLines([route]);
  expect(lines.features[0]).toEqual({
    type: 'Feature', properties: { id: 'A' },
    geometry: { type: 'LineString', coordinates: [[-96.797, 32.7767], [-84.388, 33.749]] },
  });
  expect(routeLines([])).toEqual({ type: 'FeatureCollection', features: [] });
});
