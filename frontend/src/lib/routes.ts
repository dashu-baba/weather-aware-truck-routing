import type { Checkpoint, ScoredRoute } from '../api/types';

export function riskMiles(checkpoints: Checkpoint[]): [number, number, number, number, number] {
  const miles: [number, number, number, number, number] = [0, 0, 0, 0, 0];
  for (const checkpoint of checkpoints) miles[checkpoint.risk] += checkpoint.segment_mi;
  return miles;
}

export function orderedRoutes(routes: ScoredRoute[], order: string[]): ScoredRoute[] {
  const ranks = new Map(order.map((id, rank) => [id, rank]));
  return [...routes].sort((a, b) =>
    (ranks.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (ranks.get(b.id) ?? Number.MAX_SAFE_INTEGER));
}
