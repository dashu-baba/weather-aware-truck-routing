import { useState } from 'react';
import type { PlanRequest } from './api/types';
import { MapView } from './components/MapView';
import { TripForm } from './components/TripForm';

export default function App() {
  const [trip, setTrip] = useState<PlanRequest | null>(null);

  return (
    <main className="app-shell">
      <aside className="panel">
        <header className="brand">
          <div className="brand-icon" aria-hidden="true">↗</div>
          <div>
            <h1>Weather-aware<span>Truck routing</span></h1>
            <p>PLAN WITH THE FORECAST AHEAD</p>
          </div>
        </header>
        <TripForm busy={false} hasPlan={false} onSubmit={setTrip} />
        {trip && (
          <p className="trip-ready" role="status">
            Trip details ready: {trip.origin.label} → {trip.destination.label}.
          </p>
        )}
        <footer>
          Routing © TomTom · Weather data by Open-Meteo.com (CC BY 4.0) ·
          Map © OpenFreeMap, © OpenStreetMap contributors
        </footer>
      </aside>
      <MapView />
    </main>
  );
}
