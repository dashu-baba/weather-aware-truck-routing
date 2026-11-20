import type { CanvasSource, Map } from 'maplibre-gl';
import type { Position } from '../api/types';

// Wind particles, ported from the POC (poc/frontend/particles.js). They move with the sustained wind; the Gust layer
// changes the background, never the velocity. Particles live in the heatmap's own pixel grid and are drawn on a
// canvas the map shows as a geographic image, so they pan and zoom with the map. Speed on screen is the same at
// every zoom, brightness and width grow with wind speed, and new particles fade in. No requests are made.

export type WindField = {
  width: number;
  height: number;
  seeds: number[]; // pixel indexes inside the corridor where particles may start
  northPixelScale: number;
  containsPixel(x: number, y: number): boolean;
  vectorAtPixel(x: number, y: number, hour: number, out: (number | null)[]): (number | null)[];
};

export const SPEED_PX_PER_MPH = 0.04; // screen pixels per 60 Hz frame per mph
const SPEED_BINS = 6;
const FADE_FRAMES = 12;
const SOURCE = 'wind-particles';

type Group = { path: Path2D | null; count: number; strength: number; alphaSum: number; alpha: number };
type Options = {
  debug?: boolean;
  count?: number;
  random?: () => number;
  createCanvas?: () => HTMLCanvasElement;
  createPath?: () => Path2D;
};

export function createWindParticles(field: WindField, options: Options = {}) {
  const { debug = false, count = 3000, random = Math.random } = options;
  const createPath = options.createPath ?? (() => new Path2D());
  const resolution = Math.min(2, 2048 / Math.max(field.width, field.height));
  const canvas = options.createCanvas?.() ?? document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(field.width * resolution));
  canvas.height = Math.max(1, Math.round(field.height * resolution));
  const scaleX = canvas.width / field.width;
  const scaleY = canvas.height / field.height;
  const dpr = window.devicePixelRatio || 1;
  const ctx = canvas.getContext('2d') as CanvasRenderingContext2D;
  const x = new Float64Array(count);
  const y = new Float64Array(count);
  const age = new Float32Array(count);
  const lifespan = new Float32Array(count);
  const speedAt = new Float32Array(count);
  const bucketAt = new Uint8Array(count);
  const velocity: (number | null)[] = [0, 0];
  const timings: number[] = [];
  // Six speed buckets, split by age only during the twelve-frame fade-in, so 3,000 trails need few strokes.
  const groups: Group[] = Array.from({ length: SPEED_BINS * (FADE_FRAMES + 1) },
    () => ({ path: null, count: 0, strength: 0, alphaSum: 0, alpha: 0 }));
  let raf: number | null = null;
  let enabled = true;
  let windLayer = false;
  let hour = 0;
  let screenPerCanvasPx = 1;
  let source: CanvasSource | null = null;
  let last: number | null = null;
  let frameCount = 0;
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const contains = (px: number, py: number) => field.containsPixel(px / scaleX, py / scaleY);

  function respawn(i: number) {
    const seed = field.seeds[Math.floor(random() * field.seeds.length)] ?? 0;
    x[i] = ((seed % field.width) + 0.5) * scaleX;
    y[i] = (Math.floor(seed / field.width) + 0.5) * scaleY;
    age[i] = 0;
    lifespan[i] = 120 + random() * 120;
    speedAt[i] = 0;
  }
  for (let i = 0; i < count; i++) { respawn(i); age[i] = random() * lifespan[i]; }

  function step(dt = 1): number {
    const start = performance.now();
    ctx.globalCompositeOperation = 'destination-out';
    ctx.fillStyle = `rgba(0,0,0,${1 - Math.pow(0.94, dt)})`;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.globalCompositeOperation = 'source-over';
    for (const g of groups) { g.path = null; g.count = 0; g.strength = 0; g.alphaSum = 0; g.alpha = 0; }
    for (let i = 0; i < count; i++) {
      if (age[i] >= lifespan[i] || !contains(x[i], y[i])) { respawn(i); continue; }
      field.vectorAtPixel(x[i] / scaleX, y[i] / scaleY, hour, velocity);
      const [u, v] = velocity;
      if (u == null || v == null) { respawn(i); continue; }
      const speed = Math.hypot(u, v);
      const strength = Math.min(1, speed / 35);
      const drop = 0.002 + 0.01 * strength;
      if (random() < 1 - Math.pow(1 - drop, dt)) { respawn(i); continue; }
      // Correct Mercator heading, but a length in screen pixels that does not depend on the zoom.
      const dx = u;
      const dy = (-v * field.northPixelScale * scaleY) / scaleX;
      const length = Math.hypot(dx, dy);
      const displacement = (speed * SPEED_PX_PER_MPH / screenPerCanvasPx) * dt;
      const factor = length > 0 ? displacement / length : 0;
      const nx = x[i] + dx * factor;
      const ny = y[i] + dy * factor;
      if (!contains(nx, ny)) { respawn(i); continue; }
      const speedBin = Math.min(SPEED_BINS - 1, Math.floor(strength * SPEED_BINS));
      const fadeBin = Math.min(FADE_FRAMES, Math.floor(age[i]));
      const bucket = speedBin * (FADE_FRAMES + 1) + fadeBin;
      const g = groups[bucket];
      if (!g.path) g.path = createPath();
      g.path.moveTo(x[i], y[i]);
      g.path.lineTo(nx, ny);
      g.count++;
      g.strength += strength;
      g.alphaSum += (0.12 + 0.78 * strength) * Math.min(1, age[i] / FADE_FRAMES);
      bucketAt[i] = bucket;
      speedAt[i] = speed;
      x[i] = nx;
      y[i] = ny;
      age[i] += dt;
    }
    for (const g of groups) {
      if (!g.count || !g.path) continue;
      g.alpha = g.alphaSum / g.count;
      ctx.strokeStyle = `rgba(255,255,255,${g.alpha})`;
      ctx.lineWidth = (0.6 + g.strength / g.count) * dpr;
      ctx.stroke(g.path);
    }
    const ms = performance.now() - start;
    if (debug) {
      timings.push(ms);
      if (timings.length > 1000) timings.shift();
      if (frameCount++ % 60 === 0) console.debug(`[particles] ${count} particles: ${ms.toFixed(2)} ms`);
    }
    return ms;
  }

  const shouldRun = () => enabled && windLayer && !document.hidden && !reducedMotion?.matches && field.seeds.length > 0;

  function animate(now: number) {
    raf = null;
    if (!shouldRun()) return;
    const dt = last == null ? 1 : Math.min(2, Math.max(0.1, (now - last) / (1000 / 60)));
    last = now;
    step(dt);
    raf = requestAnimationFrame(animate);
  }

  function sync() {
    if (shouldRun()) {
      if (raf == null) { last = null; source?.play(); raf = requestAnimationFrame(animate); }
    } else {
      if (raf != null) cancelAnimationFrame(raf);
      raf = null;
      last = null;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      // One upload of the cleared canvas, then stop re-uploading it every frame.
      if (source) { source.play(); source.pause(); }
    }
  }
  const visibility = () => sync();
  document.addEventListener('visibilitychange', visibility);
  reducedMotion?.addEventListener?.('change', visibility);

  return {
    canvas, timings, count, step,
    configure(next: { hour?: number; screenPerCanvasPx?: number; enabled?: boolean; windLayer?: boolean; source?: CanvasSource | null }) {
      if (next.hour != null) hour = next.hour;
      if (next.screenPerCanvasPx != null && Number.isFinite(next.screenPerCanvasPx) && next.screenPerCanvasPx > 0) {
        screenPerCanvasPx = next.screenPerCanvasPx;
      }
      let changed = false;
      if (next.enabled != null && enabled !== next.enabled) { enabled = next.enabled; changed = true; }
      if (next.windLayer != null && windLayer !== next.windLayer) { windLayer = next.windLayer; changed = true; }
      if (next.source && source !== next.source) { source = next.source; changed = true; }
      if (changed) sync();
    },
    // Copies for tests and diagnostics; the simulation arrays stay private.
    particleAt(i: number) {
      return { x: x[i], y: y[i], age: age[i], speed: speedAt[i], alpha: groups[bucketAt[i]].alpha };
    },
    get screenPerCanvasPx() { return screenPerCanvasPx; },
    get running() { return raf != null; },
    dispose() {
      enabled = false;
      sync();
      source = null;
      document.removeEventListener('visibilitychange', visibility);
      reducedMotion?.removeEventListener?.('change', visibility);
    },
  };
}

export type WindParticles = ReturnType<typeof createWindParticles>;

type MapLike = Pick<Map, 'addSource' | 'addLayer' | 'getSource' | 'getLayer' | 'removeLayer' | 'removeSource'
  | 'getStyle' | 'project' | 'on' | 'off'>;

// Shows the particle canvas on the map over the heatmap's box, below the labels, and keeps the on-screen speed
// constant as the map zooms. Returns a function that removes everything again.
export function attachWindParticles(map: MapLike, particles: WindParticles, coordinates: Position[]): () => void {
  const corners = coordinates as [Position, Position, Position, Position];
  map.addSource(SOURCE, { type: 'canvas', canvas: particles.canvas, animate: true, coordinates: corners });
  const beforeId = map.getStyle().layers.find(layer => layer.type === 'symbol')?.id;
  map.addLayer({ id: SOURCE, type: 'raster', source: SOURCE, paint: { 'raster-fade-duration': 0, 'raster-resampling': 'linear' } }, beforeId);
  particles.configure({ source: map.getSource<CanvasSource>(SOURCE) ?? null });

  let pending: number | null = null;
  const update = () => {
    pending = null;
    const xs = corners.map(corner => map.project(corner).x);
    particles.configure({ screenPerCanvasPx: (Math.max(...xs) - Math.min(...xs)) / particles.canvas.width });
  };
  const schedule = () => { if (pending == null) pending = requestAnimationFrame(update); };
  map.on('move', schedule);
  map.on('resize', schedule);
  update();

  return () => {
    if (pending != null) cancelAnimationFrame(pending);
    map.off('move', schedule);
    map.off('resize', schedule);
    particles.dispose();
    try {
      if (map.getLayer(SOURCE)) map.removeLayer(SOURCE);
      if (map.getSource(SOURCE)) map.removeSource(SOURCE);
    } catch {
      // The map was already removed (page unmount), and its layers with it.
    }
  };
}
