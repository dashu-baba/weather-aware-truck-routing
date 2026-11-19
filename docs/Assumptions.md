## Assumptions and limits

What the planner assumes, and what it does not model. The values live in `backend/routing/config.py`; change a
value there and update this page.

### Trip and truck

| Assumption | Value | Notes |
|---|---|---|
| Truck weight | Tare 35,000 lb added to the cargo | The form asks for cargo weight. TomTom needs the gross weight, so `gross = load + 35,000 lb`. The tare is a typical empty tractor and 53 ft trailer. |
| Weight warning | Gross over 80,000 lb | The US federal limit. It adds a warning to the result and does not block the plan. |
| Cargo range | 0 to 60,000 lb | Enforced by the API. |
| Routes | Three | One main route and up to two alternatives. A route that shares more than 85% of its length with another counts as the same route. |
| Departure | One hour ago to seven days ahead | A time without an offset is read as UTC. Each departure minute is its own plan. |
| Trip length | At most 72 hours of forecast | Longer trips are refused with `422` (`JOB_WINDOW_HOURS`). |
| Region | US-first | Place search is limited to the US. Reverse geocoding and routing work anywhere, but the thresholds, tare weight and weight warning are US values, so the UI warns for a point outside the US. |

### Travel time and weather timing

- **Travel times are TomTom's truck estimates with historic speeds** (`traffic=false`, no live traffic for a future
  departure). The model has **no rest stops, driving-hour limits or fuel stops**, so the truck is assumed to drive
  without stopping. On a long trip the estimated arrival gets optimistic, and so does the forecast hour used for
  every later checkpoint.
- **Checkpoints** are placed every 10, 25 or 50 miles along each route. Each one gets the forecast for the hour the
  truck is expected to be there (its ETA), taken at the **nearest forecast hour** (:30 rounds up).
- **Weather is fetched per 0.1 degree cell** (about 7 miles), so checkpoints in the same cell share one forecast.
  The forecast model itself is about 11 km wide, so it cannot resolve a single mountain pass.
- A checkpoint with **no forecast** (for example beyond the forecast range) is scored Low and reported in
  `meta.warnings`.
- Wind uses the **sustained** speed (`wind_speed_10m`), not gusts. Gusts are shown in the popup and on the map.
  `WIND_METRIC=gust` or `max` changes this for the whole backend.

### Risk scoring

- The thresholds and load rules are in [Rules](./Rules.md). The ranges in the brief overlap at their edges, so the
  boundary policy is explicit: a value equal to the lower bound of a range belongs to the higher level (wind 25 is
  Moderate), except No Travel, which follows the brief's symbols (wind at least 55 is inclusive, rain above 1.00 and
  snow above 3.0 are exclusive).
- A checkpoint's risk covers the stretch **before** it (`segment_mi`), and the first checkpoint covers none. Miles per
  level and average risk are weighted by that distance.
- `AVG_RISK_TIE_EPS` (default 0, strict) sets how close two routes' average risk must be to count as a tie.

### Heatmap

- 48 hours of forecast, in a polygon 25 miles around the three routes (a convex hull), on a grid of at most 450
  cells. Each cell is one weather call, which keeps the quota use small.
- The browser draws the heatmap and the risk layer from the grid values; it classifies risk per pixel and never
  interpolates the integer risk levels.

### Not modelled

Ice, freezing rain, fog, temperature, road closures and chain laws. The risk comes only from wind, rain and snow
rates. Treat the result as a planning aid and not a substitute for current conditions and a dispatcher's judgement.

### Service limits

- **Open-Meteo free tier:** 600 locations a minute, 5,000 an hour and 10,000 a day, where every location counts as
  one call. A plan needs roughly 650 locations for an 800-mile trip and 1,400 for a cross-country one. The server
  paces itself and answers `503` instead of waiting an hour (see the README).
- **TomTom:** a new plan costs about 5 to 7 routing calls. Nothing tracks the daily limit yet.
- **This API:** 60 searches, 60 map-point lookups, 6 plans and 120 status polls a minute per client.
- **Retention:** a plan is kept for 24 hours and a weather download for 6 hours (forecasts are revised).
