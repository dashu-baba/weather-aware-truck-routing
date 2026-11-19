import { reverseGeocode } from '../api/client';
import type { Place } from '../api/types';
import { coordinatePlace, OUTSIDE_US_WARNING, type PlaceTarget, type TripLocation } from '../lib/places';

export function createPlaceResolver(update: (target: PlaceTarget, location: TripLocation) => void) {
  const requests = {
    origin: { id: 0, controller: null as AbortController | null },
    destination: { id: 0, controller: null as AbortController | null },
  };

  const cancel = (target: PlaceTarget) => {
    const request = requests[target];
    request.id++;
    request.controller?.abort();
    request.controller = null;
  };
  const cancelAll = () => { cancel('origin'); cancel('destination'); };

  return {
    cancelAll,
    select(target: PlaceTarget, place: Place | null) {
      cancel(target);
      update(target, { place, warning: null });
    },
    async pick(target: PlaceTarget, lat: number, lon: number): Promise<void> {
      cancel(target);
      const request = requests[target];
      const id = request.id;
      const controller = new AbortController();
      request.controller = controller;
      const point = coordinatePlace(lat, lon);
      update(target, { place: point, warning: null });

      try {
        const named = await reverseGeocode(point.lat, point.lon, controller.signal);
        if (controller.signal.aborted || request.id !== id) return;
        update(target, {
          // A reverse lookup changes the label, never the point picked by the user.
          place: { ...point, label: named.label },
          warning: named.country !== 'US' || !named.found ? OUTSIDE_US_WARNING : null,
        });
      } catch {
        // Keep the coordinate label if naming fails: routing only needs lat/lon.
      } finally {
        if (request.id === id) request.controller = null;
      }
    },
  };
}
