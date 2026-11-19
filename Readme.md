# Weather-Aware Truck Routing
 
**Weather-aware route planning for trucks.** 
Enter an origin, a destination, a departure time and a load weight. 
The app finds three truck routes, checks the forecast **at the moment the truck will reach each point**, 
scores the risk with load-aware rules, and recommends the safest route on an interactive weather map.

**Live app:** 

## Contents
 
1. [Features](./docs/Features.md)
2. [Rules](./docs/Rules.md)
3. [Architecture](./docs/Architecture.md)
4. [Tech stack](./docs/TechStack.md)
5. [Running locally](#running-locally)
6. [Environment variables](#environment-variables)
7. [API reference](./docs/API_Reference.md)
8. [Testing](#testing)
9. [Project structure](#project-structure)
10. [Credits](#credits)

## Running locally
 
**You'll need:** Python 3.12+, Node.js 20+, and a free TomTom API key from
[developer.tomtom.com](https://developer.tomtom.com). Open-Meteo needs no key.

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then set TOMTOM_API_KEY
python manage.py migrate        # creates backend/db.sqlite3 (plan and weather-job records)
python manage.py runserver      # http://localhost:8000/api/health
```

### Quick API check

```bash
curl "http://localhost:8000/api/health"
curl "http://localhost:8000/api/geocode?q=Dallas"
```

## Environment variables

**Backend (`backend/.env`)**

| Variable | Required | Example | Purpose |
|---|---|---|---|
| `TOMTOM_API_KEY` | yes | `abc123…` | TomTom routing + geocoding (server-side only) |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. Defaults to `DEBUG` locally and `INFO` otherwise. |
| `NUM_PROXIES` | no | `1` | Trusted proxies in front of the app. Default `0`: clients are identified by their socket address, so a spoofed `X-Forwarded-For` can't dodge the throttle. Set `1` behind a single proxy such as Render. |
| `CORS_ALLOWED_ORIGINS` | no | `https://app.example.com` | Comma-separated browser origins allowed to call the API. Defaults to the Vite dev server (`http://localhost:5173`). |
| `DATABASE_PATH` | no | `/var/data/app.sqlite3` | SQLite file for plan and weather-job records. Defaults to `backend/db.sqlite3`. |
| `PLAN_DATA_DIR` | no | `/var/data/plans` | Folder for the JSON files the records point at (routes, weather, scored plans). Defaults to `<system temp>/weather-aware`. |
| `WEATHER_JOB_TTL_S` | no | `21600` | Seconds a weather download is kept for reuse. Default 6 hours, because forecasts are revised. |
| `PLAN_TTL_S` | no | `86400` | Seconds a finished plan is kept. Default 24 hours. |
| `JOB_STALE_S` | no | `300` | A running weather job that reports no progress for this long is treated as dead and requeued. |

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

The planner is being moved to a background flow (routes first, weather scored afterwards), so the backend now
has a small SQLite database (WAL mode, so status polls never wait for a writer):

- **`WeatherJob`**: one weather download per trip and departure hour. The forecast does not depend on the load,
  so every load on the same trip shares it (the key is origin, destination and the departure hour).
- **`PlanRequest`**: one plan for a trip, departure hour **and load**. It points at its job.
- Large payloads are JSON files under `PLAN_DATA_DIR`; rows only store the path.

Run `python manage.py migrate` after pulling, and `python manage.py cleanup_plans` to delete expired records
and their files (run it on a schedule, for example hourly). `/api/plan` does not use the database yet.

### Weather job worker

A weather job fetches the forecast for every location a plan needs, in stages: the 25-mile checkpoints first
(enough to rank the routes), then the 50-mile and 10-mile checkpoints, then the heatmap cells. Jobs run one at
a time so they share one Open-Meteo budget, and each batch updates the job's progress (`done_locations` out
of `total_locations`).

```bash
python manage.py run_jobs          # a worker process: keeps running and picks up queued jobs
python manage.py run_jobs --once   # process the queue until it is empty, then exit
```

- **Resuming:** forecasts already fetched are saved (every 200 locations and after each stage), so a failed or
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
ruff check .                    # lint (config in backend/ruff.toml)
```

Tests use fake HTTP sessions and fake clocks, so they never call TomTom or Open-Meteo. They cover cache
keys, the TomTom client's response and error parsing, the geocode endpoint (validation, caching, 502
handling), request throttling, the Open-Meteo limiter (rate-limit headers, hourly and daily budgets, 429
handling), the planning pipeline (preparing routes once and scoring them for different loads), the plan and
weather-job records (keys, expiry cleanup, file safety), the job worker (staged fetching, progress, failures and
resuming, the queue and the worker thread), and logging,
including a check that the API key never appears in log output.

## Project structure
 
```
backend/
  config/            Django settings, URLs and logging setup
  planner/           API views and URLs, caching helper, throttling, plan and weather-job records, job worker
  routing/           settings, TomTom and Open-Meteo clients, risk rules, ranking and the planning pipeline
  tests/             pytest suite (offline)
frontend/
  src/api/           API client and types
  src/components/    TripForm, PlanMap
  src/map/           MapLibre layers, heatmap renderer, wind particles
docs/                requirements and assumptions, architecture, API notes, algorithms
archive/poc/         original proof of concept (CLI + static map)
```

## Credits
 
- Routing and geocoding © [TomTom](https://developer.tomtom.com)
- Weather data by [Open-Meteo.com](https://open-meteo.com) ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/))
- Basemap © [OpenFreeMap](https://openfreemap.org), map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
- Map rendering: [MapLibre GL JS](https://maplibre.org)