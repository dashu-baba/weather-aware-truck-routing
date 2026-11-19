import type { Heatmap, PlanStatus, RouteEntry } from '../api/types';

export type PlanState = {
  phase: 'idle' | 'posting' | 'weather' | 'done' | 'error';
  hasPlan: boolean;
  plan: PlanStatus | null;
  routes: RouteEntry[];
  heatmap: Heatmap | null;
  error: string | null;
  warning: string | null;
};

export const initialPlanState: PlanState = {
  phase: 'idle',
  hasPlan: false,
  plan: null,
  routes: [],
  heatmap: null,
  error: null,
  warning: null,
};

export type PlanAction =
  | { type: 'submit' }
  | { type: 'status'; plan: PlanStatus }
  | { type: 'error'; detail: string }
  | { type: 'heatmap'; heatmap: Heatmap }
  | { type: 'warning'; detail: string };

export function planReducer(state: PlanState, action: PlanAction): PlanState {
  switch (action.type) {
    case 'submit':
      return { ...initialPlanState, hasPlan: state.hasPlan, phase: 'posting' };
    case 'status':
      return {
        ...state,
        plan: action.plan,
        hasPlan: state.hasPlan || action.plan.routes.length > 0,
        // Keep the first routes' identity: status polls must not redraw or refit the map.
        routes: state.routes.length ? state.routes : action.plan.routes,
        phase: action.plan.status === 'failed' ? 'error' : action.plan.status,
        error: action.plan.status === 'failed'
          ? action.plan.error || 'Weather scoring failed. Please retry.'
          : null,
      };
    case 'error':
      return { ...state, phase: 'error', error: action.detail };
    case 'heatmap':
      return { ...state, heatmap: action.heatmap, warning: null };
    case 'warning':
      return { ...state, warning: action.detail };
  }
}
