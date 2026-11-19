import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { loadBasemap } from '../map/basemap';
import type { RouteEntry } from '../api/types';
import { routeLines } from '../map/geometry';
import { addRouteLayers } from '../map/layers';

// Vite must bundle the worker explicitly: MapLibre's relative default URL is
// otherwise resolved inside Vite's optimized dependency directory in development.
maplibregl.setWorkerUrl(workerUrl);

const EMPTY_ROUTES: RouteEntry[] = [];

export function MapView({ routes = EMPTY_ROUTES }: { routes?: RouteEntry[] }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [message, setMessage] = useState('');
  const [ready, setReady] = useState(false);
  const fitted = useRef<RouteEntry[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let map: maplibregl.Map | undefined;

    void loadBasemap(controller.signal).then(style => {
      if (controller.signal.aborted || !container.current) return;

      try {
        map = new maplibregl.Map({
          container: container.current,
          style,
          center: [-96, 38],
          zoom: 3.6,
          attributionControl: { compact: true },
        });
        mapRef.current = map;
        map.on('load', () => {
          if (!map || controller.signal.aborted) return;
          addRouteLayers(map);
          setReady(true);
        });
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');

        if (Object.keys(style.sources).length === 0) {
          setMessage('Basemap unavailable. Showing a blank map.');
        }
        map.on('error', () => {
          setMessage('Some map details could not be loaded.');
        });
      } catch {
        setMessage('The map could not start. Check that WebGL is enabled in your browser.');
      }
    });

    return () => {
      controller.abort();
      map?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const source = map.getSource<maplibregl.GeoJSONSource>('route-casing');
    source?.setData(routeLines(routes));

    if (!routes.length) { fitted.current = null; return; }
    if (fitted.current === routes) return;

    const bounds = new maplibregl.LngLatBounds();
    routes.forEach(route => route.geometry.forEach(point => bounds.extend(point)));
    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 60, duration: 600 });
    fitted.current = routes;
  }, [ready, routes]);

  return (
    <section className="map-pane" aria-label="Trip map">
      <div className="map-container" ref={container} />
      <div className="map-badge"><span className="live-dot" /> WEATHER-AWARE ROUTING</div>
      {message && <p className="map-message" role="status">{message}</p>}
      {!routes.length && (
        <div className="map-intro">
          <strong>A clearer road ahead.</strong>
          <span>Enter your trip to compare routes and weather risk.</span>
        </div>
      )}
    </section>
  );
}
