import { useState } from 'react';
import type { PlanResult } from './api/types';
import { localTime } from './lib/format';
import { IntervalToggle } from './components/IntervalToggle';
import { Recommendation } from './components/Recommendation';
import { RouteCards } from './components/RouteCards';
import { usePlan } from './hooks/usePlan';
import { useTripPlaces } from './hooks/useTripPlaces';
import TruckLoader from './components/TruckLoader';
import { PlanStatus } from './components/PlanStatus';
import { AppHeader } from './components/AppHeader';
import { MapView } from './components/MapView';
import { TripForm } from './components/TripForm';
import { Legend } from './components/Legend';
import { TimeBar } from './components/TimeBar';
import { useHeatfield } from './hooks/useHeatfield';
import { usePlayback } from './hooks/usePlayback';
import type { HeatLayer } from './map/heatfield';

export default function App() {
  const { state, submit, retry } = usePlan();
  const locations = useTripPlaces();
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
  const [layer, setLayer] = useState<HeatLayer>('risk');
  const { heatfield, error: heatError } = useHeatfield(result, state.heatmap);
  const { hour, playing, pause, seek, toggle } = usePlayback(heatfield);

  return (
    <>
      <AppHeader />
      {state.phase === 'posting' && (
        <div className="page-loader" role="alert" aria-busy="true">
          <TruckLoader width={320} label="Finding truck routes…" />
        </div>
      )}
      <main className="app-shell">
        <aside className="panel">
          <TripForm busy={busy} hasPlan={state.hasPlan} onSubmit={submit}
            places={locations.places} pickTarget={locations.pickTarget}
            onPlaceChange={locations.select} onPick={locations.startPick} onSwap={locations.swap} />
          <PlanStatus state={state} interval={interval} onRetry={retry} />
          {result && (
            <section className="plan-results" aria-label="Scored routes">
              <div className="section-heading"><h2>Compare routes</h2></div>
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
          heatfield={heatfield} heatLayer={layer} hour={hour}
          places={locations.places} pickTarget={locations.pickTarget} onPick={locations.pick} onCancelPick={locations.cancelPick}>
          {heatfield && !locations.pickTarget && <Legend layer={layer} />}
          {state.phase === 'done' && !state.warning && (
            <TimeBar start={heatfield?.start ?? null} hours={heatfield?.hours ?? 48} hour={hour} layer={layer}
              disabled={!heatfield} note={heatError ?? 'Loading heatmap…'}
              playing={playing} onTogglePlay={toggle} onPause={pause}
              onHour={seek} onLayer={setLayer} />
          )}
        </MapView>
      </main>
    </>
  );
}
