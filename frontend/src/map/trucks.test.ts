import { afterEach, describe, expect, it, vi } from 'vitest';
import { Marker, type Map } from 'maplibre-gl';
import { createTrucks, truckAtTime } from './trucks';
import { route } from '../hooks/__tests__/fixtures';

vi.mock('maplibre-gl', () => ({
  Marker: vi.fn(class {
    setLngLat = vi.fn(() => this);
    addTo = vi.fn(() => this);
    setOpacity = vi.fn(() => this);
    remove = vi.fn();
  }),
}));

afterEach(() => { vi.unstubAllGlobals(); vi.mocked(Marker).mockClear(); });

const trip = {
  ...route,
  summary: { ...route.summary, departure: '2026-11-20T08:30:00Z', duration_s: 3600 },
  geometry: [[-100, 30], [-90, 40], [-80, 40]] as [number, number][],
  times: [0, 1800, 3600],
};
const at = (time: string) => Date.parse(time);

describe('truck position at forecast time', () => {
  it('stays at the origin before departure and while the heatmap is loading', () => {
    expect(truckAtTime(trip, null)).toMatchObject({ position: [-100, 30], opacity: 1, title: 'Route A: not departed' });
    expect(truckAtTime(trip, at('2026-11-20T08:00:00Z')).position).toEqual([-100, 30]);
  });

  it('uses each route departure, including minutes, rather than treating hour 0 as departure', () => {
    expect(truckAtTime(trip, at('2026-11-20T09:00:00Z'))).toMatchObject({ position: [-90, 40], opacity: 1, title: 'Route A: en route' });
    expect(truckAtTime(trip, at('2026-11-20T08:45:00Z')).position).toEqual([-95, 35]);
    const offset = { ...trip, summary: { ...trip.summary, departure: '2026-11-20T02:30:00-06:00' } };
    expect(truckAtTime(offset, at('2026-11-20T09:00:00Z')).position).toEqual([-90, 40]);
  });

  it('parks at the destination at 50% opacity on and after arrival', () => {
    for (const timestamp of ['2026-11-20T09:30:00Z', '2026-11-21T08:00:00Z']) {
      expect(truckAtTime(trip, at(timestamp))).toMatchObject({ position: [-80, 40], opacity: 0.5, title: 'Route A: arrived' });
    }
  });
});

it('creates labelled markers once, moves them without rebuilding, and removes all markers', () => {
  const elements: { style: Record<string, string>; setAttribute: ReturnType<typeof vi.fn> }[] = [];
  vi.stubGlobal('document', { createElement: () => {
    const element = { style: {}, setAttribute: vi.fn() };
    elements.push(element);
    return element;
  } });
  const map = {} as Map;
  const trucks = createTrucks(map, [trip, { ...trip, id: 'B', label: 'Route B' }]);
  expect(Marker).toHaveBeenCalledTimes(2);
  expect(elements[0]).toMatchObject({ className: 'truck-marker', textContent: 'A', style: { backgroundColor: '#1f5eff' } });
  expect(elements[1].style.backgroundColor).toBe('#0f9d8a');
  const markers = vi.mocked(Marker).mock.results.map(result => result.value);
  trucks.update(at('2026-11-20T09:00:00Z'));
  expect(markers[0].setLngLat).toHaveBeenLastCalledWith([-90, 40]);
  trucks.update(at('2026-11-20T10:00:00Z'));
  expect(markers[0].setOpacity).toHaveBeenLastCalledWith(0.5);
  expect(elements[0].setAttribute).toHaveBeenLastCalledWith('aria-label', 'Route A: arrived');
  expect(Marker).toHaveBeenCalledTimes(2);
  trucks.remove();
  for (const marker of markers) expect(marker.remove).toHaveBeenCalledTimes(1);
});
