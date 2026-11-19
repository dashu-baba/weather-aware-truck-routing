# Frontend — phases 1–4

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

Completed plans show the recommended route, ranked cards, checkpoint spacing,
and risk-coloured route pieces and checkpoints. Click a checkpoint for its local
ETA, weather, UTC forecast hour, risk and reasons. Click a card to focus its route;
click it again to return to the recommended route. Interval and focus changes
are computed locally with no requests.

The heatmap is fetched and stored; rendering it belongs to phase 5. Map picking
and draggable pins belong to phase 7.

## Planning lifecycle

- `hooks/usePlan.ts`: reducer state, the saved Retry body, and cancellation on new submit/unmount.
- `hooks/planReducer.ts`: state transitions; keeps the first routes stable across status polls.
- `hooks/planLifecycle.ts`: sequential `setTimeout` polls using each response's `poll_after_ms`;
  failed/404 handling; heatmap 409 retries every 2 seconds, at most ten retries after the initial fetch.
- `components/PlanStatus.tsx`: posting/progress/early pick, readable errors with Retry, and soft heatmap warnings.
- `map/geometry.ts`: full-route GeoJSON, binary-search interpolation, checkpoint stretches and point features ported from the POC.
- `map/layers.ts`: full-route/risk/checkpoint layers and focus-only paint/layout updates.
- `map/popup.ts`: checkpoint popups built with DOM text nodes for API strings.
- `components/IntervalToggle.tsx`, `Recommendation.tsx`, `RouteCards.tsx`: local interval selection, recommendation explanations and ranked route cards.
- `lib/routes.ts`, `lib/format.ts`: risk-mile distributions, ranking, local/UTC times and duration formatting.

A new submission aborts the old request and clears its timer. An unavailable
heatmap leaves the scored plan usable. Polls update progress without rebuilding
route data or moving the map; each new submission fits its first routes once.

## Review checks

- [x] `npm run build`: strict TypeScript and production bundling pass.
- [x] `npm run lint`: no errors or warnings.
- [x] `npm test`: 63 tests cover the API client, basemap, lifecycle, result components, interpolation, route pieces, checkpoint coordinates, risk-mile bars, local/UTC formatting, and focus styling.
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

## Phase 4 review checks

- [x] A real completed Dallas → Atlanta plan shows three cards in recommendation order,
  default 25-mile checkpoints and the route recommendation/reason.
- [x] 25-mile spacing: 105 route pieces and 108 checkpoints; 50-mile: 53 / 56;
  10-mile: 260 / 263 (including all three routes).
- [x] Interval changes update only route-risk and checkpoint data, without refitting the map.
- [x] Card focus updates paint/layout only; no GeoJSON source updates. Clicking the
  same card again returns focus to the recommendation.
- [x] Interval/focus changes trigger zero network requests in the browser.
- [x] Checkpoint click shows the route, mile, local ETA, wind/gust, rain/snow,
  UTC forecast hour and coloured risk; hover shows a pointer cursor.
- [x] Switching intervals closes the old popup and uses the new checkpoint indexes.
- [x] Missing forecast text and No Travel popup rendering work; API strings remain
  literal text, including strings containing HTML.
- [x] Component tests cover all-blocked/null recommendations, BEST/NO TRAVEL tags,
  weighted risk bars, absent scoring data, and zero-mile distributions.
- [x] Mobile results have no horizontal overflow; the map stays above the panel at 55vh.

A fresh weather job returned the backend's busy message during this review. The
result checks above used a previously completed real plan served by the backend,
without another weather download.

No new dependencies were added for phases 2–4. The production build reports
a bundle-size advisory for MapLibre; TypeScript compilation and bundling succeed.
