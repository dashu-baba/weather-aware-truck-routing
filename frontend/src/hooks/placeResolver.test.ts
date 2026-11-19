import { afterEach, describe, expect, it, vi } from 'vitest';
import { reverseGeocode } from '../api/client';
import type { ReversePlace } from '../api/types';
import { createPlaceResolver } from './placeResolver';
import { coordinatePlace } from '../lib/places';
import { initialTripPlaces, tripPlacesReducer } from './tripPlacesReducer';

vi.mock('../api/client', () => ({ reverseGeocode: vi.fn() }));
afterEach(() => vi.mocked(reverseGeocode).mockReset());
const named: ReversePlace = { label: 'Dallas, TX', lat: 32.7767, lon: -96.797, country: 'US', found: true };
function deferred() {
  let resolve!: (value: ReversePlace) => void;
  const promise = new Promise<ReversePlace>(finish => { resolve = finish; });
  return { promise, resolve };
}

describe('map location resolution', () => {
  it('sets a four-decimal coordinate label immediately, then names the same point', async () => {
    const reply = deferred();
    vi.mocked(reverseGeocode).mockReturnValue(reply.promise);
    const update = vi.fn();
    const resolver = createPlaceResolver(update);
    const done = resolver.pick('origin', 32.7767, -96.797);
    expect(update).toHaveBeenCalledExactlyOnceWith('origin', {
      place: { label: '32.7767, -96.7970', lat: 32.7767, lon: -96.797 }, warning: null,
    });
    expect(reverseGeocode).toHaveBeenCalledWith(32.7767, -96.797, expect.any(AbortSignal));
    reply.resolve({ ...named, lat: 0, lon: 0 });
    await done;
    expect(update).toHaveBeenLastCalledWith('origin', { place: { label: 'Dallas, TX', lat: 32.7767, lon: -96.797 }, warning: null });
  });

  it('aborts and ignores stale replies from a previous pick on the same target', async () => {
    const old = deferred();
    const recent = deferred();
    vi.mocked(reverseGeocode).mockReturnValueOnce(old.promise).mockReturnValueOnce(recent.promise);
    const update = vi.fn();
    const resolver = createPlaceResolver(update);
    const first = resolver.pick('origin', 32, -96);
    const signal = vi.mocked(reverseGeocode).mock.calls[0][2];
    const second = resolver.pick('origin', 33, -95);
    expect(signal?.aborted).toBe(true);
    recent.resolve({ ...named, label: 'New point' });
    await second;
    old.resolve({ ...named, label: 'Old point' });
    await first;
    expect(update).toHaveBeenCalledTimes(3);
    expect(update).toHaveBeenLastCalledWith('origin', { place: { label: 'New point', lat: 33, lon: -95 }, warning: null });
  });

  it('resolves origin and destination independently', async () => {
    const origin = deferred();
    const destination = deferred();
    vi.mocked(reverseGeocode).mockReturnValueOnce(origin.promise).mockReturnValueOnce(destination.promise);
    const update = vi.fn();
    const resolver = createPlaceResolver(update);
    const first = resolver.pick('origin', 32, -96);
    const second = resolver.pick('destination', 33, -84);
    expect(vi.mocked(reverseGeocode).mock.calls[0][2]?.aborted).toBe(false);
    destination.resolve({ ...named, label: 'Atlanta' });
    origin.resolve(named);
    await Promise.all([first, second]);
    expect(update).toHaveBeenCalledWith('destination', { place: { label: 'Atlanta', lat: 33, lon: -84 }, warning: null });
    expect(update).toHaveBeenLastCalledWith('origin', { place: { label: 'Dallas, TX', lat: 32, lon: -96 }, warning: null });
  });

  it.each([null, { label: 'Search choice', lat: 35, lon: -90 }])('invalidates a lookup when typing, clearing or selecting from search (%s)', async place => {
    const reply = deferred();
    vi.mocked(reverseGeocode).mockReturnValue(reply.promise);
    const update = vi.fn();
    const resolver = createPlaceResolver(update);
    const done = resolver.pick('origin', 32, -96);
    resolver.select('origin', place);
    reply.resolve(named);
    await done;
    expect(update).toHaveBeenCalledTimes(2);
    expect(update).toHaveBeenLastCalledWith('origin', { place, warning: null });
    expect(vi.mocked(reverseGeocode).mock.calls[0][2]?.aborted).toBe(true);
  });

  it('cancels both pending lookups for swap/unmount, and remains reusable in StrictMode', async () => {
    const first = deferred();
    const second = deferred();
    vi.mocked(reverseGeocode).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockResolvedValue(named);
    const update = vi.fn();
    const resolver = createPlaceResolver(update);
    const one = resolver.pick('origin', 32, -96);
    const two = resolver.pick('destination', 33, -84);
    resolver.cancelAll();
    expect(vi.mocked(reverseGeocode).mock.calls.slice(0, 2).every(call => call[2]?.aborted)).toBe(true);
    first.resolve(named); second.resolve(named);
    await Promise.all([one, two]);
    expect(update).toHaveBeenCalledTimes(2);
    await resolver.pick('origin', 32.7767, -96.797);
    expect(update).toHaveBeenLastCalledWith('origin', { place: { label: named.label, lat: named.lat, lon: named.lon }, warning: null });
  });

  it('keeps the coordinate label and usable place when reverse geocoding fails', async () => {
    vi.mocked(reverseGeocode).mockRejectedValue(new Error('502'));
    const update = vi.fn();
    await createPlaceResolver(update).pick('destination', 0, 0);
    expect(update).toHaveBeenCalledExactlyOnceWith('destination', { place: coordinatePlace(0, 0), warning: null });
  });
});

it('wraps map longitudes while preserving ordinary coordinates exactly', () => {
  expect(coordinatePlace(32.7767, -96.797).lon).toBe(-96.797);
  expect(coordinatePlace(0, 200)).toEqual({ label: '0.0000, -160.0000', lat: 0, lon: -160 });
  expect(coordinatePlace(0, -200).lon).toBe(160);
});

it('swaps both places and warnings without modifying the original state', () => {
  const state = tripPlacesReducer(initialTripPlaces, { type: 'set', target: 'origin', location: { place: named, warning: 'Check this location' } });
  const swapped = tripPlacesReducer(state, { type: 'swap' });
  expect(swapped.destination).toBe(state.origin);
  expect(swapped.origin).toBe(state.destination);
  expect(state.origin.place?.label).toBe('Dallas, TX');
});
