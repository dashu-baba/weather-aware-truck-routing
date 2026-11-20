import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { PlanStatus, stageLabel } from './PlanStatus';
import { initialPlanState, planReducer } from '../hooks/planReducer';
import { donePlan, plan } from '../hooks/__tests__/fixtures';

const render = (status = plan(), interval?: number) => renderToStaticMarkup(
  <PlanStatus state={planReducer(initialPlanState, { type: 'status', plan: status })} interval={interval} onRetry={() => {}} />,
);

describe('PlanStatus', () => {
  it.each([10, 25, 50])('labels %i-mile checkpoint stages', interval => {
    expect(stageLabel(`checkpoints_${interval}`, false)).toBe(`Weather for ${interval}-mile checkpoints`);
  });

  it('labels queued jobs, heatmap work and unknown stages', () => {
    expect(stageLabel('heatmap', true)).toBe('Checking weather along each route…');
    expect(stageLabel('heatmap', false)).toBe('Heatmap grid');
    expect(stageLabel('future-stage', false)).toBe('Fetching weather');
  });

  it('shows progress and the selected interval early pick, falling back to 25 miles', () => {
    const partial = { intervals: {
      '25': { recommendation: { best: 'B', order: ['B'], reason: 'fewer Severe miles', all_blocked: false }, scores: {} },
      '50': { recommendation: { best: 'C', order: ['C'], reason: 'less risk', all_blocked: false }, scores: {} },
    } };
    expect(render(plan({ partial }))).toContain('Early pick: Route B');
    expect(render(plan({ partial }), 50)).toContain('Early pick: Route C');
    expect(render(plan({ partial }), 10)).toContain('Early pick: Route B');
    expect(render(plan({ partial }))).toContain('value="20"');
    expect(render()).not.toContain('Early pick:');
  });

  it('does not promise result cards during phase 3 and offers Retry after failure', () => {
    expect(render(donePlan())).not.toContain('Weather scoring complete');
    expect(render(donePlan())).not.toContain('compare your routes below');
    const failed = render(plan({ status: 'failed', error: 'Try again later.' }));
    expect(failed).toContain('role="alert"');
    expect(failed).toContain('Try again later.');
    expect(failed).toContain('Retry');
  });
});

it('keeps the local TruckLoader for weather only; the full-page loader covers route finding', () => {
  const submitted = planReducer(initialPlanState, { type: 'submit' });
  const posting = renderToStaticMarkup(<PlanStatus state={submitted} onRetry={() => {}} />);
  expect(posting).not.toContain('truck-loader');
  expect(posting).toContain('Route planning progress');
  const weather = plan({ progress: { stage: 'checkpoints_25', done: 42, total: 100, percent: 42, queued: false } });
  expect(render(weather)).toContain('truck-loader');
  expect(render(weather)).toContain('Weather for 25-mile checkpoints · 42%');
  expect(render(weather)).toContain('value="42"');
  expect(render(plan({ progress: { ...weather.progress, queued: true } }))).toContain('Checking weather along each route…');
  expect(render(donePlan())).not.toContain('truck-loader');
  expect(render(donePlan())).not.toContain('Downloading weather grid');
  expect(render(plan({ status: 'failed', error: 'Failed' }))).not.toContain('truck-loader');
  expect(renderToStaticMarkup(<PlanStatus state={initialPlanState} onRetry={() => {}} />)).toBe('');
});
