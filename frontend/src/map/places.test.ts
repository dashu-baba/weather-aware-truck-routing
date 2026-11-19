import { Marker, type Map } from 'maplibre-gl';
import { afterEach, expect, it, vi } from 'vitest';
import { createPlacePins } from './places';
import { initialTripPlaces } from '../hooks/tripPlacesReducer';
import type { TripPlaces } from '../lib/places';

vi.mock('maplibre-gl', () => ({
  Marker: vi.fn(class {
    position = { lng: 0, lat: 0 };
    element: HTMLElement;
    constructor({ element }: { element: HTMLElement }) { this.element = element; }
    setLngLat = vi.fn(([lng, lat]: [number, number]) => { this.position = { lng, lat }; return this; });
    getLngLat = () => this.position;
    getElement = () => this.element;
    addTo = vi.fn(() => this);
    on = vi.fn(() => this);
    remove = vi.fn();
  }),
}));
afterEach(() => { vi.unstubAllGlobals(); vi.mocked(Marker).mockClear(); });

it('creates draggable A/B pins, moves/relabels existing pins, routes dragend, and removes cleared pins', () => {
  vi.stubGlobal('document', { createElement: () => ({ setAttribute: vi.fn() }) });
  const pick = vi.fn();
  const pins = createPlacePins({} as Map, pick);
  pins.update(initialTripPlaces);
  expect(Marker).not.toHaveBeenCalled();
  const places: TripPlaces = {
    origin: { place: { label: 'Dallas', lat: 32, lon: -96 }, warning: null },
    destination: { place: { label: 'Atlanta', lat: 33, lon: -84 }, warning: null },
  };
  pins.update(places);
  expect(Marker).toHaveBeenCalledTimes(2);
  expect(Marker).toHaveBeenCalledWith(expect.objectContaining({ draggable: true, anchor: 'bottom' }));
  const markers = vi.mocked(Marker).mock.results.map(result => result.value);
  expect(markers[0].getElement().textContent).toBe('A');
  expect(markers[1].getElement().textContent).toBe('B');
  pins.update({ ...places, origin: { place: { label: 'New label', lat: 32, lon: -96 }, warning: null } });
  expect(markers[0].setLngLat).toHaveBeenCalledTimes(1);
  expect(markers[0].getElement().title).toContain('New label');
  pins.update({ ...places, origin: { place: { label: 'New point', lat: 40, lon: -90 }, warning: null } });
  expect(markers[0].setLngLat).toHaveBeenLastCalledWith([-90, 40]);
  expect(Marker).toHaveBeenCalledTimes(2);
  markers[0].position = { lng: 200, lat: 35 };
  markers[0].on.mock.calls[0][1]();
  expect(pick).toHaveBeenCalledExactlyOnceWith('origin', 35, -160);
  pins.update({ ...places, origin: initialTripPlaces.origin });
  expect(markers[0].remove).toHaveBeenCalledTimes(1);
  pins.remove();
  expect(markers[1].remove).toHaveBeenCalledTimes(1);
});
