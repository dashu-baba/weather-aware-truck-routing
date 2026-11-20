import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Heatmap } from '../api/types';
import { levelFor } from '../lib/risk';
import { createHeatfield, hoverLabel, latitudeAtY, legendColor, mercatorY } from './heatfield';
import { RISK_COLORS } from './palette';

const HOURS = 48;
const meta = { load_lb: 42000, assumptions: { wind_metric: 'sustained' as const, truck_tare_lb: 35000 } };

// A 2 x 2 grid, 20 degrees apart. Cell order is row * ncols + col with row 0 in the south.
function heatmap(vars: Partial<Record<'wind' | 'gust' | 'rain' | 'snow', (number | null)[]>> = {}): Heatmap {
  const hour = (values: (number | null)[]) => Array.from({ length: HOURS }, () => values);
  return {
    mode: 'hull', start: '2026-11-20T08:00:00Z', hours: HOURS,
    grid: { lat0: 20, lon0: -100, step: 20, nrows: 2, ncols: 2 },
    polygon: [[-100, 20], [-80, 20], [-80, 40], [-100, 40], [-100, 20]],
    vars: {
      risk: hour([0, 0, 0, 0]),
      wind: hour(vars.wind ?? [0, 40, 0, 40]),
      gust: hour(vars.gust ?? [null, 40, 20, 60]),
      rain: hour(vars.rain ?? [0, 0, 0, 0]),
      snow: hour(vars.snow ?? [0, 0, 0, 0]),
      u: hour([0, 0, 0, 0]),
      v: hour([0, 0, 0, 0]),
    },
  };
}

// A canvas stand-in that records what is drawn, because the unit tests run without a browser.
function fakeBrowser() {
  const staged: Uint8ClampedArray[] = [];
  const clips: unknown[] = [];
  const created: { width: number; height: number }[] = [];
  const createCanvas = (width: number, height: number) => {
    const ctx = {
      createImageData: (w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }),
      putImageData: (image: { data: Uint8ClampedArray }) => staged.push(image.data.slice()),
      save: () => undefined, restore: () => undefined,
      clip: (path: unknown) => clips.push(path),
      drawImage: () => undefined,
      // The corridor mask for the wind particles: filling marks every pixel as inside (the test polygon is the box).
      filled: false,
      fill() { this.filled = true; },
      getImageData(_x: number, _y: number, w: number, h: number) {
        const data = new Uint8ClampedArray(w * h * 4);
        if (this.filled) for (let i = 3; i < data.length; i += 4) data[i] = 255;
        return { data, width: w, height: h };
      },
    };
    created.push({ width, height });
    return { width, height, getContext: () => ctx } as unknown as HTMLCanvasElement;
  };
  const idleTasks: (() => void)[] = [];
  const idle = (task: () => void) => idleTasks.push(task);
  const runIdle = () => { while (idleTasks.length) idleTasks.shift()!(); };
  return { createCanvas, idle, cancelIdle: () => undefined, staged, clips, created, runIdle };
}

const pixel = (data: Uint8ClampedArray, width: number, x: number, y: number) =>
  [...data.slice((y * width + x) * 4, (y * width + x) * 4 + 4)];

class FakePath {
  points: [string, number, number][] = [];
  moveTo(x: number, y: number) { this.points.push(['m', x, y]); }
  lineTo(x: number, y: number) { this.points.push(['l', x, y]); }
  closePath() { /* the shape is already complete */ }
}

beforeEach(() => vi.stubGlobal('Path2D', FakePath));
afterEach(() => vi.unstubAllGlobals());

function build(map = heatmap(), loadLb = meta.load_lb) {
  const browser = fakeBrowser();
  const field = createHeatfield({ meta: { ...meta, load_lb: loadLb }, heatmap: map },
    { createCanvas: browser.createCanvas, idle: browser.idle, cancelIdle: browser.cancelIdle });
  return { field, browser };
}

describe('sampling', () => {
  it('interpolates bilinearly with row 0 in the south', () => {
    const { field } = build();
    expect(field.sample('wind', 0, 30, -90)).toBeCloseTo(20); // the middle of four cells: 0, 40, 0, 40
    expect(field.sample('wind', 0, 20, -80)).toBe(40);        // the south-east cell centre
    expect(field.sample('wind', 0, 20, -100)).toBe(0);        // the south-west cell centre
    const north = build(heatmap({ wind: [0, 0, 60, 60] })).field;
    expect(north.sample('wind', 0, 40, -90)).toBe(60);        // row 1 is the northern row
    expect(north.sample('wind', 0, 20, -90)).toBe(0);
  });

  it('renormalises over the neighbours that have data and returns null when none do', () => {
    expect(build().field.sample('gust', 0, 30, -90)).toBeCloseTo(40); // 40, 20 and 60 average to 40
    const empty = build(heatmap({ gust: [null, null, null, null] })).field;
    expect(empty.sample('gust', 0, 30, -90)).toBeNull();
  });

  it('has no value outside the grid, for an unknown layer or for an hour outside 0 to 47', () => {
    const { field } = build();
    expect(field.sample('wind', 0, 0, -100)).toBeNull();
    expect(field.sample('wind', 0, 30, -130)).toBeNull();
    expect(field.sample('wind', -1, 30, -90)).toBeNull();
    expect(field.sample('wind', HOURS, 30, -90)).toBeNull();
    expect(field.sample('humidity' as never, 0, 30, -90)).toBeNull();
  });

  it('classifies the interpolated weather for the risk layer instead of interpolating risk levels', () => {
    const { field } = build(heatmap({ wind: [0, 40, 0, 40] }));
    // 30 mph three quarters of the way east is Moderate; averaging the cells' integer levels would not give 1.
    expect(field.sample('risk', 0, 20, -85)).toBe(1);
  });

  it('applies the load rules to the interpolated wind', () => {
    const windy = heatmap({ wind: [40, 40, 40, 40] });
    expect(build(windy, 42000).field.sample('risk', 0, 30, -90)).toBe(3); // 40 mph over 40,000 lb is Severe
    expect(build(windy, 38000).field.sample('risk', 0, 30, -90)).toBe(2);
  });

  it('tells whether a point is inside the corridor, boundary included', () => {
    const { field } = build();
    expect(field.contains(30, -90)).toBe(true);
    expect(field.contains(30, -105)).toBe(false);
    expect(field.contains(20, -90)).toBe(true);
  });
});

describe('rendering', () => {
  it('rejects a heatmap without a corridor', () => {
    expect(() => build({ ...heatmap(), polygon: [] })).toThrow(/not available/i);
  });

  it('places the image on the grid bounding box in [lon, lat] corner order, north-west first', () => {
    const { field } = build();
    expect(field.coordinates).toEqual([[-110, 50], [-70, 50], [-70, 10], [-110, 10]]);
    expect(field.width).toBe(16);
    expect(field.height).toBe(16);
  });

  it('colours pixels by level, with Low nearly transparent and the other levels at about 55%', () => {
    const { field, browser } = build(heatmap({ wind: [60, 60, 60, 60] }));
    field.renderFrame('wind', 0);
    expect(pixel(browser.staged[0], field.width, 8, 8)).toEqual([0x6a, 0x1b, 0x9a, 140]); // No Travel purple
    const low = build(heatmap({ wind: [0, 0, 0, 0] }));
    low.field.renderFrame('wind', 0);
    expect(pixel(low.browser.staged[0], low.field.width, 8, 8)[3]).toBe(18);
  });

  it('shows light snow and rain in blue that strengthens with the amount, and leaves dry pixels clear', () => {
    const light = build(heatmap({ snow: [0.3, 0.3, 0.3, 0.3] }));
    light.field.renderFrame('snow', 0);
    const lightSnow = pixel(light.browser.staged[0], light.field.width, 8, 8);
    expect(lightSnow.slice(0, 3)).toEqual([56, 132, 214]);
    expect(lightSnow[3]).toBeGreaterThan(80);
    const trace = build(heatmap({ snow: [0.1, 0.1, 0.1, 0.1] }));
    trace.field.renderFrame('snow', 0);
    expect(pixel(trace.browser.staged[0], trace.field.width, 8, 8)[3]).toBeLessThan(lightSnow[3]);
    const dry = build(heatmap({ snow: [0, 0, 0, 0] }));
    dry.field.renderFrame('snow', 0);
    expect(pixel(dry.browser.staged[0], dry.field.width, 8, 8)[3]).toBe(0);
    const moderate = build(heatmap({ snow: [0.7, 0.7, 0.7, 0.7] }));
    moderate.field.renderFrame('snow', 0);
    expect(pixel(moderate.browser.staged[0], moderate.field.width, 8, 8)).toEqual([0xf2, 0xb7, 0x05, 140]);
    const drizzle = build(heatmap({ rain: [0.05, 0.05, 0.05, 0.05] }));
    drizzle.field.renderFrame('rain', 0);
    expect(pixel(drizzle.browser.staged[0], drizzle.field.width, 8, 8).slice(0, 3)).toEqual([37, 99, 235]);
  });

  it('gives the particles a corridor mask, seed pixels and the wind vector at fractional pixels', () => {
    const data = heatmap();
    data.vars.u = data.vars.u.map(() => [30, 30, 30, 30]);
    data.vars.v = data.vars.v.map(() => [0, 0, 0, 0]);
    const { field } = build(data);
    const wind = field.windField();
    expect(field.windField()).toBe(wind); // built once
    expect(wind.seeds.length).toBe(field.width * field.height);
    expect(wind.containsPixel(8, 8)).toBe(true);
    expect(wind.containsPixel(-1, 8)).toBe(false);
    const [u, v] = wind.vectorAtPixel(8, 8, 0, [0, 0]);
    expect(u).toBeCloseTo(30);
    expect(v).toBeCloseTo(0);
    data.vars.u[0] = [0, 40, 0, 40];
    const fresh = build(data).field.windField();
    expect(fresh.vectorAtPixel(8, 8, 0, [0, 0])[0]).toBeCloseTo(20); // the middle of 0 and 40
    expect(fresh.northPixelScale).toBeGreaterThan(0);
  });

  it('colours gusts on their own scale, 15 mph above the wind scale', () => {
    const { field, browser } = build(heatmap({ gust: [45, 45, 45, 45] }));
    field.renderFrame('gust', 0);
    expect(pixel(browser.staged[0], field.width, 8, 8)).toEqual([0xf2, 0xb7, 0x05, 140]); // Moderate, not Severe
    expect(legendColor('gust', 1)).toBe('#f2b705');
    expect(legendColor('snow', 0)).toBe('rgb(56, 132, 214)');
  });

  it('leaves pixels transparent where the layer has no value', () => {
    const { field, browser } = build(heatmap({ gust: [null, null, null, null] }));
    field.renderFrame('gust', 0);
    expect(pixel(browser.staged[0], field.width, 8, 8)[3]).toBe(0);
  });

  it('rasterises in Web Mercator so rows line up with the basemap', () => {
    const map: Heatmap = { ...heatmap({ wind: [0, 0, 60, 60] }), polygon: [[-110, 10], [-70, 10], [-70, 50], [-110, 50], [-110, 10]] };
    const { field, browser } = build(map);
    field.renderFrame('wind', 0);
    const north = field.coordinates[0][1];
    const south = field.coordinates[3][1];
    for (let row = 1; row < 15; row++) {
      const lat = latitudeAtY(mercatorY(north) + (mercatorY(south) - mercatorY(north)) * (row + 0.5) / field.height);
      const level = levelFor('wind', field.sample('wind', 0, lat, -90))!;
      const expectedRed = parseInt(RISK_COLORS[level].slice(1, 3), 16);
      expect(pixel(browser.staged[0], field.width, 8, row)[0]).toBe(expectedRed);
    }
  });

  it('clips the frame to the corridor polygon in the same Mercator mapping', () => {
    const { field, browser } = build();
    field.renderFrame('wind', 0);
    expect(browser.clips).toHaveLength(1);
    const path = browser.clips[0] as FakePath;
    expect(path.points).toHaveLength(5);
    expect(path.points[0][0]).toBe('m');
    expect(path.points[0][1]).toBeCloseTo(4); // [-100, 20] is a quarter of the way across the -110..-70 box
    for (const [, x, y] of path.points) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(field.width);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(field.height);
    }
  });

  it('refuses an unknown layer or an hour outside 0 to 47', () => {
    const { field } = build();
    expect(() => field.renderFrame('humidity' as never, 0)).toThrow(/layer/i);
    expect(() => field.renderFrame('wind', 48)).toThrow(/hour/i);
    expect(() => field.renderFrame('wind', 1.5)).toThrow(/hour/i);
  });
});

describe('frame cache', () => {
  it('reuses a rendered frame', () => {
    const { field } = build();
    const first = field.renderFrame('wind', 0);
    expect(field.renderFrame('wind', 0)).toBe(first);
    expect(field.cacheSize).toBe(1);
  });

  it('keeps at most 60 frames and drops the least recently used one first', () => {
    const { field } = build();
    const first = field.renderFrame('wind', 0);
    const second = field.renderFrame('wind', 1);
    for (let hour = 2; hour < HOURS; hour++) field.renderFrame('wind', hour);
    field.renderFrame('wind', 0); // touch hour 0 so hour 1 is now the oldest
    for (let hour = 0; hour < 13; hour++) field.renderFrame('gust', hour); // 48 + 13 = 61 frames, so one is dropped
    expect(field.cacheSize).toBe(60);
    expect(field.renderFrame('wind', 0)).toBe(first);
    expect(field.renderFrame('wind', 1)).not.toBe(second);
  });

  it('pre-renders the next and previous hour when idle, without re-rendering them later', () => {
    const { field, browser } = build();
    field.prerenderNeighbours('wind', 5);
    browser.runIdle();
    expect(field.cacheSize).toBe(2);
    const before = browser.created.length;
    field.renderFrame('wind', 6);
    field.renderFrame('wind', 4);
    expect(browser.created.length).toBe(before);
  });

  it('pre-renders only hours that exist', () => {
    const { field, browser } = build();
    field.prerenderNeighbours('wind', 0);
    browser.runIdle();
    expect(field.cacheSize).toBe(1); // hour 1 only
    field.clearCache();
    field.prerenderNeighbours('wind', HOURS - 1);
    browser.runIdle();
    expect(field.cacheSize).toBe(1); // hour 46 only
  });

  it('records timings only in debug mode', () => {
    const quiet = build();
    quiet.field.renderFrame('wind', 0);
    expect(quiet.field.timings).toHaveLength(0);
    vi.spyOn(console, 'debug').mockImplementation(() => undefined);
    const browser = fakeBrowser();
    const debug = createHeatfield({ meta, heatmap: heatmap() },
      { debug: true, createCanvas: browser.createCanvas, idle: browser.idle, cancelIdle: browser.cancelIdle });
    debug.renderFrame('wind', 0);
    debug.renderFrame('wind', 0);
    expect(debug.timings.map(t => t.cached)).toEqual([false, true]);
  });
});

describe('hoverLabel', () => {
  const at = new Date('2026-11-21T04:00:00Z');
  it('shows speed, level and time for wind and gust', () => {
    expect(hoverLabel('gust', 41.2, at)).toMatch(/^Gust 41 mph · Moderate · /);
    expect(hoverLabel('wind', 55, at)).toMatch(/^Wind 55 mph · No Travel · /);
  });
  it('shows rates with three decimals for rain and snow', () => {
    expect(hoverLabel('rain', 0.3, at)).toMatch(/^Rain 0\.300 in\/hr · High · /);
    expect(hoverLabel('snow', 0.1, at)).toMatch(/^Snow 0\.100 in\/hr · Low · /);
  });
  it('shows just the level for risk', () => {
    expect(hoverLabel('risk', 3, at)).toMatch(/^Risk · Severe · /);
  });
});
