import { Marker, type Map } from 'maplibre-gl';
import type { RouteEntry } from '../api/types';
import { parseUtc } from '../lib/format';
import { pointAtTime } from './geometry';
import { routeColor } from './palette';

// Forecast start and route departure need not coincide (departures may include minutes).
export function truckAtTime(route: RouteEntry, timestamp: number | null) {
  const elapsed = timestamp === null ? -1 : (timestamp - parseUtc(route.summary.departure).getTime()) / 1000;
  const arrived = elapsed >= route.summary.duration_s;
  return {
    position: pointAtTime(route, elapsed),
    opacity: arrived ? 0.5 : 1,
    title: `${route.label}: ${elapsed < 0 ? 'not departed' : arrived ? 'arrived' : 'en route'}`,
  };
}

// HTML markers are independent of the GeoJSON sources and survive hour/layer/focus changes.
export function createTrucks(map: Map, routes: RouteEntry[]) {
  const trucks = routes.map(route => {
    const element = document.createElement('div');
    element.className = 'truck-marker';
    element.style.backgroundColor = routeColor(route.id);
    element.textContent = route.id;
    element.setAttribute('role', 'img');
    const marker = new Marker({ element }).setLngLat(route.geometry[0]).addTo(map);
    return { route, marker, element };
  });
  const update = (timestamp: number | null) => {
    for (const { route, marker, element } of trucks) {
      const state = truckAtTime(route, timestamp);
      marker.setLngLat(state.position);
      // Let MapLibre retain opacity across pan/zoom and marker projection updates.
      marker.setOpacity(state.opacity);
      element.title = state.title;
      element.setAttribute('aria-label', state.title);
    }
  };
  update(null);
  return { update, remove: () => trucks.forEach(({ marker }) => marker.remove()) };
}
