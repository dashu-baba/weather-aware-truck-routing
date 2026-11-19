import { useCallback, useEffect, useReducer, useState } from 'react';
import type { Place } from '../api/types';
import type { PlaceTarget } from '../lib/places';
import { createPlaceResolver } from './placeResolver';
import { initialTripPlaces, tripPlacesReducer } from './tripPlacesReducer';

export function useTripPlaces() {
  const [places, dispatch] = useReducer(tripPlacesReducer, initialTripPlaces);
  const [pickTarget, setPickTarget] = useState<PlaceTarget | null>(null);
  const [resolver] = useState(() => createPlaceResolver((target, location) => {
    dispatch({ type: 'set', target, location });
  }));

  useEffect(() => () => resolver.cancelAll(), [resolver]);
  useEffect(() => {
    if (!pickTarget) return;
    const cancel = (event: KeyboardEvent) => { if (event.key === 'Escape') setPickTarget(null); };
    window.addEventListener('keydown', cancel);
    return () => window.removeEventListener('keydown', cancel);
  }, [pickTarget]);

  const select = useCallback((target: PlaceTarget, place: Place | null) => {
    setPickTarget(null);
    resolver.select(target, place);
  }, [resolver]);

  const pick = useCallback((target: PlaceTarget, lat: number, lon: number) => {
    setPickTarget(null);
    void resolver.pick(target, lat, lon);
  }, [resolver]);

  const swap = useCallback(() => {
    resolver.cancelAll();
    setPickTarget(null);
    dispatch({ type: 'swap' });
  }, [resolver]);

  const startPick = useCallback((target: PlaceTarget) => {
    setPickTarget(current => current === target ? null : target);
  }, []);
  const cancelPick = useCallback(() => setPickTarget(null), []);

  return { places, pickTarget, select, pick, swap, startPick, cancelPick };
}
