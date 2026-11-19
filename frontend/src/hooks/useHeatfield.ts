import { useEffect, useMemo } from 'react';
import type { Heatmap, PlanResult } from '../api/types';
import { createHeatfield, type Heatfield } from '../map/heatfield';

// ?debug=1 logs how long each heatmap frame takes (cold render and cached swap) to the console.
export const isDebug = () => new URLSearchParams(window.location.search).get('debug') === '1';

type Built = { heatfield: Heatfield | null; error: string | null };

// Builds the renderer once the plan's heatmap has arrived. A heatmap that cannot be drawn is an error message,
// not a crash: the scored plan stays usable.
export function useHeatfield(result: PlanResult | null, heatmap: Heatmap | null): Built {
  const built = useMemo<Built>(() => {
    if (!result || !heatmap) return { heatfield: null, error: null };
    try {
      return { heatfield: createHeatfield({ meta: result.meta, heatmap }, { debug: isDebug() }), error: null };
    } catch (error) {
      return { heatfield: null, error: error instanceof Error ? error.message : 'The weather map could not be drawn.' };
    }
  }, [result, heatmap]);

  useEffect(() => {
    if (isDebug()) (window as unknown as { __heatfield?: Heatfield | null }).__heatfield = built.heatfield;
  }, [built.heatfield]);

  return built;
}
