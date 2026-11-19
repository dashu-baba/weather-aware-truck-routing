import { Marker, type Map } from 'maplibre-gl';
import { coordinatePlace, type PlaceTarget, type TripPlaces } from '../lib/places';

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
          element.className = 'place-pin';
          element.textContent = target === 'origin' ? 'A' : 'B';
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
        const label = `${target === 'origin' ? 'Origin A' : 'Destination B'}: ${place.label}. Drag to move.`;
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
