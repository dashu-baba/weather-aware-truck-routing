import { expect, it } from 'vitest';
import { duration, parseUtc, utcTime } from './format';

it('reads offsetless API forecast hours as UTC, preserving explicit offsets', () => {
  expect(parseUtc('2026-11-20T08:00').toISOString()).toBe('2026-11-20T08:00:00.000Z');
  expect(parseUtc('2026-11-20T08:00:00Z').toISOString()).toBe('2026-11-20T08:00:00.000Z');
  expect(parseUtc('2026-11-20T08:00:00-06:00').toISOString()).toBe('2026-11-20T14:00:00.000Z');
  expect(utcTime('2026-11-20T08:00')).toBe('2026-11-20 08:00 UTC');
});

it('rounds durations across hour boundaries without displaying 60 minutes', () => {
  expect(duration(3599)).toBe('1h 00m');
  expect(duration(3600)).toBe('1h 00m');
  expect(duration(3660)).toBe('1h 01m');
});
