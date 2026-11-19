
## Architecture
 
```
Browser (React + MapLibre)             Django REST API                      Third-party services
──────────────────────────             ───────────────                      ────────────────────
Trip form ── GET  /api/geocode ──────► GeocodeView  (cache 1 day) ────────► TomTom Search API
Map click ── GET  /api/reverse ──────► ReverseGeocodeView (cache 1 day) ──► TomTom reverse geocoding
"Plan"    ── POST /api/plan ─────────► PlanView     (routes at once) ─────► TomTom Routing API (truck)
          ── GET  /api/plan/<id> ────► PlanStatusView (progress, result)
          ── GET  /api/plan/<id>/heatmap ► PlanHeatmapView (409 until ready)
                                         weather job worker ──────────────► Open-Meteo (paced by its rate limits)
Basemap tiles ───────────────────────────────────────────────────────────► OpenFreeMap (keyless, direct)
```
 
- **Backend for the frontend.** The React app only talks to Django. TomTom and Open-Meteo are called
  only by the server, so the TomTom key never leaves the backend, and the server controls caching and quotas.
- **The one exception is basemap tiles.** OpenFreeMap needs no key, and sending map tiles through Django
  would only slow the map down.
- **Light state:** Django's in-memory cache holds geocoding and reverse-geocoding results for a day. A small
  SQLite database (`backend/db.sqlite3`) holds plan and weather-job records for the background plan flow, with
  large JSON payloads in files under `PLAN_DATA_DIR`. Each plan and weather download is stored there, so a
  plan survives a restart and a repeated request is answered without calling TomTom again.
- **Rate limiting:** DRF throttles each client (60 searches, 60 map-point lookups, 6 plans and 120 status polls
  a minute) so a public deployment can't use up the API quotas.
- **Weather jobs** (`backend/planner/jobs.py`): a worker thread or `manage.py run_jobs` process takes queued
  jobs one at a time, fetches the forecast stage by stage (25-mile checkpoints, 50, 10, then the heatmap) and
  stores it in a per-job pool file, saved every 50 locations. It reports progress after every batch and a
  heartbeat that lets a restarted worker (or an idle one) requeue a dead job. A plan for another load adds only
  the locations that are missing.
- **The planner is three steps** (`backend/routing/pipeline.py`): `prepare` gets the routes and builds the
  checkpoints and heatmap grid, `fetch_weather` loads every forecast location in one prefetch, and
  `score_plan` turns weather into risk, ranking and heatmap for one load. Only the middle step is slow
  and uses the weather quota. Scoring the same prepared plan again with another load is instant and makes
  no network calls. `plan()` runs the three in order. The API runs them at different times: `prepare` while
  the request waits, `fetch_weather` in the worker, and `score_plan` when the job is done.
- **Keys.** A weather job is keyed by trip and departure **hour**, so every load and every departure minute in
  that hour shares one weather download. A plan is keyed by trip, departure **minute** and load, because the
  routes and ETAs depend on the exact minute.
- **Weather quota:** Open-Meteo counts every location as a call (600 a minute, 5,000 an hour, 10,000 a day on
  the free tier). The server follows the `X-RateLimit-*` response headers for the per-minute limit and keeps
  in-memory hourly and daily budgets below the real limits, returning 503 instead of waiting an hour.
- **Routes first, then the weather.** `POST /api/plan` returns the three routes in seconds (`202`), so the map
  can draw them at once. The browser then polls `GET /api/plan/<id>` for a progress percentage and, as each
  checkpoint interval arrives, a recommendation. The final result holds the checkpoints for all three
  intervals, the scores and the recommendation; the 48-hour heatmap is a separate request. After that,
  switching the interval, layer or hour **never calls the server**.

### Frontend

```
App ── usePlan (useReducer) ── runPlanLifecycle: POST ─► poll every poll_after_ms ─► GET heatmap
 │         state: idle · posting · weather · done · error (+ a soft heatmap warning)
 ├─ TripForm / PlaceInput    place search, departure, cargo weight
 ├─ PlanStatus               progress, stage label, early pick, error with Retry
 ├─ Recommendation, IntervalToggle, RouteCards     the result, for the selected spacing and focused route
 └─ MapView                  one MapLibre map: route lines, risk pieces, checkpoints, popups
```

- **One state machine.** `planReducer` is a pure function and `planLifecycle` is a plain async function that
  dispatches into it, so the flow (including cancelling the old poll on a new submit or on unmount) is tested without
  rendering anything. Polls use `setTimeout` with the server's `poll_after_ms` and never overlap.
- **The map is imperative.** `MapView` creates the map once and updates GeoJSON sources only when the routes, the
  result or the interval change. Focusing a route only changes paint and layout properties.
- **Every API path** goes through `apiUrl()`, which adds `VITE_API_URL` (empty in development, where Vite proxies
  `/api` to Django), including the `heatmap_url` the API returns as a relative path.
