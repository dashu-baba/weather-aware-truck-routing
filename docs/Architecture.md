
## Architecture
 
```
Browser (React + MapLibre)            Django REST API                     Third-party services
──────────────────────────            ───────────────                     ────────────────────
Trip form ── GET  /api/geocode ─────► GeocodeView  (cache 1 day) ───────► TomTom Search API
"Plan"    ── POST /api/plan ────────► PlanView     (cache 10 min) ──────► TomTom Routing API (truck)
                                        routing pipeline ───────────────► Open-Meteo (throttled, cached)
Basemap tiles ──────────────────────────────────────────────────────────► OpenFreeMap (keyless, direct)
```
 
- **Backend for the frontend.** The React app only talks to Django. TomTom and Open-Meteo are called
  only by the server, so the TomTom key never leaves the backend, and the server controls caching and quotas.
- **The one exception is basemap tiles.** OpenFreeMap needs no key, and sending map tiles through Django
  would only slow the map down.
- **Light state:** Django's in-memory cache holds geocoding results and finished plans. A small SQLite
  database (`backend/db.sqlite3`) holds plan and weather-job records for the background plan flow, with
  large JSON payloads in files under `PLAN_DATA_DIR`. `/api/plan` does not use it yet.
- **Rate limiting:** DRF throttles each client (60 geocodes and 6 plans a minute) so a public deployment
  can't use up the API quotas.
- **Weather jobs** (`backend/planner/jobs.py`): a worker thread or `manage.py run_jobs` process takes queued
  jobs one at a time, fetches the forecast stage by stage (25-mile checkpoints, 50, 10, then the heatmap) and
  stores it in a per-job pool file. It reports progress after every batch and a heartbeat that lets a
  restarted worker requeue a dead job. A plan for another load adds only the locations that are missing.
- **The planner is three steps** (`backend/routing/pipeline.py`): `prepare` gets the routes and builds the
  checkpoints and heatmap grid, `fetch_weather` loads every forecast location in one prefetch, and
  `score_plan` turns weather into risk, ranking and heatmap for one load. Only the middle step is slow
  and uses the weather quota. Scoring the same prepared plan again with another load is instant and makes
  no network calls. `plan()` runs the three in order, so the API response is unchanged.
- **Weather quota:** Open-Meteo counts every location as a call (600 a minute, 5,000 an hour, 10,000 a day on
  the free tier). The server follows the `X-RateLimit-*` response headers for the per-minute limit and keeps
  in-memory hourly and daily budgets below the real limits, returning 503 instead of waiting an hour.
- **One request, one complete plan.** The response holds the routes, the checkpoints for all three
  intervals, the scores, the recommendation and the 48-hour heatmap. Switching the interval, layer or
  hour **never calls the server**.