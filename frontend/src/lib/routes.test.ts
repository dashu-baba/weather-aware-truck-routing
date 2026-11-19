import { expect, it } from 'vitest';
import { orderedRoutes, riskMiles } from './routes';
import { scoredResult, checkpoints } from '../hooks/__tests__/scoredFixtures';

it('weights risk bars by segment miles rather than checkpoint counts', () => {
  expect(riskMiles(checkpoints)).toEqual([0, 5, 10, 15, 10]);
  expect(riskMiles([])).toEqual([0, 0, 0, 0, 0]);
});

it('orders cards by the recommendation without mutating or dropping unranked routes', () => {
  expect(orderedRoutes(scoredResult.routes, ['B', 'A']).map(route => route.id)).toEqual(['B', 'A']);
  expect(scoredResult.routes.map(route => route.id)).toEqual(['A', 'B']);
  expect(orderedRoutes(scoredResult.routes, ['B']).map(route => route.id)).toEqual(['B', 'A']);
  expect(orderedRoutes(scoredResult.routes, []).map(route => route.id)).toEqual(['A', 'B']);
});
