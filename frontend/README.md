# Frontend — phases 1–3

```sh
npm install
npm run dev
```

Vite serves the app at http://localhost:5173 and proxies `/api/*` to
http://localhost:8000. For a separately hosted backend, copy `.env.example`
to `.env` and set `VITE_API_URL` to its origin without a trailing slash.

The trip form now submits real plans. The first POST response draws the three
routes while weather scoring continues. The panel shows progress, stage labels,
and the early recommendation for 25-mile checkpoints. Retry re-posts the original
request, even if form values have since changed.

Phase 3 fetches and stores the completed result and heatmap. Checkpoints, cards,
interval selection and route focus belong to phase 4; heatmap rendering belongs
to phase 5. Map picking and draggable pins belong to phase 7.

## Planning lifecycle

- `hooks/usePlan.ts`: reducer state, the saved Retry body, and cancellation on new submit/unmount.
- `hooks/planReducer.ts`: state transitions; keeps the first routes stable across status polls.
- `hooks/planLifecycle.ts`: sequential `setTimeout` polls using each response's `poll_after_ms`;
  failed/404 handling; heatmap 409 retries every 2 seconds, at most ten retries after the initial fetch.
- `components/PlanStatus.tsx`: posting/progress/early pick, readable errors with Retry, and soft heatmap warnings.
- `map/geometry.ts` and `map/layers.ts`: full-route GeoJSON and MapLibre styling ported from the POC.

A new submission aborts the old request and clears its timer. An unavailable
heatmap leaves the scored plan usable. Polls update progress without rebuilding
route data or moving the map; each new submission fits its first routes once.

## Review checks

- [x] `npm run build`: strict TypeScript and production bundling pass.
- [x] `npm run lint`: no errors or warnings.
- [x] `npm test`: 39 tests cover API errors, basemap fallback, reducer transitions, polling/cancellation, status rendering, and route coordinates.
- [x] Map appears before a trip, centered on the US, with one map canvas in StrictMode.
- [x] MapLibre worker loads through Vite; the basemap tiles and labels render.
- [x] Real Dallas/Atlanta place searches return through `/api/geocode`.
- [x] Search requires 3 characters and waits 300 ms; query changes abort the previous search.
- [x] Arrow keys select suggestions, Enter confirms, and Escape dismisses.
- [x] Clear removes a selected place; swap exchanges origin and destination.
- [x] Submit requires two selected places. Departure defaults to the next full local hour.
- [x] Cargo defaults to 42,000 lb, with 0–60,000 bounds and step 500.
- [x] At mobile width the map is above the panel, at 55vh, without horizontal overflow.
- [x] Basemap failure falls back to a blank background.
- [x] Data requests use only `/api/*` and `tiles.openfreemap.org` (application scripts and the map worker are served locally).

## Phase 3 review checks

- [x] Real Dallas → Atlanta plan: POST `202 weather`, three routes visible in about 6.9 seconds.
- [x] Real progress: 0% → 40% → 87% → 100%; weather responses include the early pick for Route A.
- [x] GET reaches `done`, then the separate heatmap GET succeeds.
- [x] Cached POST `200 done` skips status polling and fetches the heatmap.
- [x] Map fits once across the weather polls; only one map canvas is mounted.
- [x] Simulated 502 displays the API detail and Retry, preserving form values.
- [x] Editing cargo after failure does not change the Retry POST body.
- [x] Browser hook check: a new submit aborts the previous session; unmount aborts the active session.
- [x] Fake-timer tests: failed/404 status, changing poll delays, no overlapping polls,
  stale responses, timer cleanup, and heatmap retry exhaustion with a soft warning.
- [x] Browser console has no errors; data requests stay within `/api/*` and `tiles.openfreemap.org`.

No new dependencies were added for phases 2 or 3. The production build reports
a bundle-size advisory for MapLibre; TypeScript compilation and bundling succeed.
