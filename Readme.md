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

## Testing

```bash
cd backend
python -m pytest -q             # offline tests, no network or API key needed
ruff check .                    # lint (config in backend/ruff.toml)
```

Tests use fake HTTP sessions and fake clocks, so they never call TomTom or Open-Meteo. They cover cache
keys, the TomTom client's response and error parsing, the geocode endpoint (validation, caching, 502
handling), request throttling, the Open-Meteo limiter (rate-limit headers, hourly and daily budgets, 429
handling), the planning pipeline (preparing routes once and scoring them for different loads), and logging,
including a check that the API key never appears in log output.

## Project structure
 
```
backend/
  config/            Django settings, URLs and logging setup
  planner/           API views and URLs, caching helper, throttling
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