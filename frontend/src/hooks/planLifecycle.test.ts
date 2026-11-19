import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, fetchHeatmap, getPlan, postPlan } from '../api/client';
import { runPlanLifecycle, waitForPoll } from './planLifecycle';
import { initialPlanState, planReducer } from './planReducer';
import type { PlanAction } from './planReducer';
import { donePlan, heatmap, plan, request } from './__tests__/fixtures';

vi.mock('../api/client', async importOriginal => ({
  ...await importOriginal<typeof import('../api/client')>(),
  postPlan: vi.fn(), getPlan: vi.fn(), fetchHeatmap: vi.fn(),
}));

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(postPlan).mockReset();
  vi.mocked(getPlan).mockReset();
  vi.mocked(fetchHeatmap).mockReset().mockResolvedValue(heatmap);
});
afterEach(() => vi.useRealTimers());

function session(controller = new AbortController()) {
  let state = planReducer(initialPlanState, { type: 'submit' });
  const actions: PlanAction[] = [];
  const completion = runPlanLifecycle(request, controller.signal, action => {
    actions.push(action);
    state = planReducer(state, action);
  });
  return { controller, completion, actions, state: () => state };
}

// Resolve the POST microtasks without advancing the polling timer.
const flushPost = () => vi.advanceTimersByTimeAsync(0);

describe('plan lifecycle', () => {
  it('publishes first routes immediately and uses each response poll_after_ms without overlapping polls', async () => {
    vi.mocked(postPlan).mockResolvedValue(plan());
    let finishPoll!: (value: ReturnType<typeof plan>) => void;
    vi.mocked(getPlan)
      .mockImplementationOnce(() => new Promise(resolve => { finishPoll = resolve; }))
      .mockResolvedValueOnce(donePlan());
    const run = session();
    await flushPost();
    expect(run.state().routes).toHaveLength(1);
    expect(run.state().phase).toBe('weather');
    await vi.advanceTimersByTimeAsync(1499);
    expect(getPlan).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(getPlan).toHaveBeenCalledExactlyOnceWith('test-plan', run.controller.signal);
    await vi.advanceTimersByTimeAsync(10000);
    expect(getPlan).toHaveBeenCalledTimes(1);
    finishPoll(plan({ poll_after_ms: 700 }));
    await vi.advanceTimersByTimeAsync(699);
    expect(getPlan).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    await run.completion;
    expect(getPlan).toHaveBeenCalledTimes(2);
    expect(run.state().phase).toBe('done');
    expect(fetchHeatmap).toHaveBeenCalledWith('/api/plan/test-plan/heatmap', run.controller.signal);
    expect(run.state().heatmap).toBe(heatmap);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not poll an already-done POST', async () => {
    vi.mocked(postPlan).mockResolvedValue(donePlan());
    const run = session();
    await run.completion;
    expect(getPlan).not.toHaveBeenCalled();
    expect(run.state().phase).toBe('done');
    expect(run.state().heatmap).toBe(heatmap);
  });

  it('uses a 2-second fallback when weather poll_after_ms is null', async () => {
    vi.mocked(postPlan).mockResolvedValue(plan({ poll_after_ms: null }));
    vi.mocked(getPlan).mockResolvedValue(donePlan());
    const run = session();
    await vi.advanceTimersByTimeAsync(1999);
    expect(getPlan).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    await run.completion;
    expect(getPlan).toHaveBeenCalledTimes(1);
  });

  it.each(['post', 'poll'])('stops on a failed status from %s', async source => {
    const failed = plan({ status: 'failed', error: 'Weather service is busy.' });
    vi.mocked(postPlan).mockResolvedValue(source === 'post' ? failed : plan());
    vi.mocked(getPlan).mockResolvedValue(failed);
    const run = session();
    await vi.runAllTimersAsync();
    await run.completion;
    expect(run.state().error).toBe('Weather service is busy.');
    expect(run.state().routes).toHaveLength(1);
    expect(fetchHeatmap).not.toHaveBeenCalled();
    expect(getPlan).toHaveBeenCalledTimes(source === 'post' ? 0 : 1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('shows an expired message for poll 404, rather than an opaque API detail', async () => {
    vi.mocked(postPlan).mockResolvedValue(plan());
    vi.mocked(getPlan).mockRejectedValue(new ApiError(404, { detail: 'Not found.' }));
    const run = session();
    await vi.runAllTimersAsync();
    await run.completion;
    expect(run.state().error).toBe('This plan expired');
    expect(run.state().routes).toHaveLength(1);
  });

  it.each([400, 422, 429, 502, 504])('preserves the readable POST error for HTTP %i', async status => {
    const error = new ApiError(status, { detail: 'Unable to plan this trip.' });
    vi.mocked(postPlan).mockRejectedValue(error);
    const run = session();
    await run.completion;
    expect(run.state().error).toBe(error.detail);
    expect(getPlan).not.toHaveBeenCalled();
  });

  it('retries heatmap 409 after 2 seconds, without polling the completed plan', async () => {
    vi.mocked(postPlan).mockResolvedValue(donePlan());
    vi.mocked(fetchHeatmap).mockRejectedValueOnce(new ApiError(409, { detail: 'Not ready.' })).mockResolvedValueOnce(heatmap);
    const run = session();
    await flushPost();
    expect(run.state().phase).toBe('done');
    await vi.advanceTimersByTimeAsync(1999);
    expect(fetchHeatmap).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    await run.completion;
    expect(fetchHeatmap).toHaveBeenCalledTimes(2);
    expect(run.state().heatmap).toBe(heatmap);
    expect(getPlan).not.toHaveBeenCalled();
  });

  it('stops after ten heatmap retries with a soft warning and an intact result', async () => {
    vi.mocked(postPlan).mockResolvedValue(donePlan());
    vi.mocked(fetchHeatmap).mockRejectedValue(new ApiError(409, { detail: 'Not ready.' }));
    const run = session();
    await vi.runAllTimersAsync();
    await run.completion;
    expect(fetchHeatmap).toHaveBeenCalledTimes(11); // Initial fetch plus ten retries.
    expect(run.state().phase).toBe('done');
    expect(run.state().plan?.result).not.toBeNull();
    expect(run.state().error).toBeNull();
    expect(run.state().warning).toContain('Heatmap unavailable');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not retry non-409 heatmap errors', async () => {
    vi.mocked(postPlan).mockResolvedValue(donePlan());
    vi.mocked(fetchHeatmap).mockRejectedValue(new ApiError(502, { detail: 'Unavailable.' }));
    const run = session();
    await run.completion;
    expect(fetchHeatmap).toHaveBeenCalledTimes(1);
    expect(run.state().phase).toBe('done');
    expect(run.state().warning).toContain('Unavailable.');
  });

  it('cancels a pending poll timer without reporting an error', async () => {
    vi.mocked(postPlan).mockResolvedValue(plan());
    const run = session();
    await flushPost();
    expect(vi.getTimerCount()).toBe(1);
    run.controller.abort();
    await run.completion;
    expect(vi.getTimerCount()).toBe(0);
    await vi.runAllTimersAsync();
    expect(getPlan).not.toHaveBeenCalled();
    expect(run.state().error).toBeNull();
  });

  it('ignores a late POST response after abort', async () => {
    let finish!: (value: ReturnType<typeof plan>) => void;
    vi.mocked(postPlan).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const run = session();
    run.controller.abort();
    finish(plan());
    await run.completion;
    expect(run.actions).toEqual([]);
    expect(getPlan).not.toHaveBeenCalled();
  });

  it('ignores a late poll response after abort', async () => {
    vi.mocked(postPlan).mockResolvedValue(plan());
    let finish!: (value: ReturnType<typeof plan>) => void;
    vi.mocked(getPlan).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const run = session();
    await vi.advanceTimersByTimeAsync(1500);
    run.controller.abort();
    finish(donePlan());
    await run.completion;
    expect(run.actions).toHaveLength(1);
    expect(fetchHeatmap).not.toHaveBeenCalled();
  });

  it('cancels heatmap retries and ignores late heatmap responses', async () => {
    vi.mocked(postPlan).mockResolvedValue(donePlan());
    vi.mocked(fetchHeatmap).mockRejectedValue(new ApiError(409, {}));
    const run = session();
    await flushPost();
    run.controller.abort();
    await run.completion;
    expect(fetchHeatmap).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
    expect(run.state().warning).toBeNull();

    let finish!: (value: typeof heatmap) => void;
    vi.mocked(fetchHeatmap).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const second = session();
    await flushPost();
    second.controller.abort();
    finish(heatmap);
    await second.completion;
    expect(second.state().heatmap).toBeNull();
  });

  it('skips a session that is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    await session(controller).completion;
    expect(postPlan).not.toHaveBeenCalled();
    await expect(waitForPoll(100, controller.signal)).rejects.toBe(controller.signal.reason);
    expect(vi.getTimerCount()).toBe(0);
  });
});
