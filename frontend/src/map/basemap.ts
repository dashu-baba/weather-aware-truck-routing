import type { StyleSpecification } from 'maplibre-gl';

export const BASEMAP_URL = 'https://tiles.openfreemap.org/styles/liberty';

export const blankStyle = (): StyleSpecification => ({
  version: 8,
  sources: {},
  layers: [{
    id: 'background',
    type: 'background',
    paint: { 'background-color': '#eef1f5' },
  }],
});

// Ported from the POC loadBasemap. Reuse the style response instead of fetching twice.
export async function loadBasemap(signal: AbortSignal): Promise<StyleSpecification> {
  const timeout = AbortSignal.timeout(5000);
  try {
    const response = await fetch(BASEMAP_URL, {
      signal: AbortSignal.any([signal, timeout]),
    });
    if (response.ok) return await response.json() as StyleSpecification;
  } catch {
    // Keep the map usable if the basemap is offline or times out.
  }
  return blankStyle();
}
