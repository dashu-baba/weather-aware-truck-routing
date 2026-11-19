## API reference

### `GET /api/health`
`200 {"status": "ok"}`. Used by Render's health check.

### `GET /api/geocode?q=<text>&typeahead=true`
Place search for the trip form. `q` must be at least 3 characters; results are US-only, limited to 5,
and cached for 1 day. `typeahead` is optional (`true` for autocomplete) and is part of the cache key.

```json
[{ "label": "Dallas, TX", "lat": 32.7767, "lon": -96.797, "type": "Geography" }]
```

Limited to 60 requests a minute per client.

### Errors

Errors use `{"detail": "..."}`:

| Status | Meaning |
|---|---|
| `400` | Invalid input (for example, `q` is shorter than 3 characters) |
| `429` | Too many requests (throttled) |
| `502` | TomTom returned an error or could not be reached |
