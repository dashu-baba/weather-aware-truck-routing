import { useState } from 'react';
import type { Place, PlanRequest } from '../api/types';
import { PlaceInput } from './PlaceInput';

export function nextHourLocal(now = new Date()): string {
  const next = new Date(now);
  next.setMinutes(0, 0, 0);
  next.setHours(next.getHours() + 1);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}T${pad(next.getHours())}:00`;
}

type Props = {
  busy: boolean;
  hasPlan: boolean;
  onSubmit: (body: PlanRequest) => void;
};

export function TripForm({ busy, hasPlan, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [departure, setDeparture] = useState(nextHourLocal);
  const [load, setLoad] = useState(42000);

  return (
    <form className="trip-form" onSubmit={event => {
      event.preventDefault();
      if (!origin || !destination || !departure || busy) return;
      onSubmit({
        origin,
        destination,
        departure: new Date(departure).toISOString(),
        load_lb: load,
      });
    }}>
      <div className="section-heading"><h2>Your trip</h2><span>01 — PLAN</span></div>
      <PlaceInput label="Origin" value={origin} onChange={setOrigin} />
      <div className="swap-row">
        <span className="journey-line" />
        <button type="button" className="swap" aria-label="Swap origin and destination"
          onClick={() => { setOrigin(destination); setDestination(origin); }}>
          ⇄ Swap
        </button>
      </div>
      <PlaceInput label="Destination" value={destination} onChange={setDestination} />
      <label className="field-label" htmlFor="departure">Departure <span>your local time</span></label>
      <input id="departure" type="datetime-local" required value={departure}
        onChange={event => setDeparture(event.target.value)} />
      <label className="field-label" htmlFor="load">Cargo weight <span>lb</span></label>
      <input id="load" type="number" min="0" max="60000" step="500" required value={load}
        onChange={event => setLoad(Number(event.target.value))} />
      <p className="field-note">Truck weight is added automatically.</p>
      <button type="submit" className="primary" disabled={!origin || !destination || busy}>
        {busy ? 'Planning…' : hasPlan ? 'Re-plan' : 'Plan routes'} <span aria-hidden="true">→</span>
      </button>
    </form>
  );
}
