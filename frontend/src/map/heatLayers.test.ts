import type { Map } from 'maplibre-gl';
import { describe, expect, it, vi } from 'vitest';
import { drawHeatFrame, hideHeatfield, showHeatfield } from './heatLayers';
import type { Heatfield } from './heatfield';

function fakeMap() {
  const calls: string[] = [];
  const sources = new globalThis.Map<string, unknown>();
  const layers = new globalThis.Map<string, Record<string, unknown>>();
  const canvasSource = { play: vi.fn(() => calls.push('play')), pause: vi.fn(() => calls.push('pause')) };
  const map = {
    addSource: (id: string, spec: unknown) => { calls.push(`addSource ${id}`); sources.set(id, spec); },
    addLayer: (spec: { id: string }, before?: string) => { calls.push(`addLayer ${spec.id} before ${before}`); layers.set(spec.id, spec as Record<string, unknown>); },
    getLayer: (id: string) => layers.get(id),
    getSource: (id: string) => (sources.has(id) ? (id === 'heatfield' ? canvasSource : sources.get(id)) : undefined),
    removeLayer: (id: string) => { calls.push(`removeLayer ${id}`); layers.delete(id); },
    removeSource: (id: string) => { calls.push(`removeSource ${id}`); sources.delete(id); },
    triggerRepaint: () => calls.push('repaint'),
  };
  return { map: map as unknown as Map, calls, sources, layers };
}

const field = {
  coordinates: [[-110, 50], [-70, 50], [-70, 10], [-110, 10]],
  polygon: [[-100, 20], [-80, 20], [-80, 40], [-100, 20]],
} as unknown as Heatfield;
const canvas = {} as HTMLCanvasElement;

describe('showHeatfield', () => {
  it('adds the image and the corridor outline under the route layers', () => {
    const { map, calls, sources, layers } = fakeMap();
    showHeatfield(map, field, canvas);
    expect(calls).toEqual([
      'addSource heatfield', 'addSource corridor',
      'addLayer heatfield before route-casing', 'addLayer corridor-outline before route-casing',
    ]);
    expect(sources.get('heatfield')).toMatchObject({ type: 'canvas', animate: false, coordinates: field.coordinates });
    expect(layers.get('heatfield')).toMatchObject({ type: 'raster', paint: { 'raster-opacity': 0.85, 'raster-fade-duration': 0 } });
    expect(layers.get('corridor-outline')).toMatchObject({ type: 'line' });
  });

  it('draws the corridor from the polygon in [lon, lat] order', () => {
    const { map, sources } = fakeMap();
    showHeatfield(map, field, canvas);
    expect(sources.get('corridor')).toMatchObject({
      type: 'geojson', data: { geometry: { type: 'Polygon', coordinates: [field.polygon] } },
    });
  });

  it('replaces what was there instead of failing on a second plan', () => {
    const { map, calls } = fakeMap();
    showHeatfield(map, field, canvas);
    calls.length = 0;
    showHeatfield(map, field, canvas);
    expect(calls.slice(0, 4)).toEqual(['removeLayer heatfield', 'removeLayer corridor-outline', 'removeSource heatfield', 'removeSource corridor']);
    expect(calls).toContain('addLayer heatfield before route-casing');
  });
});

describe('hideHeatfield', () => {
  it('removes the layers before their sources and is harmless when nothing is shown', () => {
    const { map, calls } = fakeMap();
    expect(() => hideHeatfield(map)).not.toThrow();
    expect(calls).toEqual([]);
    showHeatfield(map, field, canvas);
    calls.length = 0;
    hideHeatfield(map);
    expect(calls).toEqual(['removeLayer heatfield', 'removeLayer corridor-outline', 'removeSource heatfield', 'removeSource corridor']);
  });
});

describe('drawHeatFrame', () => {
  it('copies the frame into the shared canvas and uploads it once, without rebuilding any source', () => {
    const { map, calls } = fakeMap();
    showHeatfield(map, field, canvas);
    calls.length = 0;
    const context = { clearRect: vi.fn(), drawImage: vi.fn() };
    const target = { width: 16, height: 12, getContext: () => context } as unknown as HTMLCanvasElement;
    const frame = {} as HTMLCanvasElement;
    const renderFrame = vi.fn(() => frame);
    drawHeatFrame(map, { renderFrame } as unknown as Heatfield, target, 'gust', 7);
    expect(renderFrame).toHaveBeenCalledWith('gust', 7);
    expect(context.clearRect).toHaveBeenCalledWith(0, 0, 16, 12);
    expect(context.drawImage).toHaveBeenCalledWith(frame, 0, 0);
    expect(calls).toEqual(['play', 'pause', 'repaint']);
  });
});
