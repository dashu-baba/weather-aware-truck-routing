import type { Place } from '../api/types';

export type PlaceTarget = 'origin' | 'destination';
export type TripLocation = { place: Place | null; warning: string | null };
export type TripPlaces = Record<PlaceTarget, TripLocation>;
export const OUTSIDE_US_WARNING = 'Outside the US — geocoding and risk thresholds assume US roads';

export function coordinatePlace(lat: number, lon: number): Place {
  // MapLibre can report longitudes outside [-180, 180] when the world is wrapped.
  const longitude = lon >= -180 && lon <= 180 ? lon : ((lon + 180) % 360 + 360) % 360 - 180;
  return { label: `${lat.toFixed(4)}, ${longitude.toFixed(4)}`, lat, lon: longitude };
}
