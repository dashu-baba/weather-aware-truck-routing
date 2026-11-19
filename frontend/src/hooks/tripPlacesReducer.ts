import type { PlaceTarget, TripLocation, TripPlaces } from '../lib/places';

export const initialTripPlaces: TripPlaces = {
  origin: { place: null, warning: null },
  destination: { place: null, warning: null },
};
export type TripPlacesAction =
  | { type: 'set'; target: PlaceTarget; location: TripLocation }
  | { type: 'swap' };

export function tripPlacesReducer(state: TripPlaces, action: TripPlacesAction): TripPlaces {
  if (action.type === 'swap') return { origin: state.destination, destination: state.origin };
  return { ...state, [action.target]: action.location };
}
