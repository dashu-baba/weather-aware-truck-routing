import type { Recommendation as RecommendationData, RouteEntry } from '../api/types';
import { routeColor } from '../map/palette';

type Props = { recommendation: RecommendationData | null; routes: RouteEntry[]; interval: number };

export function Recommendation({ recommendation, routes, interval }: Props) {
  const best = routes.find(route => route.id === recommendation?.best);
  if (!recommendation) return <p className="recommendation">No recommendation available for this interval.</p>;
  if (recommendation.all_blocked) {
    return (
      <div className="recommendation blocked" role="alert">
        <strong>No route avoids No Travel conditions.</strong>
        <p>{best ? `Least bad: ${best.label} — consider a later departure.` : 'Consider a later departure.'}</p>
        <p className="recommendation-reason">Decided by: {recommendation.reason} (every {interval} mi)</p>
      </div>
    );
  }
  return (
    <div className="recommendation" style={best ? { borderLeftColor: routeColor(best.id) } : undefined}>
      <strong>{best ? `Recommended: ${best.label}` : 'No recommendation available.'}</strong>
      <p className="recommendation-reason">Decided by: {recommendation.reason} (every {interval} mi)</p>
    </div>
  );
}
