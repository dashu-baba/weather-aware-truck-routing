import { useCallback, useEffect, useReducer, useRef } from 'react';
import type { PlanRequest } from '../api/types';
import { initialPlanState, planReducer } from './planReducer';
import { runPlanLifecycle } from './planLifecycle';

export function usePlan() {
  const [state, dispatch] = useReducer(planReducer, initialPlanState);
  const current = useRef<AbortController | null>(null);
  const lastBody = useRef<PlanRequest | null>(null);

  useEffect(() => () => { current.current?.abort(); }, []);

  const submit = useCallback((body: PlanRequest) => {
    current.current?.abort();
    const controller = new AbortController();
    current.current = controller;
    // Editing the form after an error must not change the body sent by Retry.
    const saved = structuredClone(body);
    lastBody.current = saved;
    dispatch({ type: 'submit' });
    void runPlanLifecycle(saved, controller.signal, dispatch);
  }, []);

  const retry = useCallback(() => {
    if (lastBody.current) submit(lastBody.current);
  }, [submit]);

  return { state, submit, retry };
}
