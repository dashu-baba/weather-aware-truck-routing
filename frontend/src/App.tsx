import { usePlan } from './hooks/usePlan';
import { PlanStatus } from './components/PlanStatus';
import { MapView } from './components/MapView';
import { TripForm } from './components/TripForm';

export default function App() {
  const { state, submit, retry } = usePlan();
  const busy = state.phase === 'posting' || state.phase === 'weather';

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
        <TripForm busy={busy} hasPlan={state.hasPlan} onSubmit={submit} />
        <PlanStatus state={state} onRetry={retry} />
        <footer>
          Routing © TomTom · Weather data by Open-Meteo.com (CC BY 4.0) ·
          Map © OpenFreeMap, © OpenStreetMap contributors
        </footer>
      </aside>
      <MapView routes={state.routes} />
    </main>
  );
}
