## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, Django 5.2 LTS, Django REST Framework 3.17, django-cors-headers, Gunicorn |
| Storage | SQLite through the Django ORM (plan and weather-job records) plus JSON files for large payloads |
| Frontend | React 19, TypeScript (strict), Vite 8, MapLibre GL JS 6 |
| Frontend state | `useReducer` and a `usePlan` hook (the plan flow is a small state machine, so no data-fetching library) |
| Routing + geocoding | TomTom Routing API v1 (`travelMode=truck`), TomTom Search API v2 (search and reverse geocoding) |
| Weather | Open-Meteo hourly forecast API |
| Basemap | OpenFreeMap (OpenStreetMap data) |
| Deployment | Docker Compose (nginx and Gunicorn containers), Terraform, GitHub Actions, Amazon Lightsail, Cloudflare |
| Tests and checks | pytest and ruff (backend); Vitest, ESLint and `tsc` (frontend) |

The frontend needs Node.js 20.19+ or 22.12+ (a Vite 8 requirement).
