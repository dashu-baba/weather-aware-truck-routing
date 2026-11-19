import { ApiError, fetchHeatmap, getPlan, postPlan } from '../api/client';
import type { PlanRequest } from '../api/types';
import type { PlanAction } from './planReducer';

const HEATMAP_RETRY_MS = 2000;
const HEATMAP_RETRIES = 10;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unable to reach the server. Please retry.';
}

// Abort cancels the pending timer immediately. Successful waits remove their listener.
export function waitForPoll(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(signal.reason); return; }
    const onAbort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, Math.max(0, ms));
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

export async function runPlanLifecycle(
  body: PlanRequest,
  signal: AbortSignal,
  dispatch: (action: PlanAction) => void,
): Promise<void> {
  if (signal.aborted) return;
  const send = (action: PlanAction) => { if (!signal.aborted) dispatch(action); };

  try {
    let plan = await postPlan(body, signal);
    if (signal.aborted) return;
    send({ type: 'status', plan });

    while (plan.status === 'weather') {
      await waitForPoll(plan.poll_after_ms ?? 2000, signal);
      try {
        plan = await getPlan(plan.plan_id, signal);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          throw new Error('This plan expired');
        }
        throw error;
      }
      if (signal.aborted) return;
      send({ type: 'status', plan });
    }

    if (plan.status !== 'done' || !plan.heatmap_url) return;

    // A 409 is transient. Other heatmap errors are soft failures; the plan stays usable.
    for (let retry = 0; retry <= HEATMAP_RETRIES; retry++) {
      try {
        const heatmap = await fetchHeatmap(plan.heatmap_url, signal);
        send({ type: 'heatmap', heatmap });
        return;
      } catch (error) {
        if (signal.aborted) return;
        if (error instanceof ApiError && error.status === 409 && retry < HEATMAP_RETRIES) {
          await waitForPoll(HEATMAP_RETRY_MS, signal);
          continue;
        }
        send({
          type: 'warning',
          detail: `Heatmap unavailable. Your scored plan is still ready. ${errorMessage(error)}`,
        });
        return;
      }
    }
  } catch (error) {
    if (!signal.aborted) send({ type: 'error', detail: errorMessage(error) });
  }
}
