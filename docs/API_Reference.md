## API reference

### `GET /api/health`
`200 {"status": "ok"}`. Used by Render's health check.

### `GET /api/geocode?q=<text>&typeahead=true`
Place search for the trip form. `q` must be at least 3 characters; results are worldwide, limited to 5,
and cached for 1 day. `typeahead` is optional (`true` for autocomplete) and is part of the cache key.

```json
[{ "label": "Dallas, TX", "lat": 32.7767, "lon": -96.797, "type": "Geography" }]
```

Limited to 60 requests a minute per client.

### `GET /api/reverse?lat=<n>&lon=<n>`
Names a point picked on the map, so the trip form can show "1400 Young Street, Dallas, TX" instead of coordinates.
`lat` is -90 to 90 and `lon` is -180 to 180. It works anywhere in the world, not only in the US. Results are cached
for 1 day per point (rounded to about 11 m).

```json
{ "label": "1400 Young Street, Dallas, TX 75201", "lat": 32.7767, "lon": -96.797, "country": "US", "found": true }
```

`lat` and `lon` echo the point you sent, not a snapped one. When TomTom knows no address there (open water,
wilderness), the answer is still `200`, with `"found": false`, `"country": null` and the coordinates as the label
(`"0.0000, 0.0000"`), so the form can always fill itself in. Missing, non-numeric or out-of-range values give `400`; a
TomTom failure gives `502`. Limited to 60 requests a minute per client, separately from `/api/geocode`.

### `POST /api/plan`

Starts a plan. The three truck routes come back within seconds so the map can draw them. The weather is
fetched and scored in the background; poll `GET /api/plan/<plan_id>` for progress and the result.

```json
{
  "origin":      { "label": "Dallas, TX",  "lat": 32.7767, "lon": -96.797 },
  "destination": { "label": "Atlanta, GA", "lat": 33.749,  "lon": -84.388 },
  "departure": "2026-11-20T08:00:00-06:00",
  "load_lb": 30000
}
```

- `lat` is -90 to 90 and `lon` is -180 to 180. Origin and destination must differ.
- `departure` is an ISO 8601 time, from one hour ago to seven days ahead. A time without an offset is read as UTC.
  Each departure minute is its own plan, with its own routes and ETAs (seconds are ignored). The weather download is
  shared by the whole departure **hour**, so a different minute in the same hour costs one routing call and no new weather.
- `load_lb` is the cargo weight, 0 to 60,000 lb. The truck's own weight is added before it goes to TomTom.
- Limited to 6 requests a minute per client. Sending the same request again (same trip, departure minute and load) returns the same `plan_id`.

Returns `202 Accepted` while the weather is still being fetched, or `200 OK` when the plan is already complete
(the same plan again, or another load on a trip whose weather is already in). Both use the body below.

### `GET /api/plan/<plan_id>`

The same body as the POST, always `200`. Poll it every `poll_after_ms` until `status` is not `weather`.
Limited to 120 requests a minute per client. A plan is kept for 24 hours.

```json
{
  "plan_id": "8f3c1d2e-…",
  "status": "weather",
  "routes": [
    {
      "id": "A", "label": "Route A", "source": "tomtom",
      "summary": { "distance_mi": 786.1, "duration_s": 49210, "departure": "…", "arrival": "…" },
      "geometry": [[-96.797, 32.7767], "…"],
      "times": [0, 12, "…"]
    }
  ],
  "progress": { "stage": "checkpoints_25", "done": 212, "total": 647, "percent": 33, "queued": false },
  "partial": { "intervals": { "25": { "recommendation": { "best": "A", "order": ["A", "B", "C"], "reason": "…", "all_blocked": false },
                                      "scores": { "A": { "avg_risk": 1.2, "…": "…" } } } } },
  "result": null,
  "heatmap_url": null,
  "error": null,
  "poll_after_ms": 2000
}
```

| Field | Meaning |
|---|---|
| `status` | `weather` (still fetching), `done`, or `failed` |
| `routes` | The routes with map `geometry` (`[lon, lat]`) and `times` (seconds from departure for each point). Always present. |
| `progress` | `done` of `total` weather locations. `stage` is `routes`, `checkpoints_25`, `checkpoints_50`, `checkpoints_10`, `heatmap` or `done`. `queued` is true while no worker has started the job. |
| `partial` | Recommendations for each checkpoint interval (10, 25 and 50 miles) whose weather has arrived, so the best route can be shown early. `null` until the first interval is ready. |
| `result` | The scored plan once `status` is `done`: `meta`, `origin`, `destination`, `routes` (with `by_interval` checkpoints and scores) and `recommendation`. **It does not contain the heatmap.** |
| `heatmap_url` | Where to fetch the heatmap once `status` is `done`. |
| `error` | A short message when `status` is `failed`. Send the same `POST` again to retry; it continues where it stopped. |
| `poll_after_ms` | How long to wait before polling again. `null` when polling is over. |

Plans for the same trip and departure hour but a different load share one weather download, so the second
one is scored almost at once. A plan whose forecast has expired (about 6 hours) reports `failed`; post it again.

### `GET /api/plan/<plan_id>/heatmap`

The 48-hour heatmap for a finished plan, kept apart because it is large and affects no ranking. Limited with the
status endpoint. Returns `409` until the weather is in.

```json
{
  "mode": "hull", "start": "2026-11-20T08:00:00Z", "hours": 48,
  "polygon": [[-97.3, 32.7], "…"],
  "grid": { "lat0": 31.2, "lon0": -98.0, "step": 0.4, "nrows": 12, "ncols": 20 },
  "vars": { "risk": [[0, 1, null, "…"]], "wind": ["…"], "gust": ["…"], "rain": ["…"], "snow": ["…"], "u": ["…"], "v": ["…"] }
}
```

Each layer in `vars` is indexed `[hour][cell]`, with `null` for cells outside the corridor or without a forecast.

### Errors

Errors use `{"detail": "..."}`:

| Status | Meaning |
|---|---|
| `400` | Invalid input (for example, `q` is shorter than 3 characters, or a bad plan field) |
| `404` | The plan does not exist or has expired. Post it again. |
| `409` | The heatmap is not ready yet |
| `422` | No truck route between the points, or the trip is longer than the forecast window (72 hours) |
| `429` | Too many requests (throttled) |
| `502` | TomTom returned an error or could not be reached |
| `504` | TomTom timed out |
