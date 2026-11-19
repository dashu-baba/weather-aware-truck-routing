# Weather-Aware Truck Routing
 
**Weather-aware route planning for trucks.** 
Enter an origin, a destination, a departure time and a load weight. 
The app finds three truck routes, checks the forecast **at the moment the truck will reach each point**, 
scores the risk with load-aware rules, and recommends the safest route on an interactive weather map.

**Live app:** 

## Contents
 
1. [Features](./docs/Features.md)
2. [Rules](./docs/Rules.md)
3. [Assumptions and limits](./docs/Assumptions.md)
4. [Architecture](./docs/Architecture.md)
5. [Tech stack](./docs/TechStack.md)
6. [Running locally](#running-locally)
7. [Environment variables](#environment-variables)
8. [API reference](./docs/API_Reference.md)
9. [Testing](#testing)
10. [Project structure](#project-structure)
11. [Credits](#credits)

## Running locally
 
**You'll need:** Python 3.12+, Node.js 20.19+ (or 22.12+), and a free TomTom API key from
[developer.tomtom.com](https://developer.tomtom.com). Open-Meteo needs no key.

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then set TOMTOM_API_KEY (it already has DJANGO_DEBUG=1 for local use)
python manage.py migrate        # creates backend/db.sqlite3 (plan and weather-job records)
python manage.py runserver      # http://localhost:8000/api/health
```

### Frontend

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

Run it with the backend above. Vite proxies `/api/*` to `http://localhost:8000`, so no configuration is needed
locally. To use a backend on another host, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_URL`
to its origin without a trailing slash, and add the frontend's origin to the backend's `CORS_ALLOWED_ORIGINS`.
`npm run build` creates a production bundle in `frontend/dist`. See [`frontend/README.md`](./frontend/README.md)
for the structure and a manual checklist.

### Quick API check

```bash
curl "http://localhost:8000/api/health"
curl "http://localhost:8000/api/geocode?q=Dallas"
curl "http://localhost:8000/api/reverse?lat=32.7767&lon=-96.797"
```

To plan a trip, `POST /api/plan` with an origin, a destination, a departure and a load, then poll the `plan_id` it
returns. The [API reference](./docs/API_Reference.md) has the request and every field of the response.

## Environment variables

**Backend (`backend/.env`)**

| Variable | Required | Example | Purpose |
|---|---|---|---|
| `TOMTOM_API_KEY` | yes | `abc123…` | TomTom routing + geocoding (server-side only) |
| `DJANGO_DEBUG` | locally | `1` | Debug mode, off by default. Set `1` in your local `.env`; without it Django refuses to start unless `DJANGO_SECRET_KEY` is set. |
| `DJANGO_SECRET_KEY` | in production | `…` | Django's signing key. Required when `DJANGO_DEBUG` is off. Generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"`. |
| `DJANGO_ALLOWED_HOSTS` | in production | `truckroute.example.com,localhost` | Comma-separated hostnames Django will serve. Defaults to `localhost`, `127.0.0.1`, `[::1]`. |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. Defaults to `DEBUG` locally and `INFO` otherwise. |
| `NUM_PROXIES` | no | `1` | Trusted proxies in front of the app. Default `0`: clients are identified by their socket address, so a spoofed `X-Forwarded-For` can't dodge the throttle. Set `1` behind a single proxy such as Render. |
| `CORS_ALLOWED_ORIGINS` | no | `https://app.example.com` | Comma-separated browser origins allowed to call the API. Defaults to the Vite dev server (`http://localhost:5173`); an empty value allows no cross-origin access. |
| `DATABASE_PATH` | no | `/var/data/app.sqlite3` | SQLite file for plan and weather-job records. Defaults to `backend/db.sqlite3`. |
| `PLAN_DATA_DIR` | no | `/var/data/plans` | Folder for the JSON files the records point at (routes, weather, scored plans). Defaults to `<system temp>/weather-aware`. |
| `WEATHER_JOB_TTL_S` | no | `21600` | Seconds a weather download is kept for reuse. Default 6 hours, because forecasts are revised. |
| `PLAN_TTL_S` | no | `86400` | Seconds a finished plan is kept. Default 24 hours. |
| `JOB_STALE_S` | no | `300` | A running weather job that reports no progress for this long is treated as dead and requeued. |
| `JOB_WORKER` | no | `external` | `thread` (default): the web process runs the weather jobs itself, starting on the first plan request. `external`: run `python manage.py run_jobs` as a separate process instead. |
| `JOB_WINDOW_HOURS` | no | `72` | Hours of forecast each weather job fetches from the departure hour. Trips longer than this are refused with `422`. |
| `WIND_METRIC` | no | `gust` | Which wind speed the thresholds use: `sustained` (default), `gust` or `max` (the larger of the two). |
| `AVG_RISK_TIE_EPS` | no | `0.05` | How close two routes' average risk must be to count as a tie in the ranking. Default `0` (strict). |

**Frontend (`frontend/.env`)**

| Variable | Required | Example | Purpose |
|---|---|---|---|
| `VITE_API_URL` | no | `https://api.example.com` | Origin of the backend, without a trailing slash. Leave empty in development, where Vite proxies `/api`. It is added to every API path, including the heatmap URL. |

Logs go to stderr in the format `time LEVEL logger: message`. The TomTom API key is never written to the logs.

### Weather API limits

Open-Meteo's free tier allows 600 locations a minute, 5,000 an hour and 10,000 a day per IP address, and
**every location in a request counts as one call**. A plan needs roughly 650 locations for an 800-mile trip and
1,400 for a cross-country one, so the server paces itself:

- **Per minute:** it follows the `X-RateLimit-Remaining` and `X-RateLimit-Reset` headers on every response
  (the server's own count) and waits for the reset when a batch won't fit. Without usable headers it falls back
  to a local limit of 500 locations a minute.
- **Per hour and per day:** it keeps its own count and stops with a "weather service busy" error
  (HTTP 503) at 4,500 an hour or 9,000 a day, below the real limits, instead of sleeping for an hour.
  These counters live in memory, so they reset when the server restarts.
- **HTTP 429:** it waits for the reset time and retries.

The limits are in `backend/routing/config.py` (`OPEN_METEO_*`).

### Database and plan files

`POST /api/plan` returns the routes first and scores the weather in the background (see the
[API reference](./docs/API_Reference.md)), so the backend keeps a small SQLite database (WAL mode, so status
polls never wait for a writer):

- **`WeatherJob`**: one weather download per trip and departure hour. The forecast does not depend on the load,
  so every load on the same trip shares it (the key is origin, destination and the departure hour).
- **`PlanRequest`**: one plan for a trip, departure hour **and load**. It points at its job.
- Large payloads are JSON files under `PLAN_DATA_DIR`; rows only store the path.

Run `python manage.py migrate` after pulling, and `python manage.py cleanup_plans` to delete expired records
and their files (run it on a schedule, for example hourly). Expired records are also removed whenever a plan is
started.

### Weather job worker

A weather job fetches the forecast for every location a plan needs, in stages: the 25-mile checkpoints first
(enough to rank the routes), then the 50-mile and 10-mile checkpoints, then the heatmap cells. Jobs run one at
a time so they share one Open-Meteo budget, and each batch updates the job's progress (`done_locations` out
of `total_locations`).

```bash
python manage.py run_jobs          # a worker process: keeps running and picks up queued jobs
python manage.py run_jobs --once   # process the queue until it is empty, then exit
```

By default (`JOB_WORKER=thread`) you don't need to run this: the web process starts one worker thread the first
time a plan is requested. Run **one** web process (for example one Gunicorn worker) so a single worker holds the
Open-Meteo budget. For several web processes, set `JOB_WORKER=external` and run one `run_jobs` process.

- **Resuming:** forecasts already fetched are saved (every 50 locations and after each stage), so a failed or
  restarted job continues where it stopped. A running job with no progress for `JOB_STALE_S` seconds is requeued
  when a worker starts.
- **Sharing:** another plan for the same trip, with a different load, adds only the locations its routes need
  that the job does not hold yet.
- **Errors:** a failed job stores a short message such as "Weather service is busy. Try again in about 2
  minute(s)." It never contains a URL, so the API key can't leak.

## Testing

```bash
cd backend
python -m pytest -q             # offline tests, no network or API key needed
ruff check . && ruff format --check .   # lint and formatting (config in backend/ruff.toml)

cd ../frontend
npm test                        # Vitest, offline
npm run lint                    # ESLint, no warnings allowed
npm run build                   # strict TypeScript check and production bundle
```

Tests use fake HTTP sessions and fake clocks, so they never call TomTom or Open-Meteo. They cover cache
keys, the TomTom client's response and error parsing, the geocode and reverse-geocode endpoints (validation,
caching, 502 handling), request throttling, the Open-Meteo limiter (rate-limit headers, hourly and daily budgets, 429
handling), the planning pipeline (preparing routes once and scoring them for different loads), the plan and
weather-job records (keys, expiry cleanup, file safety), the job worker (staged fetching, progress, failures and
resuming, the queue and the worker thread), the plan endpoints (routes at once, progress polling, sharing the
weather between loads, errors), and logging,
including a check that the API key never appears in log output.

The backend suite has **332 tests**, up from 244 before the rain and rule coverage was added:

- `test_risk.py`: hazard boundaries, strict load cutoffs, hazard reasons and wind selection.
- `test_ranking.py`: ranking priority, ties, explanations and distance-weighted scores.
- `test_checkpoints.py`: spacing, segment totals, progress interpolation and ETAs.
- `test_openmeteo_rain.py`: total rain, missing values, provider requests and old-cache refetching.

The frontend tests cover the API client and its error messages, the plan reducer and the polling lifecycle
(timing, cancellation, retries and the heatmap fallback) with fake timers, the result components, route
interpolation and risk pieces, the focus styling and the time formatting.

## Project structure
 
```
backend/
  config/            Django settings, URLs and logging setup
  planner/           API views and URLs, caching helper, throttling, plan and weather-job records, job worker
  routing/           settings, TomTom and Open-Meteo clients, risk rules, ranking and the planning pipeline
  tests/             pytest suite (offline)
frontend/
  src/api/           API client and types
  src/hooks/         plan state machine (reducer, polling lifecycle, usePlan)
  src/components/    TripForm, PlaceInput, PlanStatus, Recommendation, IntervalToggle, RouteCards, MapView
  src/map/           basemap, route and checkpoint GeoJSON, MapLibre layers, popups, palette
  src/lib/           time and distance formatting, route ranking helpers
docs/                features, rules, assumptions, architecture, tech stack, API reference
```

## Credits
 
- Routing and geocoding © [TomTom](https://developer.tomtom.com)
- Weather data by [Open-Meteo.com](https://open-meteo.com) ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/))
- Basemap © [OpenFreeMap](https://openfreemap.org), map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
- Map rendering: [MapLibre GL JS](https://maplibre.org)