# Frontend — phases 1 and 2

```sh
npm install
npm run dev
```

Vite serves the app at http://localhost:5173 and proxies `/api/*` to
http://localhost:8000. For a separately hosted backend, copy `.env.example`
to `.env` and set `VITE_API_URL` to its origin without a trailing slash.

Phase 2 includes the trip form, debounced place search, and the basemap.
Submitting validates and displays the trip details locally. POST planning,
polling, progress, and route rendering will be connected in phase 3.
Map picking and draggable pins belong to phase 7.

## Review checks

- [x] `npm run build`: strict TypeScript and production bundling pass.
- [x] `npm run lint`: no errors or warnings.
- [x] `npm test`: API client and basemap loading/fallback tests pass.
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

No new runtime dependencies were added for phase 2. The production build reports
a bundle-size advisory for MapLibre; TypeScript compilation and bundling succeed.
