import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { IntervalToggle } from './IntervalToggle';
import { Recommendation } from './Recommendation';
import { RouteCards, sourceLabel } from './RouteCards';
import { localTime } from '../lib/format';
import { scoredResult, scoredRoute } from '../hooks/__tests__/scoredFixtures';

const renderCards = (interval = 25) => renderToStaticMarkup(
  <RouteCards routes={scoredResult.routes} recommendation={scoredResult.recommendation[String(interval)]}
    interval={interval} focusId="B" onFocus={() => {}} />,
);

describe('result components', () => {
  it('renders the supplied intervals and marks only the selected interval pressed', () => {
    const html = renderToStaticMarkup(<IntervalToggle intervals={[10, 25, 50]} interval={25} onChange={() => {}} />);
    expect(html).toContain('aria-pressed="true">25 mi');
    expect(html).toContain('aria-pressed="false">10 mi');
    expect(html).toContain('aria-pressed="false">50 mi');
  });

  it('explains the recommended route and selected spacing', () => {
    const html = renderToStaticMarkup(<Recommendation recommendation={scoredResult.recommendation['50']} routes={scoredResult.routes} interval={50} />);
    expect(html).toContain('Recommended: Route A');
    expect(html).toContain('border-left-color:#1f5eff');
    expect(html).toContain('shorter travel time');
    expect(html).toContain('every 50 mi');
  });

  it('shows a warning and least-bad route when all routes are blocked; handles null best safely', () => {
    const recommendation = scoredResult.recommendation['25'];
    const html = renderToStaticMarkup(<Recommendation recommendation={recommendation} routes={scoredResult.routes} interval={25} />);
    expect(html).toContain('No route avoids No Travel conditions.');
    expect(html).toContain('Least bad: Route B');
    expect(html).toContain('consider a later departure');
    const empty = renderToStaticMarkup(<Recommendation recommendation={{ ...recommendation, best: null }} routes={scoredResult.routes} interval={25} />);
    expect(empty).not.toContain('Route null');
    expect(empty).toContain('Consider a later departure.');
    expect(renderToStaticMarkup(<Recommendation recommendation={null} routes={[]} interval={25} />)).toContain('No recommendation available');
  });

  it('orders cards, tags BEST/NO TRAVEL, displays required stats and local arrivals', () => {
    const html = renderCards();
    expect(html.indexOf('data-route-id="B"')).toBeLessThan(html.indexOf('data-route-id="A"'));
    expect(html).toContain('BEST');
    expect(html).toContain('NO TRAVEL');
    for (const label of ['Distance', 'Drive time', 'No Travel miles', 'Severe miles', 'High miles', 'Average risk', 'Worst level']) {
      expect(html).toContain(label);
    }
    expect(html).toContain(localTime(scoredRoute.summary.arrival));
    expect(html).toContain('2.625');
    expect(html).toContain('Risk miles: Low 0 mi; Moderate 5 mi; High 10 mi; Severe 15 mi; No Travel 10 mi');
    expect(html).toContain('width:37.5%');
    expect(renderCards(50)).not.toContain('NO TRAVEL');
  });

  it('shows each route note on its own card and names the route source plainly', () => {
    const note = '1.8 mi of this route may not suit trucks (TomTom could not apply truck rules)';
    const withNote = { ...scoredRoute, warnings: [note] };
    const html = renderToStaticMarkup(<RouteCards routes={[withNote]} recommendation={null} interval={25} focusId={null} onFocus={() => {}} />);
    expect(html).toContain(`<span class="route-note">${note}</span>`);
    expect(renderCards()).not.toContain('route-note');
    expect(sourceLabel('tomtom')).toBe('TomTom');
    expect(sourceLabel('tomtom-via')).toBe('TomTom detour');
    expect(sourceLabel('fake')).toBe('fake');
  });

  it('renders zero-mile bars and missing interval scores without NaN or crashes', () => {
    const empty = { ...scoredRoute, by_interval: { '25': { ...scoredRoute.by_interval['25'], checkpoints: [] } } };
    const html = renderToStaticMarkup(<RouteCards routes={[empty]} recommendation={null} interval={25} focusId={null} onFocus={() => {}} />);
    expect(html).not.toMatch(/NaN|Infinity/);
    expect(renderCards(99)).toContain('Scoring unavailable');
  });
});
