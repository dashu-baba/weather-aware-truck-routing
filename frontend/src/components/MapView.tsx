import { useEffect, useRef, useState, type ReactNode } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { loadBasemap } from '../map/basemap';
import type { PlanResult, RouteEntry } from '../api/types';
import { checkpointFeatures, routeLines, routePieces } from '../map/geometry';
import { addResultLayers, addRouteLayers, applyRouteFocus } from '../map/layers';
import { checkpointPopup } from '../map/popup';
import type { Heatfield, HeatLayer } from '../map/heatfield';
import { drawHeatFrame, hideHeatfield, showHeatfield } from '../map/heatLayers';
import { attachHover, type HoverContext } from '../map/hover';
import { isDebug } from '../hooks/useHeatfield';

// Vite must bundle the worker explicitly: MapLibre's relative default URL is
// otherwise resolved inside Vite's optimized dependency directory in development.
maplibregl.setWorkerUrl(workerUrl);

const EMPTY_ROUTES: RouteEntry[] = [];

type Props = {
  routes?: RouteEntry[];
  result?: PlanResult | null;
  interval?: number;
  focusId?: string | null;
  heatfield?: Heatfield | null;
  heatLayer?: HeatLayer;
  hour?: number;
  children?: ReactNode; // controls drawn over the map, such as the legend and the time bar
};

export function MapView({
  routes = EMPTY_ROUTES, result = null, interval = 25, focusId = null,
  heatfield = null, heatLayer = 'risk', hour = 0, children,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [message, setMessage] = useState('');
  const [ready, setReady] = useState(false);
  const fitted = useRef<RouteEntry[] | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const checkpointContext = useRef<{ result: PlanResult | null; interval: number }>({ result: null, interval: 25 });
  const heatCanvas = useRef<HTMLCanvasElement | null>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  const hoverContext = useRef<HoverContext | null>(null);
  const hover = useRef<ReturnType<typeof attachHover> | null>(null);

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
          addResultLayers(map);
          map.on('click', 'checkpoints', event => {
            const properties = event.features?.[0]?.properties;
            if (!properties || typeof properties.id !== 'string' || !Number.isInteger(properties.idx)) return;
            const context = checkpointContext.current;
            const route = context.result?.routes.find(item => item.id === properties.id);
            const checkpoint = route?.by_interval[String(context.interval)]?.checkpoints[properties.idx];
            if (!map || !route || !checkpoint) return;
            popupRef.current?.remove();
            popupRef.current = new maplibregl.Popup({ maxWidth: '300px' })
              .setLngLat(event.lngLat)
              .setDOMContent(checkpointPopup(route.label, checkpoint))
              .addTo(map);
          });
          map.on('mouseenter', 'checkpoints', () => { if (map) map.getCanvas().style.cursor = 'pointer'; });
          map.on('mouseleave', 'checkpoints', () => { if (map) map.getCanvas().style.cursor = ''; });
          if (tooltip.current) hover.current = attachHover(map, tooltip.current, () => hoverContext.current);
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
      hover.current?.detach();
      hover.current = null;
      popupRef.current?.remove();
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

  useEffect(() => {
    checkpointContext.current = { result, interval };
    popupRef.current?.remove();
    popupRef.current = null;
    const map = mapRef.current;
    if (!ready || !map) return;
    const empty = { type: 'FeatureCollection' as const, features: [] };
    map.getSource<maplibregl.GeoJSONSource>('route-risk')?.setData(result ? routePieces(result, interval) : empty);
    map.getSource<maplibregl.GeoJSONSource>('checkpoints')?.setData(result ? checkpointFeatures(result, interval) : empty);
    map.getCanvas().style.cursor = '';
  }, [ready, result, interval]);

  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) applyRouteFocus(map, focusId);
  }, [ready, focusId]);

  // The weather image is added when a heatmap arrives, replaced by the next plan's, and removed when a plan starts.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (!heatfield) {
      hideHeatfield(map);
      heatCanvas.current = null;
      hoverContext.current = null;
      hover.current?.update();
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = heatfield.width;
    canvas.height = heatfield.height;
    heatCanvas.current = canvas;
    showHeatfield(map, heatfield, canvas);
  }, [ready, heatfield]);

  // Moving the slider or switching layers only swaps the image's pixels, once per animation frame.
  useEffect(() => {
    const map = mapRef.current;
    const canvas = heatCanvas.current;
    if (!ready || !map || !heatfield || !canvas) return;
    const frame = requestAnimationFrame(() => {
      const shown = Math.min(Math.max(0, hour), heatfield.hours - 1);
      const started = performance.now();
      drawHeatFrame(map, heatfield, canvas, heatLayer, shown);
      if (isDebug()) console.debug(`[heatfield] swap ${heatLayer}:${shown}: ${(performance.now() - started).toFixed(2)} ms`);
      hoverContext.current = { field: heatfield, layer: heatLayer, hour: shown, start: heatfield.start };
      hover.current?.update();
      heatfield.prerenderNeighbours(heatLayer, shown);
    });
    return () => cancelAnimationFrame(frame);
  }, [ready, heatfield, heatLayer, hour]);

  return (
    <section className="map-pane" aria-label="Trip map">
      <div className="map-container" ref={container} />
      <div className="map-badge"><span className="live-dot" /> WEATHER-AWARE ROUTING</div>
      {message && <p className="map-message" role="status">{message}</p>}
      <div className="heat-hover" ref={tooltip} hidden />
      {children}
      {!routes.length && (
        <div className="map-intro">
          <strong>A clearer road ahead.</strong>
          <span>Enter your trip to compare routes and weather risk.</span>
        </div>
      )}
    </section>
  );
}
