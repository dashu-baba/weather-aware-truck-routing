# Frontend — phases 1–7

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

When the heatmap arrives it is drawn under the routes, inside a dashed outline of
the corridor. A time bar below the map has a 0–47 hour slider (hour 0 is the
heatmap's start, shown in local time with the UTC time beside it) and a layer
toggle: Risk, Wind, Gust, Rain and Snow. The legend follows the layer, and
hovering over the corridor shows the value under the cursor, for example
`Gust 41 mph · High · Fri 10:00 PM`. Moving the slider or changing the layer
only redraws the image: it makes no request and rebuilds no GeoJSON. Add
`?debug=1` to the address to log frame times to the console and to expose the
renderer as `window.__heatfield`.

Three route-coloured truck markers move with the forecast hour, using each route's
own departure and per-vertex elapsed times. Before departure they stay at the
origin; on arrival they park at the destination at 50% opacity, with an `arrived`
title. Play advances one forecast hour every 600 ms and loops after hour 47.
Pause holds the current hour. Dragging or using the slider's adjustment keys
pauses playback; rapid inputs are coalesced into one animation frame. A new
heatmap resets playback to hour 0, paused. Layer, interval and focus changes
leave playback running.

Use the 📍 button beside either place input to pick its location on the map.
The crosshair and hint show which endpoint is being set; Escape, Cancel, or the
same picker button cancels. A coordinate label appears immediately, then the
address replaces it when `/api/reverse` returns. A/B pins are draggable and use
the same lookup flow. Search selection moves the corresponding pin; clearing
removes it and swap exchanges both locations.

Outside-US or unknown reverse results show a soft warning, but planning stays
available. If naming fails, the coordinate label stays usable. Location edits
never replan automatically: select Re-plan explicitly to update an existing trip.

## Heatmap

- `lib/risk.ts`: a TypeScript copy of `backend/routing/risk.py` (thresholds, load rules and the wind metric).
  Risk pixels are classified from the interpolated weather and never by interpolating the integer levels.
- `map/heatfield.ts`: the renderer. It rasterises the grid in Web Mercator so it lines up with the basemap,
  interpolates bilinearly (row 0 is the south and cells without a forecast are skipped), clips to the corridor
  polygon, keeps the last 60 frames and pre-renders the next and previous hour when the browser is idle.
- `map/heatLayers.ts`: adds the image and the outline under the route layers, and swaps a frame into one canvas.
- `map/hover.ts`: the readout beside the cursor, one update per animation frame, kept inside the map.
- `components/TimeBar.tsx`, `components/Legend.tsx`: the slider, label, layer toggle and legend.
- `hooks/useHeatfield.ts`: builds the renderer once the heatmap has loaded. A heatmap that cannot be drawn
  becomes a message in the time bar, and the scored plan stays usable.

## Trucks and playback

- `map/trucks.ts`: HTML marker creation, time interpolation via `pointAtTime`,
  departure/arrival labels, arrival opacity and marker cleanup.
- `hooks/playbackReducer.ts`: play/pause, bounded seeks, hourly ticks and looping.
- `hooks/usePlayback.ts`: the 600 ms timer, animation-frame slider updates and
  cleanup on timeline replacement/unmount.
- `components/MapView.tsx`: creates markers only when the routes arrive or change;
  an hour change moves the existing markers without changing GeoJSON sources.
- `components/TimeBar.tsx`: accessible Play/Pause and slider pointer/keyboard pause.

## Location picking

- `hooks/useTripPlaces.ts`: shared form/map locations, picker target, Escape and swap.
- `hooks/placeResolver.ts`: immediate coordinate labels, per-target request IDs and
  AbortControllers, reverse naming and soft country/unknown-point warnings.
- `hooks/tripPlacesReducer.ts`: location state and swaps that carry warning metadata.
- `lib/places.ts`: location types and wrapped-longitude coordinate labels.
- `map/places.ts`: A/B pin creation, position/label updates, drag-end callbacks and cleanup.

New picks, typing, clear, search selection, swap and unmount invalidate obsolete
lookups. Origin and destination resolve independently. A pending reverse reply
cannot overwrite a newer choice or move a point to a snapped address coordinate.
Picking takes priority over checkpoint popups, and the legend is temporarily
hidden while picking so the hint remains readable on smaller screens.

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
- [x] `npm test`: 162 tests cover the API client, basemap, lifecycle, result components, interpolation, route pieces, checkpoint coordinates, risk-mile bars, local/UTC formatting, focus styling, the risk rules, the heatmap renderer and its controls.
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

## Phase 5 review checks

Run in headless Chrome against a completed real Dallas → Atlanta plan (read-only; Open-Meteo's daily limit was
used up, so a new weather download was not possible that day).

- [x] The corridor outline and the weather image appear under the routes, and the Gust layer at hour 14 follows
  the Gulf coast (Mercator alignment).
- [x] The slider runs 0–47; the label reads `+0h · Fri, Nov 20, 12:00 AM (18:00 UTC)` and changes with the hour.
- [x] The layer toggle switches Risk, Wind, Gust, Rain and Snow, and the legend title and labels follow it.
- [x] Hover shows `Risk · Low · Fri 12:00 AM` inside the corridor and nothing outside it.
- [x] Dragging the slider 0 → 47 → 0, switching all layers and moving the cursor made **0 requests**
  (apart from basemap tiles).
- [x] Frame times with `?debug=1` (software GL, small grid of 304 × 144 px): cold render median 2.6 ms, 95th
  percentile 5.0 ms, maximum 6.6 ms; cached frames at most 0.1 ms; a full image swap (render and upload) median
  0.2 ms, maximum 7 ms. These are well under the 30 ms and 5 ms targets for a grid this size; a 1,000-mile plan
  has a larger grid and was not timed.
- [x] No console errors, and no horizontal overflow at 390 px. On a phone the legend and time bar cover part
  of the map.
- [x] Unit tests: risk boundaries and load rules (copied from the proof of concept), bilinear sampling with
  row 0 in the south, Mercator row alignment, the corridor clip, the 60-frame cache, idle pre-rendering, the
  layer glue, the tooltip placement, the legend and the time bar.

## Phase 6 review checks

Browser checks used a previously completed real Dallas → Atlanta plan read from
`GET /api/plan/<id>` and its heatmap. The browser test supplied that cached response
to the form's POST handler, so it did not start another weather job.

- [x] Three labelled route-coloured markers appear; at hour 7 their positions match
  `pointAtTime` using forecast start minus each route's own departure.
- [x] At hour 47 all trucks are at their destinations, labelled `arrived`, at 50% opacity;
  MapLibre's opacity API preserves the fade after panning.
- [x] Play advances hourly (observed updates at 634 ms and 1,254 ms); Pause holds the hour.
- [x] Playback loops 47 → 0 and pauses on slider pointer-down.
- [x] The same three marker elements survive seeks and playback.
- [x] Playback and slider changes make zero requests and zero GeoJSON source updates.
- [x] StrictMode hook probe: only one timer is active, rapid seeks coalesce to the
  last hour, replacement resets the clock, and unmount clears timers/animation frames.
- [x] Unit tests cover before/during/after departure, departure minutes and UTC offsets,
  arrival fading, play/pause, looping, seek bounds, marker reuse/removal and disabled controls.
- [x] The mobile time bar fits without horizontal overflow; no browser console errors.

## Phase 7 review checks

- [x] Picking works before a plan exists. The origin picker shows the crosshair/hint;
  Escape cancels without making a request.
- [x] A Dallas pick immediately shows `32.7767, -96.7970` and an A pin; the real reverse
  response replaces the label with `1400 Young Street, Dallas, TX 75201`.
- [x] Both pins are draggable. A real browser drag moved A and sent the new coordinates
  to `/api/reverse`; a search selection then moved it to Dallas's search coordinates.
- [x] Clearing removes its pin and disables submit when an endpoint is missing.
- [x] Swap moves both locations/pins and preserves warning metadata.
- [x] A real Toronto lookup shows the outside-US warning. An open-water lookup at
  0,0 keeps the coordinate label and shows the unknown-point warning. Submit remains enabled.
- [x] Simulated reverse 502 keeps the coordinate label and pin, without blocking planning.
- [x] After loading a completed real plan, editing a location sends zero additional
  plan POSTs and causes zero route/risk/checkpoint source updates. The button remains Re-plan.
- [x] Picking over a checkpoint sets the new point without opening its popup.
- [x] At mobile width the hint fits, the legend hides while picking, and there is no horizontal overflow.
- [x] Unit tests cover stale/out-of-order replies, independent endpoint requests,
  search/clear cancellation, swap/unmount cancellation, warning states, wrapped longitudes,
  pin reuse/movement and cleanup. No browser console errors.

The completed-plan check used a real cached GET response supplied to the test's
POST handler; it did not start another weather job. Reverse-geocode checks used
the real backend except for the explicitly simulated 502.

No new dependencies were added for phases 2–7. The production build reports
a bundle-size advisory for MapLibre; TypeScript compilation and bundling succeed.
