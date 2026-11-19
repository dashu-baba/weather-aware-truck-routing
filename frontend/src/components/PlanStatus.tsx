import type { PlanState } from '../hooks/planReducer';

export function stageLabel(stage: string, queued: boolean): string {
  if (queued) return 'Waiting for a worker…';
  const checkpointStage = /^checkpoints_(\d+)$/.exec(stage);
  if (checkpointStage) return `Weather for ${checkpointStage[1]}-mile checkpoints`;
  switch (stage) {
    case 'routes': return 'Preparing routes';
    case 'heatmap': return 'Heatmap grid';
    case 'done': return 'Weather scoring complete';
    default: return 'Fetching weather';
  }
}

type Props = {
  state: PlanState;
  interval?: number;
  onRetry: () => void;
};

export function PlanStatus({ state, interval = 25, onRetry }: Props) {
  const { phase, plan } = state;
  const early = plan?.partial?.intervals[String(interval)]?.recommendation
    ?? plan?.partial?.intervals['25']?.recommendation;

  if (phase === 'idle') return null;

  return (
    <section className="plan-status" aria-label="Plan status" aria-live="polite" aria-atomic="true">
      {phase === 'posting' && (
        <p className="status-heading"><span className="spinner" aria-hidden="true" />Finding truck routes…</p>
      )}
      {phase === 'weather' && plan && (
        <>
          <div className="status-heading">
            <span className="spinner" aria-hidden="true" />
            <span>{stageLabel(plan.progress.stage, plan.progress.queued)}</span>
            <strong>{Math.round(plan.progress.percent)}%</strong>
          </div>
          <progress max="100" value={plan.progress.percent} aria-label="Weather progress" />
          <p className="status-note">Routes are ready. Checking weather along the way.</p>
          {early?.best && (
            <div className="early-pick">
              Early pick: Route {early.best}
              <span>{early.reason}</span>
              {early.all_blocked && <span>All routes have No Travel conditions.</span>}
            </div>
          )}
        </>
      )}
      {phase === 'done' && (
        <>
          <p className="ready-label">✓ Weather scoring complete</p>
          {plan?.heatmap_url && !state.heatmap && !state.warning && (
            <p className="status-note">Downloading weather grid…</p>
          )}
        </>
      )}
      {state.error && (
        <div className="error-box" role="alert">
          <p>{state.error}</p>
          <button type="button" onClick={onRetry}>Retry</button>
        </div>
      )}
      {state.warning && <p className="warning">{state.warning}</p>}
    </section>
  );
}
