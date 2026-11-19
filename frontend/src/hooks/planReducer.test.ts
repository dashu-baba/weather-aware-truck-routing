import { describe, expect, it } from 'vitest';
import { initialPlanState, planReducer } from './planReducer';
import { donePlan, heatmap, plan, result } from './__tests__/fixtures';

describe('usePlan reducer', () => {
  it('transitions idle → posting → weather → done and keeps the first routes stable', () => {
    const posting = planReducer(initialPlanState, { type: 'submit' });
    expect(posting.phase).toBe('posting');
    const first = plan();
    const weather = planReducer(posting, { type: 'status', plan: first });
    expect(weather.phase).toBe('weather');
    expect(weather.routes).toBe(first.routes);
    const partial = { intervals: { '25': { recommendation: result.recommendation['25'], scores: {} } } };
    const progress = planReducer(weather, { type: 'status', plan: plan({ partial, routes: structuredClone(first.routes) }) });
    expect(progress.plan?.partial).toEqual(partial);
    expect(progress.routes).toBe(first.routes);
    const done = planReducer(progress, { type: 'status', plan: donePlan() });
    expect(done.phase).toBe('done');
    expect(done.plan?.result).toBe(result);
    expect(done.routes).toBe(first.routes);
  });

  it('accepts an already-done POST directly', () => {
    expect(planReducer(initialPlanState, { type: 'status', plan: donePlan() }).phase).toBe('done');
  });

  it('preserves routes and exposes the backend failure message', () => {
    const weather = planReducer(initialPlanState, { type: 'status', plan: plan() });
    const failed = planReducer(weather, { type: 'status', plan: plan({ status: 'failed', error: 'Weather service is busy.' }) });
    expect(failed.phase).toBe('error');
    expect(failed.error).toBe('Weather service is busy.');
    expect(failed.routes).toBe(weather.routes);
    expect(planReducer(weather, { type: 'status', plan: plan({ status: 'failed' }) }).error).toContain('Please retry');
  });

  it('preserves routes when a poll reports 404', () => {
    const weather = planReducer(initialPlanState, { type: 'status', plan: plan() });
    const expired = planReducer(weather, { type: 'error', detail: 'This plan expired' });
    expect(expired.phase).toBe('error');
    expect(expired.error).toBe('This plan expired');
    expect(expired.routes).toBe(weather.routes);
  });

  it('keeps heatmap failures soft and stores a successful heatmap', () => {
    const done = planReducer(initialPlanState, { type: 'status', plan: donePlan() });
    const warning = planReducer(done, { type: 'warning', detail: 'Heatmap unavailable' });
    expect(warning.phase).toBe('done');
    expect(warning.plan?.result).toBe(result);
    const ready = planReducer(warning, { type: 'heatmap', heatmap });
    expect(ready.heatmap).toBe(heatmap);
    expect(ready.warning).toBeNull();
  });

  it('clears old progress, errors, routes and heatmap on a new submission, remembering Re-plan', () => {
    let state = planReducer(initialPlanState, { type: 'status', plan: donePlan() });
    state = planReducer(state, { type: 'heatmap', heatmap });
    state = planReducer(state, { type: 'warning', detail: 'Old warning' });
    state = planReducer(state, { type: 'error', detail: 'Old error' });
    expect(planReducer(state, { type: 'submit' })).toEqual({ ...initialPlanState, phase: 'posting', hasPlan: true });
  });
});
