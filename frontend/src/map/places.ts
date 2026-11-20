import { Marker, type Map } from 'maplibre-gl';
import { coordinatePlace, type PlaceTarget, type TripPlaces } from '../lib/places';

// The pins use icons, not letters: routes are already called A, B and C.
const PIN_ICONS: Record<PlaceTarget, string> = {
  origin: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="8" cy="8" r="5" fill="currentColor"/></svg>',
  destination: '<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M4 1.5v13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M4.9 2.2h8.2l-2 3.1 2 3.1H4.9z" fill="currentColor"/></svg>',
};
const PIN_NAMES: Record<PlaceTarget, string> = { origin: 'Start', destination: 'Destination' };

export function createPlacePins(map: Map, onPick: (target: PlaceTarget, lat: number, lon: number) => void) {
  const pins = new globalThis.Map<PlaceTarget, Marker>();
  return {
    update(places: TripPlaces) {
      for (const target of ['origin', 'destination'] as const) {
        const place = places[target].place;
        let marker = pins.get(target);
        if (!place) {
          marker?.remove();
          pins.delete(target);
          continue;
        }
        if (!marker) {
          const element = document.createElement('div');
          element.className = `place-pin place-pin--${target}`;
          element.innerHTML = PIN_ICONS[target];
          element.setAttribute('role', 'img');
          marker = new Marker({ element, draggable: true, anchor: 'bottom' });
          const pin = marker;
          marker.on('dragend', () => {
            const { lat, lng } = pin.getLngLat();
            const point = coordinatePlace(lat, lng);
            onPick(target, point.lat, point.lon);
          });
          marker.setLngLat([place.lon, place.lat]).addTo(map);
          pins.set(target, marker);
        } else {
          const current = marker.getLngLat();
          if (current.lat !== place.lat || current.lng !== place.lon) marker.setLngLat([place.lon, place.lat]);
        }
        const label = `${PIN_NAMES[target]}: ${place.label}. Drag to move.`;
        marker.getElement().title = label;
        marker.getElement().setAttribute('aria-label', label);
      }
    },
    remove() {
      pins.forEach(marker => marker.remove());
      pins.clear();
    },
  };
}
