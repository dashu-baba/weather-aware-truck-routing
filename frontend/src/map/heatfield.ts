import type { Heatmap, PlanResult, Position } from '../api/types';
import { classifyPixel, levelFor, type Hazard, type Level } from '../lib/risk';
import { LEVELS, RISK_COLORS } from './palette';

// The corridor weather image. It rasterises the heatmap grid in Web Mercator so it lines up with the basemap,
// and keeps a small cache of finished frames so moving the time slider never recomputes the same hour twice.
// Coordinates: the polygon is [lon, lat]; the grid is described by lat0/lon0 (the south-west cell centre).

export const HEAT_LAYERS = {
  risk: { title: 'Risk (with load rules)', labels: LEVELS },
  wind: { title: 'Wind (mph)', labels: ['<25', '25–<35', '35–<45', '45–<55', '≥55'] },
  // Gusts run well above sustained wind, so they get a scale 15 mph higher (NWS gust criteria sit 15–18 mph above
  // the sustained ones). Risk itself uses sustained wind; this layer is for seeing where the gusts are.
  gust: { title: 'Gust (mph, gust scale)', labels: ['<40', '40–<50', '50–<60', '60–<70', '≥70'] },
  rain: { title: 'Rain (in/hr)', labels: ['Light <0.10', '0.10–<0.25', '0.25–<0.50', '0.50–1.00', '>1.00'] },
  snow: { title: 'Snow (in/hr)', labels: ['Light <0.5', '0.5–<1.0', '1.0–<2.0', '2.0–3.0', '>3.0'] },
} as const;
export type HeatLayer = keyof typeof HEAT_LAYERS;
export const HEAT_LAYER_KEYS = Object.keys(HEAT_LAYERS) as HeatLayer[];

const CACHE_FRAMES = 60;
const MAX_PIXELS_PER_CELL = 8;
const MAX_SIDE_PX = 1024;

export const mercatorY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
export const latitudeAtY = (y: number) => ((2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180) / Math.PI;

// RGBA per level: Low is almost transparent, the rest are the risk colours at about 55% opacity.
const PALETTE = RISK_COLORS.map((hex, level) => [
  parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16), level === 0 ? 18 : 140,
] as const);

// Light rain and snow (below Moderate) are drawn in blue that strengthens with the amount, so a snow band is
// visible before it is risky. Dry pixels stay clear. Wind and gust keep the faint Low tint: there is always wind.
const LIGHT: Record<'rain' | 'snow', { trace: number; full: number; rgb: readonly [number, number, number] }> = {
  rain: { trace: 0.005, full: 0.1, rgb: [37, 99, 235] },
  snow: { trace: 0.02, full: 0.5, rgb: [56, 132, 214] },
};

function lightAlpha(layer: 'rain' | 'snow', value: number): number {
  const { trace, full } = LIGHT[layer];
  return value < trace ? 0 : Math.round(70 + 110 * Math.min(1, value / full));
}

// The swatch colour for one legend row.
export function legendColor(layer: HeatLayer, level: number): string {
  if (level === 0 && (layer === 'rain' || layer === 'snow')) return `rgb(${LIGHT[layer].rgb.join(', ')})`;
  return RISK_COLORS[level];
}

type Stencil = readonly [number, number, number, number, number, number, number, number]; // 4 cell indexes, 4 weights

export type HeatfieldInput = { meta: Pick<PlanResult['meta'], 'load_lb' | 'assumptions'>; heatmap: Heatmap };
export type HeatfieldOptions = {
  debug?: boolean;
  createCanvas?: (width: number, height: number) => HTMLCanvasElement;
  idle?: (task: () => void) => unknown;
  cancelIdle?: (handle: unknown) => void;
};
export type FrameTiming = { layer: HeatLayer; hour: number; cached: boolean; ms: number };

export function levelOfLayer(layer: HeatLayer, value: number | null): Level | null {
  if (value == null) return null;
  if (layer === 'risk') return value as Level;
  return levelFor(layer as Hazard, value);
}

const FORMAT_TIME = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });

// The text next to the cursor, for example "Gust 41 mph · High · Fri 10:00 PM".
export function hoverLabel(layer: HeatLayer, value: number, at: Date): string {
  const name = layer[0].toUpperCase() + layer.slice(1);
  const units = layer === 'wind' || layer === 'gust' ? ` ${Math.round(value)} mph`
    : layer === 'rain' || layer === 'snow' ? ` ${value.toFixed(3)} in/hr` : '';
  const level = levelOfLayer(layer, value);
  return `${name}${units} · ${level == null ? 'No data' : LEVELS[level]} · ${FORMAT_TIME.format(at)}`;
}

const defaultCanvas = (width: number, height: number) => {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  return canvas;
};

export function createHeatfield({ meta, heatmap }: HeatfieldInput, options: HeatfieldOptions = {}) {
  if (heatmap.mode !== 'hull' || !heatmap.grid || !heatmap.polygon?.length) {
    throw new Error('The heatmap is not available for this plan.');
  }
  const createCanvas = options.createCanvas ?? defaultCanvas;
  const idle = options.idle ?? ((task: () => void) => (window.requestIdleCallback ? window.requestIdleCallback(task) : window.setTimeout(task, 40)));
  const cancelIdle = options.cancelIdle ?? ((handle: unknown) => (window.cancelIdleCallback ? window.cancelIdleCallback(handle as number) : window.clearTimeout(handle as number)));

  const { lat0, lon0, step, nrows, ncols } = heatmap.grid;
  const hours = heatmap.hours;
  const west = lon0 - step / 2;
  const east = lon0 + (ncols - 0.5) * step;
  const south = lat0 - step / 2;
  const north = lat0 + (nrows - 0.5) * step;
  const topY = mercatorY(north);
  const bottomY = mercatorY(south);
  const scale = Math.min(MAX_PIXELS_PER_CELL, MAX_SIDE_PX / Math.max(nrows, ncols));
  const width = Math.max(1, Math.round(ncols * scale));
  const height = Math.max(1, Math.round(nrows * scale));
  // [lon, lat] corners, north-west first, clockwise: the order MapLibre's image and canvas sources expect.
  const coordinates: Position[] = [[west, north], [east, north], [east, south], [west, south]];
  const metric = meta.assumptions?.wind_metric ?? 'sustained';
  const cache = new Map<string, HTMLCanvasElement>();
  const timings: FrameTiming[] = [];
  let idleTask: unknown = null;

  const isLayer = (layer: string): layer is HeatLayer => layer in HEAT_LAYERS;

  function contains(lat: number, lon: number): boolean {
    let inside = false;
    const polygon = heatmap.polygon;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const [ax, ay] = polygon[j];
      const [bx, by] = polygon[i];
      const cross = (lon - ax) * (by - ay) - (lat - ay) * (bx - ax);
      if (Math.abs(cross) < 1e-10 && lon >= Math.min(ax, bx) && lon <= Math.max(ax, bx) && lat >= Math.min(ay, by) && lat <= Math.max(ay, by)) return true;
      if ((ay > lat) !== (by > lat) && lon < ax + ((lat - ay) * (bx - ax)) / (by - ay)) inside = !inside;
    }
    return inside;
  }

  // Which four cells surround a point and how much each counts. Row 0 is the south. Null outside the grid's bounding box.
  function stencil(lat: number, lon: number): Stencil | null {
    if (lat < south || lat > north || lon < west || lon > east) return null;
    const y = Math.max(0, Math.min(nrows - 1, (lat - lat0) / step));
    const x = Math.max(0, Math.min(ncols - 1, (lon - lon0) / step));
    const r = Math.floor(y);
    const c = Math.floor(x);
    const fy = y - r;
    const fx = x - c;
    const r1 = Math.min(r + 1, nrows - 1);
    const c1 = Math.min(c + 1, ncols - 1);
    return [r * ncols + c, r * ncols + c1, r1 * ncols + c, r1 * ncols + c1,
      (1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy];
  }

  // Cells without a forecast are skipped and the rest are renormalised, so a gap does not drag values towards zero.
  function interpolate(values: (number | null)[] | undefined, s: Stencil | null): number | null {
    if (!values || !s) return null;
    let sum = 0;
    let weight = 0;
    for (let k = 0; k < 4; k++) {
      const value = values[s[k]];
      const w = s[k + 4];
      if (value != null && w > 0) { sum += value * w; weight += w; }
    }
    return weight > 0 ? sum / weight : null;
  }

  function valueAt(layer: HeatLayer, hour: number, s: Stencil | null): number | null {
    const { vars } = heatmap;
    // Risk is never interpolated as integers: the weather is interpolated first, then classified for this load.
    if (layer !== 'risk') return interpolate(vars[layer]?.[hour], s);
    return classifyPixel(interpolate(vars.wind[hour], s), interpolate(vars.gust[hour], s),
      interpolate(vars.rain[hour], s), interpolate(vars.snow[hour], s), meta.load_lb, metric);
  }

  function sample(layer: HeatLayer, hour: number, lat: number, lon: number): number | null {
    if (!isLayer(layer) || hour < 0 || hour >= hours) return null;
    return valueAt(layer, hour, stencil(lat, lon));
  }

  // The geometry is the same for every frame, so each pixel's latitude (inverse Mercator) and weights are found once.
  const stencils: (Stencil | null)[] = new Array<Stencil | null>(width * height);
  for (let py = 0; py < height; py++) {
    const lat = latitudeAtY(topY + ((bottomY - topY) * (py + 0.5)) / height);
    for (let px = 0; px < width; px++) {
      stencils[py * width + px] = stencil(lat, west + ((east - west) * (px + 0.5)) / width);
    }
  }

  const polygonPath = new Path2D();
  heatmap.polygon.forEach(([lon, lat], i) => {
    const x = ((lon - west) / (east - west)) * width;
    const y = ((topY - mercatorY(lat)) / (topY - bottomY)) * height;
    if (i === 0) polygonPath.moveTo(x, y);
    else polygonPath.lineTo(x, y);
  });
  polygonPath.closePath();

  const staging = createCanvas(width, height);
  const stagingContext = staging.getContext('2d') as CanvasRenderingContext2D;
  const image = stagingContext.createImageData(width, height);

  function renderFrame(layer: HeatLayer, hour: number): HTMLCanvasElement {
    const started = performance.now();
    const key = `${layer}:${hour}`;
    let canvas = cache.get(key);
    const cached = canvas !== undefined;
    if (canvas) {
      cache.delete(key); // re-inserted below, so the Map's order is least recently used first
    } else {
      if (!isLayer(layer)) throw new Error('Choose a heatmap layer: risk, wind, gust, rain or snow.');
      if (!Number.isInteger(hour) || hour < 0 || hour >= hours) throw new Error(`Choose an hour from 0 to ${hours - 1}.`);
      const pixels = image.data;
      for (let i = 0; i < stencils.length; i++) {
        const value = valueAt(layer, hour, stencils[i]);
        const level = levelOfLayer(layer, value);
        const offset = i * 4;
        if (level == null || value == null) { pixels[offset + 3] = 0; continue; }
        if (level === 0 && (layer === 'rain' || layer === 'snow')) {
          const [r, g, b] = LIGHT[layer].rgb;
          pixels[offset] = r;
          pixels[offset + 1] = g;
          pixels[offset + 2] = b;
          pixels[offset + 3] = lightAlpha(layer, value);
          continue;
        }
        const [r, g, b, a] = PALETTE[level];
        pixels[offset] = r;
        pixels[offset + 1] = g;
        pixels[offset + 2] = b;
        pixels[offset + 3] = a;
      }
      stagingContext.putImageData(image, 0, 0);
      canvas = createCanvas(width, height);
      const context = canvas.getContext('2d') as CanvasRenderingContext2D;
      context.save();
      context.clip(polygonPath);
      context.drawImage(staging, 0, 0);
      context.restore();
    }
    cache.set(key, canvas);
    if (cache.size > CACHE_FRAMES) cache.delete(cache.keys().next().value as string);
    if (options.debug) {
      const ms = performance.now() - started;
      timings.push({ layer, hour, cached, ms });
      if (timings.length > 1000) timings.shift();
      console.debug(`[heatfield] ${cached ? 'cached' : 'cold'} ${key}: ${ms.toFixed(2)} ms`);
    }
    return canvas;
  }

  // While the browser is idle, render the hours the slider is most likely to reach next.
  function prerenderNeighbours(layer: HeatLayer, hour: number): void {
    if (idleTask != null) cancelIdle(idleTask);
    const queue = [hour + 1, hour - 1].filter(h => h >= 0 && h < hours);
    const next = () => {
      idleTask = idle(() => {
        const h = queue.shift();
        if (h !== undefined && !cache.has(`${layer}:${h}`)) renderFrame(layer, h);
        if (queue.length) next();
        else idleTask = null;
      });
    };
    if (queue.length) next();
  }

  return {
    sample, renderFrame, contains, coordinates, width, height, hours, prerenderNeighbours, timings,
    polygon: heatmap.polygon,
    start: heatmap.start, // the UTC time of forecast hour 0
    clearCache: () => cache.clear(),
    get cacheSize() { return cache.size; },
  };
}

export type Heatfield = ReturnType<typeof createHeatfield>;
