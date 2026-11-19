import type { Map } from 'maplibre-gl';
import { parseUtc } from '../lib/format';
import { hoverLabel, type Heatfield, type HeatLayer } from './heatfield';

type Size = { width: number; height: number };
const OFFSET_PX = 12;

// Keep the readout beside the cursor and inside the map: flip to the other side of the cursor at an edge.
export function placeTooltip(point: { x: number; y: number }, tip: Size, box: Size): { left: number; top: number } {
  let left = point.x + OFFSET_PX;
  let top = point.y + OFFSET_PX;
  if (left + tip.width > box.width) left = point.x - OFFSET_PX - tip.width;
  if (top + tip.height > box.height) top = point.y - OFFSET_PX - tip.height;
  return { left: Math.max(0, left), top: Math.max(0, top) };
}

export type HoverContext = { field: Heatfield; layer: HeatLayer; hour: number; start: string };

// The value under the cursor for the layer and hour on screen. Updates are throttled to one per animation frame,
// and the readout is hidden outside the corridor, while the map moves and when the cursor leaves the map.
export function attachHover(map: Map, tooltip: HTMLElement, getContext: () => HoverContext | null) {
  let cursor: { lat: number; lng: number; x: number; y: number } | null = null;
  let pending: number | null = null;

  function update(): void {
    const context = getContext();
    const value = cursor && context && context.field.contains(cursor.lat, cursor.lng)
      ? context.field.sample(context.layer, context.hour, cursor.lat, cursor.lng) : null;
    if (!cursor || !context || value == null) { tooltip.hidden = true; return; }
    const at = new Date(parseUtc(context.start).getTime() + context.hour * 3_600_000);
    tooltip.textContent = hoverLabel(context.layer, value, at);
    tooltip.hidden = false;
    const canvas = map.getCanvas();
    const { left, top } = placeTooltip(cursor, { width: tooltip.offsetWidth, height: tooltip.offsetHeight },
      { width: canvas.clientWidth, height: canvas.clientHeight });
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  const onMove = (event: { lngLat: { lat: number; lng: number }; point: { x: number; y: number } }) => {
    cursor = { lat: event.lngLat.lat, lng: event.lngLat.lng, x: event.point.x, y: event.point.y };
    if (pending != null) return;
    pending = requestAnimationFrame(() => { pending = null; update(); });
  };
  const clear = () => { cursor = null; update(); };

  map.on('mousemove', onMove);
  map.on('movestart', clear);
  map.getCanvas().addEventListener('mouseleave', clear);

  return {
    update,
    detach() {
      map.off('mousemove', onMove);
      map.off('movestart', clear);
      map.getCanvas().removeEventListener('mouseleave', clear);
      if (pending != null) cancelAnimationFrame(pending);
    },
  };
}
