import { expect, it, vi } from 'vitest';
import { applyRouteFocus } from './layers';

it('focuses routes using only paint/layout properties, including sorting and checkpoint size', () => {
  const map = { setPaintProperty: vi.fn(), setLayoutProperty: vi.fn() };
  applyRouteFocus(map, 'B');
  const focused = ['==', ['get', 'id'], 'B'];
  expect(map.setPaintProperty).toHaveBeenCalledWith('route-casing', 'line-width', ['case', focused, 11, 7]);
  expect(map.setPaintProperty).toHaveBeenCalledWith('route-casing', 'line-opacity', ['case', focused, 0.85, 0.25]);
  expect(map.setPaintProperty).toHaveBeenCalledWith('route-risk', 'line-width', ['case', focused, 5, 3]);
  expect(map.setPaintProperty).toHaveBeenCalledWith('route-risk', 'line-opacity', ['case', focused, 1, 0.45]);
  expect(map.setPaintProperty).toHaveBeenCalledWith('checkpoints', 'circle-radius', ['case', focused, 5, 3]);
  expect(map.setLayoutProperty).toHaveBeenCalledWith('route-casing', 'line-sort-key', ['case', focused, 1, 0]);
  expect(map.setLayoutProperty).toHaveBeenCalledWith('route-risk', 'line-sort-key', ['case', focused, 1, 0]);
  expect(map.setLayoutProperty).toHaveBeenCalledWith('checkpoints', 'circle-sort-key', ['case', focused, 1, 0]);
});

it('keeps all initial routes visible before a recommendation exists', () => {
  const map = { setPaintProperty: vi.fn(), setLayoutProperty: vi.fn() };
  applyRouteFocus(map, null);
  expect(map.setPaintProperty).toHaveBeenCalledWith('route-casing', 'line-opacity', ['case', ['==', ['get', 'id'], ''], 0.85, 0.85]);
});
