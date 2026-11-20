// Ported from the POC's poc/frontend/tests/particles.test.js, run without a browser.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SPEED_PX_PER_MPH, attachWindParticles, createWindParticles, type WindField } from './windParticles';

class FakePath {
  segments: number[][] = [];
  moveTo(x: number, y: number) { this.segments.push([x, y]); }
  lineTo(x: number, y: number) { this.segments[this.segments.length - 1].push(x, y); }
}

function fakeCanvas() {
  const context = {
    globalCompositeOperation: '', fillStyle: '', strokeStyle: '', lineWidth: 0,
    fillRect: vi.fn(), clearRect: vi.fn(), stroke: vi.fn(),
  };
  return { canvas: { width: 0, height: 0, getContext: () => context } as unknown as HTMLCanvasElement, context };
}

let motion: { matches: boolean; listeners: (() => void)[]; addEventListener: (t: string, f: () => void) => void; removeEventListener: () => void };
let documentListeners: (() => void)[];
let hidden: boolean;
let frames: FrameRequestCallback[];

beforeEach(() => {
  motion = { matches: false, listeners: [], addEventListener: (_t, f) => motion.listeners.push(f), removeEventListener: vi.fn() };
  documentListeners = [];
  hidden = false;
  frames = [];
  vi.stubGlobal('window', { devicePixelRatio: 1, matchMedia: () => motion });
  vi.stubGlobal('document', {
    get hidden() { return hidden; },
    addEventListener: (_t: string, f: () => void) => documentListeners.push(f),
    removeEventListener: vi.fn(),
  });
  vi.stubGlobal('requestAnimationFrame', (f: FrameRequestCallback) => { frames.push(f); return frames.length; });
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});
afterEach(() => vi.unstubAllGlobals());

const makeField = (u = 30, v = 0): WindField => ({
  width: 100, height: 100, northPixelScale: 1, seeds: [5050],
  containsPixel: (x, y) => x >= 0 && y >= 0 && x < 100 && y < 100,
  vectorAtPixel: (_x, _y, _hour, out) => { out[0] = u; out[1] = v; return out; },
});

function make(field: WindField, count = 1, random = () => 0.5) {
  const { canvas, context } = fakeCanvas();
  const particles = createWindParticles(field, {
    count, random, createCanvas: () => canvas, createPath: () => new FakePath() as unknown as Path2D,
  });
  return { particles, context };
}

function measure(speed: number, screenPerCanvasPx = 1) {
  const { particles } = make(makeField(speed));
  particles.configure({ screenPerCanvasPx });
  const before = particles.particleAt(0);
  particles.step();
  const after = particles.particleAt(0);
  particles.dispose();
  return { dx: after.x - before.x, dy: after.y - before.y, alpha: after.alpha };
}

describe('wind particle motion', () => {
  it('moves in proportion to wind speed, at the same on-screen speed at every zoom', () => {
    expect(SPEED_PX_PER_MPH).toBe(0.04);
    const slow = measure(10);
    const fast = measure(20);
    const zoomed = measure(20, 4);
    expect(slow.dx).toBeCloseTo(fast.dx / 2, 9);
    expect(zoomed.dx).toBeCloseTo(fast.dx / 4, 9);
    expect(measure(2).dx).toBeLessThan(0.1);
  });

  it('draws stronger wind bolder (more opaque)', () => {
    expect(measure(35).alpha).toBeGreaterThan(measure(5).alpha);
    expect(measure(35).alpha).toBeCloseTo(0.9, 9);
    expect(measure(5).alpha).toBeCloseTo(0.12 + (0.78 * 5) / 35, 9);
  });

  it('respawns dropped particles at age zero and fades new ones in over twelve frames', () => {
    let dropNext = false;
    const { particles } = make(makeField(35), 1, () => { if (dropNext) { dropNext = false; return 0; } return 0.5; });
    dropNext = true;
    particles.step();
    expect(particles.particleAt(0).age).toBe(0);
    particles.step();
    const initial = particles.particleAt(0).alpha;
    for (let i = 0; i < 6; i++) particles.step();
    const middle = particles.particleAt(0).alpha;
    for (let i = 0; i < 6; i++) particles.step();
    const mature = particles.particleAt(0).alpha;
    expect(initial).toBe(0);
    expect(middle).toBeGreaterThan(initial);
    expect(middle).toBeLessThan(mature);
    expect(mature).toBeCloseTo(0.9, 9);
  });

  it('follows the wind direction: east wind moves east, wind from the north moves south', () => {
    const field = makeField();
    const { particles, context } = make(field, 3000);
    expect(particles.count).toBe(3000);
    expect([particles.canvas.width, particles.canvas.height]).toEqual([200, 200]);
    const first = particles.particleAt(0);
    particles.step();
    const east = particles.particleAt(0);
    expect(east.x).toBeGreaterThan(first.x);
    expect(east.y).toBe(first.y);
    field.vectorAtPixel = (_x, _y, _hour, out) => { out[0] = 0; out[1] = -30; return out; };
    particles.step();
    const south = particles.particleAt(0);
    expect(south.y).toBeGreaterThan(east.y);
    expect(south.x).toBe(east.x);
    expect(context.stroke).toHaveBeenCalled();
  });

  it('uses the slider hour', () => {
    const field = makeField();
    const spy = vi.fn((_x: number, _y: number, _hour: number, out: (number | null)[]) => { out[0] = 10; out[1] = 0; return out; });
    field.vectorAtPixel = spy;
    const { particles } = make(field);
    particles.configure({ hour: 7 });
    particles.step();
    expect(spy).toHaveBeenCalledWith(expect.any(Number), expect.any(Number), 7, expect.any(Array));
  });
});

describe('when the particles run', () => {
  it('runs only on a wind layer, and pauses for reduced motion, a hidden tab or when disabled', () => {
    const { particles, context } = make(makeField(), 10);
    expect(particles.running).toBe(false);
    particles.configure({ windLayer: true });
    expect(particles.running).toBe(true);
    motion.matches = true; motion.listeners.forEach(f => f());
    expect(particles.running).toBe(false);
    motion.matches = false; motion.listeners.forEach(f => f());
    expect(particles.running).toBe(true);
    hidden = true; documentListeners.forEach(f => f());
    expect(particles.running).toBe(false);
    hidden = false; documentListeners.forEach(f => f());
    expect(particles.running).toBe(true);
    context.clearRect.mockClear();
    particles.configure({ windLayer: false });
    expect(particles.running).toBe(false);
    expect(context.clearRect).toHaveBeenCalled(); // no stale trails left on the map
  });

  it('does not run when the corridor has no seed pixels', () => {
    const { particles } = make({ ...makeField(), seeds: [] });
    particles.configure({ windLayer: true });
    expect(particles.running).toBe(false);
  });
});

describe('attachWindParticles', () => {
  it('adds a canvas source over the heatmap box below the labels, keeps screen speed in step with zoom, and cleans up', () => {
    const { particles } = make(makeField());
    const handlers: Record<string, () => void> = {};
    const source = { play: vi.fn(), pause: vi.fn() };
    const map = {
      addSource: vi.fn(), addLayer: vi.fn(), removeLayer: vi.fn(), removeSource: vi.fn(),
      getSource: vi.fn(() => source), getLayer: vi.fn(() => ({})),
      getStyle: () => ({ layers: [{ id: 'water', type: 'fill' }, { id: 'labels', type: 'symbol' }] }),
      project: ([lng]: [number, number]) => ({ x: (lng + 110) * 10, y: 0 }),
      on: vi.fn((name: string, f: () => void) => { handlers[name] = f; }), off: vi.fn(),
    };
    const coordinates: [number, number][] = [[-110, 50], [-70, 50], [-70, 10], [-110, 10]];
    const detach = attachWindParticles(map as never, particles, coordinates);
    expect(map.addSource).toHaveBeenCalledWith('wind-particles', expect.objectContaining({ type: 'canvas', animate: true, coordinates }));
    expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({ id: 'wind-particles', type: 'raster' }), 'labels');
    expect(particles.screenPerCanvasPx).toBeCloseTo(400 / 200); // 400 screen px across a 200 px canvas
    detach();
    expect(map.off).toHaveBeenCalledWith('move', handlers.move);
    expect(map.removeLayer).toHaveBeenCalledWith('wind-particles');
    expect(map.removeSource).toHaveBeenCalledWith('wind-particles');
  });
});
