# Frontend

React 19 + TypeScript, built with Vite, with MapLibre GL for the map. It talks only to the Django API (`/api/*`), so
no third-party key ever reaches the browser. The project overview, the rules and the assumptions are in the
[root README](../Readme.md) and [`docs/`](../docs).

## Run

```sh
npm install
npm run dev        # http://localhost:5173, proxies /api/* to http://localhost:8000
```

For a backend on another origin, copy `.env.example` to `.env` and set `VITE_API_URL` to that origin, with no
trailing slash. In production the app and the API share one domain, so `VITE_API_URL` stays empty.

| Command | What it does |
|---|---|
| `npm run build` | Strict TypeScript check and production bundle |
| `npm run lint` | ESLint, no warnings allowed |
| `npm test` | Vitest, 183 tests, no browser or network needed |

Add `?debug=1` to the address to log heatmap frame and particle timings to the console.

## How the page works

- **Planning.** `POST /api/plan` returns the three routes at once, and they are drawn straight away. The page then
  polls `GET /api/plan/<id>` at the interval the server asks for, shows progress, and fetches the heatmap once the
  plan is done. A new plan cancels the old requests. Errors show the API's message with a Retry button that
  re-sends the original request.
- **Results.** The ranked route cards, the recommendation with the rule that decided it, and the 10/25/50-mile
  checkpoint spacing are all worked out from the plan already in memory: changing spacing or focusing a route sends
  no request.
- **Checkpoint popups.** Each one shows the route and mile, the local ETA, wind and gust, rain and snow, the UTC
  forecast hour, the risk level and the reasons. API strings are inserted as text, never as HTML.
- **Corridor weather map.** The heatmap grid is drawn in Web Mercator on a canvas, clipped to the corridor around the
  three routes, with bilinear interpolation. The Risk layer classifies each pixel from the interpolated weather with
  the same rules and load as the checkpoints (`lib/risk.ts` mirrors `backend/routing/risk.py`). The last 60 frames
  are cached, and the next and previous hours are drawn while the browser is idle, so moving the 0–47 hour slider is
  instant and makes no request.
- **Layer scales.** Wind uses the brief's thresholds. Gust uses a scale 15 mph higher, and light rain and snow
  (below Moderate) show in blue that deepens with the amount.
- **Wind particles** (Wind and Gust layers) move with the sustained wind at the slider hour, at the same on-screen
  speed at every zoom. They pause in a hidden tab and stay still when reduced motion is requested.
- **Trucks** move along each route with the slider hour, from each route's own departure; Play steps one hour every
  600 ms.
- **Choosing places.** Places can be searched (at least 3 characters, debounced) or picked on the map with the pin
  button beside each field. Pins can be dragged. Picks are named through `/api/reverse`, and an outside-US or
  unknown point shows a soft warning.

## Layout

| Path | Contents |
|---|---|
| `src/api/` | Typed API client and response types |
| `src/hooks/` | Plan lifecycle (reducer, polling), heatmap loading, playback, place picking |
| `src/components/` | Form, status and loader, recommendation, route cards, spacing toggle, time bar, legend, map |
| `src/map/` | MapLibre layers, route and checkpoint GeoJSON, heatmap renderer, wind particles, trucks, pins, popups, palette |
| `src/lib/` | Risk rules for the browser, route maths, formatting |
| `nginx/` | Production nginx config, baked into the `web` Docker image (see [`docs/Deployment.md`](../docs/Deployment.md)) |
