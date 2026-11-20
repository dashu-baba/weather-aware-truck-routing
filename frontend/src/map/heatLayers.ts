import type { CanvasSource, LayerSpecification, Map } from 'maplibre-gl';
import type { Position } from '../api/types';
import type { Heatfield, HeatLayer } from './heatfield';

// Weather sits below basemap roads; route overlays remain above the basemap.
const IMAGE = 'heatfield';
const CORRIDOR = 'corridor';
const OUTLINE = 'corridor-outline';
export function weatherBeforeId(layers: readonly LayerSpecification[]): string | undefined {
  return layers.find(layer => 'source-layer' in layer && layer['source-layer'] === 'transportation')?.id
    ?? layers.find(layer => layer.type === 'symbol')?.id;
}

type LayerMap = Pick<Map, 'getStyle' | 'addSource' | 'addLayer' | 'getLayer' | 'getSource' | 'removeLayer' | 'removeSource'>;

export function hideHeatfield(map: LayerMap): void {
  for (const id of [IMAGE, OUTLINE]) if (map.getLayer(id)) map.removeLayer(id);
  for (const id of [IMAGE, CORRIDOR]) if (map.getSource(id)) map.removeSource(id);
}

export function showHeatfield(
  map: LayerMap, field: Pick<Heatfield, 'coordinates' | 'polygon'>, canvas: HTMLCanvasElement,
): void {
  hideHeatfield(map); // a new plan replaces the previous image
  const beforeId = weatherBeforeId(map.getStyle().layers);
  const coordinates = field.coordinates as [Position, Position, Position, Position];
  map.addSource(IMAGE, { type: 'canvas', canvas, coordinates, animate: false });
  map.addSource(CORRIDOR, {
    type: 'geojson',
    data: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [field.polygon] } },
  });
  map.addLayer({
    id: IMAGE, type: 'raster', source: IMAGE,
    paint: { 'raster-opacity': 0.7, 'raster-fade-duration': 0, 'raster-resampling': 'linear' },
  }, beforeId);
  map.addLayer({
    id: OUTLINE, type: 'line', source: CORRIDOR,
    paint: { 'line-color': '#6b7280', 'line-width': 1.5, 'line-dasharray': [4, 3] },
  }, beforeId);
}

// Changing the hour or the layer only swaps the pixels of one canvas: no GeoJSON is rebuilt and nothing is requested.
export function drawHeatFrame(
  map: Pick<Map, 'getSource' | 'triggerRepaint'>, field: Pick<Heatfield, 'renderFrame'>,
  canvas: HTMLCanvasElement, layer: HeatLayer, hour: number,
): void {
  const frame = field.renderFrame(layer, hour);
  const context = canvas.getContext('2d');
  if (!context) return;
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(frame, 0, 0);
  // play() then pause() uploads the new pixels once, without starting a repaint loop.
  const source = map.getSource<CanvasSource>(IMAGE);
  source?.play();
  source?.pause();
  map.triggerRepaint();
}
