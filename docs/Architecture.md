
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
- **Stateless:** there's no database. Django's in-memory cache holds geocoding results, weather series
  and finished plans.
- **Rate limiting:** DRF throttles each client (60 geocodes and 6 plans a minute) so a public deployment
  can't use up the API quotas.
- **Weather quota:** Open-Meteo counts every location as a call (600 a minute, 5,000 an hour, 10,000 a day on
  the free tier). The server follows the `X-RateLimit-*` response headers for the per-minute limit and keeps
  in-memory hourly and daily budgets below the real limits, returning 503 instead of waiting an hour.
- **One request, one complete plan.** The response holds the routes, the checkpoints for all three
  intervals, the scores, the recommendation and the 48-hour heatmap. Switching the interval, layer or
  hour **never calls the server**.