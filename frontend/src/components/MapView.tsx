import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { loadBasemap } from '../map/basemap';

// Vite must bundle the worker explicitly: MapLibre's relative default URL is
// otherwise resolved inside Vite's optimized dependency directory in development.
maplibregl.setWorkerUrl(workerUrl);

export function MapView() {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [message, setMessage] = useState('');

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

  return (
    <section className="map-pane" aria-label="Trip map">
      <div className="map-container" ref={container} />
      <div className="map-badge"><span className="live-dot" /> WEATHER-AWARE ROUTING</div>
      {message && <p className="map-message" role="status">{message}</p>}
      <div className="map-intro">
        <strong>A clearer road ahead.</strong>
        <span>Enter your trip to compare routes and weather risk.</span>
      </div>
    </section>
  );
}
