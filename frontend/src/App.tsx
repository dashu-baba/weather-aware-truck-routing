import { useState } from 'react';
import type { PlanResult } from './api/types';
import { localTime } from './lib/format';
import { IntervalToggle } from './components/IntervalToggle';
import { Recommendation } from './components/Recommendation';
import { RouteCards } from './components/RouteCards';
import { usePlan } from './hooks/usePlan';
import { PlanStatus } from './components/PlanStatus';
import { MapView } from './components/MapView';
import { TripForm } from './components/TripForm';
import { Legend } from './components/Legend';
import { TimeBar } from './components/TimeBar';
import { useHeatfield } from './hooks/useHeatfield';
import type { HeatLayer } from './map/heatfield';

export default function App() {
  const { state, submit, retry } = usePlan();
  const result = state.plan?.result ?? null;
  const [selection, setSelection] = useState<{ result: PlanResult | null; interval: number; routeId: string | null }>({
    result: null, interval: 25, routeId: null,
  });
  // Derive defaults for a new result without an effect that could briefly use old choices.
  const current = selection.result === result;
  const interval = current ? selection.interval : result?.meta.default_interval ?? 25;
  const selectedId = current ? selection.routeId : null;
  const recommendation = result?.recommendation[String(interval)] ?? null;
  const focusId = selectedId ?? recommendation?.best ?? null;
  const busy = state.phase === 'posting' || state.phase === 'weather';
  // The heatmap controls. Changing them never calls the server: every frame is drawn from the heatmap already loaded.
  const [heat, setHeat] = useState<{ layer: HeatLayer; hour: number }>({ layer: 'risk', hour: 0 });
  const { heatfield, error: heatError } = useHeatfield(result, state.heatmap);
  const hour = heatfield ? Math.min(heat.hour, heatfield.hours - 1) : 0;

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
        <PlanStatus state={state} interval={interval} onRetry={retry} />
        {result && (
          <section className="plan-results" aria-label="Scored routes">
            <div className="section-heading"><h2>Compare routes</h2><span>02 — RESULTS</span></div>
            <p className="result-trip">{result.origin.label} → {result.destination.label}</p>
            <p className="result-context">Depart {localTime(result.meta.departure)} · {result.meta.load_lb.toLocaleString()} lb cargo</p>
            <Recommendation recommendation={recommendation} routes={result.routes} interval={interval} />
            <IntervalToggle intervals={result.meta.intervals} interval={interval}
              onChange={value => setSelection({ result, interval: value, routeId: selectedId })} />
            <RouteCards routes={result.routes} recommendation={recommendation} interval={interval} focusId={focusId}
              onFocus={id => setSelection({ result, interval, routeId: selectedId === id ? null : id })} />
            {result.meta.warnings.length > 0 && (
              <div className="plan-warnings" aria-label="Plan warnings">
                {result.meta.warnings.map((warning, index) => <p className="warning" key={index}>{warning}</p>)}
              </div>
            )}
          </section>
        )}
        <footer>
          Routing © TomTom · Weather data by Open-Meteo.com (CC BY 4.0) ·
          Map © OpenFreeMap, © OpenStreetMap contributors
        </footer>
      </aside>
      <MapView routes={state.routes} result={result} interval={interval} focusId={focusId}
        heatfield={heatfield} heatLayer={heat.layer} hour={hour}>
        {heatfield && <Legend layer={heat.layer} />}
        {state.phase === 'done' && !state.warning && (
          <TimeBar start={heatfield?.start ?? null} hours={heatfield?.hours ?? 48} hour={hour} layer={heat.layer}
            disabled={!heatfield} note={heatError ?? 'Loading the weather map…'}
            onHour={value => setHeat(current => ({ ...current, hour: value }))}
            onLayer={layer => setHeat(current => ({ ...current, layer }))} />
        )}
      </MapView>
    </main>
  );
}
