import { describe, expect, it } from 'vitest';
import { placeTooltip } from './hover';

const box = { width: 800, height: 600 };
const tip = { width: 150, height: 28 };

describe('placeTooltip', () => {
  it('sits 12 px right of and below the cursor', () => {
    expect(placeTooltip({ x: 100, y: 200 }, tip, box)).toEqual({ left: 112, top: 212 });
  });

  it('flips to the left of the cursor near the right edge', () => {
    expect(placeTooltip({ x: 750, y: 200 }, tip, box)).toEqual({ left: 750 - 12 - 150, top: 212 });
  });

  it('flips above the cursor near the bottom edge', () => {
    expect(placeTooltip({ x: 100, y: 590 }, tip, box)).toEqual({ left: 112, top: 590 - 12 - 28 });
  });

  it('never leaves the map, even in a very small one', () => {
    const place = placeTooltip({ x: 10, y: 5 }, { width: 400, height: 50 }, { width: 100, height: 30 });
    expect(place.left).toBeGreaterThanOrEqual(0);
    expect(place.top).toBeGreaterThanOrEqual(0);
  });
});
