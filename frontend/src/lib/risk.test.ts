import { describe, expect, it } from 'vitest';
import { classifyPixel, levelFor } from './risk';

// Boundaries mirror backend/routing/risk.py: a value equal to a lower bound belongs to the higher level,
// and No Travel is inclusive for wind (>= 55) but exclusive for rain (> 1.00) and snow (> 3.0).
describe('levelFor', () => {
  it.each([
    ['wind', 24.9, 0], ['wind', 25, 1], ['wind', 34.9, 1], ['wind', 35, 2], ['wind', 45, 3], ['wind', 54.9, 3], ['wind', 55, 4],
    ['gust', 39.9, 0], ['gust', 40, 1], ['gust', 50, 2], ['gust', 60, 3], ['gust', 70, 4],
    ['rain', 0.099, 0], ['rain', 0.1, 1], ['rain', 0.25, 2], ['rain', 0.5, 3], ['rain', 1, 3], ['rain', 1.000001, 4],
    ['snow', 0.499, 0], ['snow', 0.5, 1], ['snow', 1, 2], ['snow', 2, 3], ['snow', 3, 3], ['snow', 3.000001, 4],
  ] as const)('%s %s is level %s', (hazard, value, level) => {
    expect(levelFor(hazard, value)).toBe(level);
  });

  it('has no level for a missing value', () => {
    expect(levelFor('wind', null)).toBeNull();
  });
});

describe('classifyPixel', () => {
  it.each([
    [35, 40000, 2], [35, 40001, 3], [44.9, 40001, 3], [45, 30000, 3], [45, 30001, 4], [54.9, 30001, 4], [55, 0, 4], [24.9, 60000, 0],
  ])('wind %s with a %s lb load is level %s', (wind, load, expected) => {
    expect(classifyPixel(wind, 60, 0, 0, load)).toBe(expected);
  });

  it('takes the worst of wind, rain and snow', () => {
    expect(classifyPixel(10, 10, 0.3, 0, 0)).toBe(2);
    expect(classifyPixel(10, 10, 0, 2.5, 0)).toBe(3);
    expect(classifyPixel(30, 10, 1.2, 0, 0)).toBe(4);
  });

  it('applies the wind metric: sustained by default, then gust, then the larger of the two', () => {
    expect(classifyPixel(10, 45, 0, 0, 42000)).toBe(0);
    expect(classifyPixel(10, 45, 0, 0, 42000, 'gust')).toBe(4);
    expect(classifyPixel(55, 10, 0, 0, 0, 'max')).toBe(4);
    expect(classifyPixel(35, null, 0, 0, 0, 'gust')).toBe(2);
    expect(classifyPixel(null, 36, 0, 0, 0, 'max')).toBe(2);
  });

  it('has no level without any data, and treats a single missing hazard as Low', () => {
    expect(classifyPixel(null, null, null, null, 0)).toBeNull();
    expect(classifyPixel(10, null, null, null, 0)).toBe(0);
  });
});
