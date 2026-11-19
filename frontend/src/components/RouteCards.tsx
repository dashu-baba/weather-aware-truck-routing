import type { Recommendation, ScoredRoute } from '../api/types';
import { duration, localTime, miles } from '../lib/format';
import { orderedRoutes, riskMiles } from '../lib/routes';
import { LEVELS, RISK_COLORS, routeColor } from '../map/palette';

type Props = {
  routes: ScoredRoute[];
  recommendation: Recommendation | null;
  interval: number;
  focusId: string | null;
  onFocus: (id: string) => void;
};

export function RouteCards({ routes, recommendation, interval, focusId, onFocus }: Props) {
  return (
    <div className="route-cards" aria-label="Ranked routes">
      {orderedRoutes(routes, recommendation?.order ?? []).map((route, rank) => {
        const scored = route.by_interval[String(interval)];
        const distribution = riskMiles(scored?.checkpoints ?? []);
        const total = distribution.reduce((sum, value) => sum + value, 0);
        return (
          <button key={route.id} type="button" className="route-card" data-route-id={route.id}
            aria-pressed={focusId === route.id} onClick={() => onFocus(route.id)}>
            <span className="card-top">
              <span className="route-name">
                <span className="route-swatch" style={{ background: routeColor(route.id) }} aria-hidden="true" />
                {route.label}<span className="route-rank">#{rank + 1}</span>
              </span>
              <span className="route-tags">
                {route.id === recommendation?.best && <span className="tag">BEST</span>}
                {scored && !scored.score.drivable && <span className="tag no-travel">NO TRAVEL</span>}
              </span>
            </span>
            <span className="route-stats">
              <span><span>Distance</span>{miles(route.summary.distance_mi)} mi</span>
              <span><span>Drive time</span>{duration(route.summary.duration_s)}</span>
              <span className="arrival"><span>Arrival · local time</span>{localTime(route.summary.arrival)}</span>
              {scored && <>
                <span><span>No Travel miles</span>{miles(scored.score.no_travel_mi)}</span>
                <span><span>Severe miles</span>{miles(scored.score.severe_mi)}</span>
                <span><span>High miles</span>{miles(scored.score.high_mi)}</span>
                <span><span>Average risk</span>{scored.score.avg_risk.toFixed(2)}</span>
                <span><span>Worst level</span>{LEVELS[scored.score.max_risk] ?? 'Unknown'}</span>
              </>}
              <span><span>Source</span>{route.source}</span>
            </span>
            {scored ? (
              <span className="riskbar" role="img"
                aria-label={`Risk miles: ${distribution.map((value, level) => `${LEVELS[level]} ${miles(value)} mi`).join('; ')}`}>
                {distribution.map((value, level) => (
                  <span key={level} style={{ width: `${total ? 100 * value / total : 0}%`, background: RISK_COLORS[level] }}
                    title={`${LEVELS[level]}: ${miles(value)} mi`} />
                ))}
              </span>
            ) : <span className="status-note">Scoring unavailable for this interval.</span>}
          </button>
        );
      })}
    </div>
  );
}
