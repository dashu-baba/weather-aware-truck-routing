import { useEffect, useRef, useState, type ReactNode } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { loadBasemap } from '../map/basemap';
import type { PlanResult, RouteEntry } from '../api/types';
import { checkpointFeatures, fitPadding, routeLines, routePieces } from '../map/geometry';
import { addResultLayers, addRouteLayers, applyRouteFocus } from '../map/layers';
import { checkpointPopup } from '../map/popup';
import type { Heatfield, HeatLayer } from '../map/heatfield';
import { drawHeatFrame, hideHeatfield, showHeatfield } from '../map/heatLayers';
import { attachHover, type HoverContext } from '../map/hover';
import { isDebug } from '../hooks/useHeatfield';
import { createTrucks } from '../map/trucks';
import { attachWindParticles, createWindParticles, type WindParticles } from '../map/windParticles';
import { parseUtc } from '../lib/format';
import { createPlacePins } from '../map/places';
import type { PlaceTarget, TripPlaces } from '../lib/places';
import { initialTripPlaces } from '../hooks/tripPlacesReducer';

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
  places?: TripPlaces;
  pickTarget?: PlaceTarget | null;
  onPick?: (target: PlaceTarget, lat: number, lon: number) => void;
  onCancelPick?: () => void;
  children?: ReactNode; // controls drawn over the map, such as the legend and the time bar
};

export function MapView({
  routes = EMPTY_ROUTES, result = null, interval = 25, focusId = null,
  heatfield = null, heatLayer = 'risk', hour = 0, children,
  places = initialTripPlaces, pickTarget = null, onPick, onCancelPick,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [message, setMessage] = useState('');
  const [ready, setReady] = useState(false);
  const fitted = useRef<RouteEntry[] | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const checkpointContext = useRef<{ result: PlanResult | null; interval: number }>({ result: null, interval: 25 });
  const pins = useRef<ReturnType<typeof createPlacePins> | null>(null);
  const pickContext = useRef({ target: pickTarget, onPick });
  const trucks = useRef<ReturnType<typeof createTrucks> | null>(null);
  const heatCanvas = useRef<HTMLCanvasElement | null>(null);
  const wind = useRef<WindParticles | null>(null);
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
        map.getCanvas().style.cursor = pickContext.current.target ? 'crosshair' : '';
        map.on('click', event => {
          const context = pickContext.current;
          if (context.target) context.onPick?.(context.target, event.lngLat.lat, event.lngLat.lng);
        });
        map.on('load', () => {
          if (!map || controller.signal.aborted) return;
          addRouteLayers(map);
          addResultLayers(map);
          pins.current = createPlacePins(map, (target, lat, lon) => pickContext.current.onPick?.(target, lat, lon));
          map.on('click', 'checkpoints', event => {
            if (pickContext.current.target) return;
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
          map.on('mouseenter', 'checkpoints', () => { if (map) map.getCanvas().style.cursor = pickContext.current.target ? 'crosshair' : 'pointer'; });
          map.on('mouseleave', 'checkpoints', () => { if (map) map.getCanvas().style.cursor = pickContext.current.target ? 'crosshair' : ''; });
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
      pins.current?.remove();
      pins.current = null;
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
    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: fitPadding(map.getContainer().clientWidth), duration: 600 });
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
    map.getCanvas().style.cursor = pickContext.current.target ? 'crosshair' : '';
  }, [ready, result, interval]);

  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) applyRouteFocus(map, focusId);
  }, [ready, focusId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const markers = createTrucks(map, routes);
    trucks.current = markers;
    return () => {
      markers.remove();
      trucks.current = null;
    };
  }, [ready, routes]);

  useEffect(() => {
    if (!ready) return;
    const frame = requestAnimationFrame(() => {
      const timestamp = heatfield ? parseUtc(heatfield.start).getTime() + hour * 3_600_000 : null;
      trucks.current?.update(timestamp);
    });
    return () => cancelAnimationFrame(frame);
  }, [ready, routes, heatfield, hour]);

  useEffect(() => {
    pickContext.current = { target: pickTarget, onPick };
    const map = mapRef.current;
    if (map) map.getCanvas().style.cursor = pickTarget ? 'crosshair' : '';
    if (pickTarget) popupRef.current?.remove();
  }, [ready, pickTarget, onPick]);

  useEffect(() => {
    if (ready) pins.current?.update(places);
  }, [ready, places]);

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
    const particles = createWindParticles(heatfield.windField(), { debug: isDebug() });
    const detach = attachWindParticles(map, particles, heatfield.coordinates);
    wind.current = particles;
    return () => {
      detach();
      wind.current = null;
    };
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

  // Wind particles run on the Wind and Gust layers, moved by the sustained wind at the slider hour.
  useEffect(() => {
    if (!ready || !heatfield) return;
    const shown = Math.min(Math.max(0, hour), heatfield.hours - 1);
    wind.current?.configure({ hour: shown, windLayer: heatLayer === 'wind' || heatLayer === 'gust' });
  }, [ready, heatfield, heatLayer, hour]);

  return (
    <section className="map-pane" aria-label="Trip map">
      <div className="map-container" ref={container} />
      {pickTarget && (
        <div className="map-pick-hint" role="status">
          <span>Click the map to set the {pickTarget} · Esc to cancel</span>
          <button type="button" onClick={onCancelPick} aria-label="Cancel map picking">Cancel</button>
        </div>
      )}
      {message && <p className="map-message" role="status">{message}</p>}
      <div className="heat-hover" ref={tooltip} hidden />
      {children}
    </section>
  );
}
