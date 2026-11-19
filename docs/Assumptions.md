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
| Region | Worldwide | Search, reverse geocoding and routing are not limited to a country. The thresholds (mph, inches per hour), the tare weight and the 80,000 lb warning are US values and are applied to every trip. |

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
- **Rain** is Open-Meteo `rain + showers`: `rain` covers large-scale systems and `showers` adds convective
  thunderstorm rain, which can be the heaviest rain on a trip.
- Wind uses the **sustained** 10 m speed (`wind_speed_10m`). The brief's steps match sustained-wind scales.
  NWS gust thresholds are 15–18 mph higher: Wind Advisory uses sustained 31–39 mph or gusts 46–57 mph;
  High Wind Warning uses sustained ≥ 40 mph or gusts ≥ 58 mph. Applying the brief's table to gusts would rate
  ordinary breezy days High. Gusts are still shown in the popup and on the map.
  `WIND_METRIC=gust` or `max` changes this for the whole backend.
- Open-Meteo rain, showers and snowfall are totals for the hour **before** each timestamp, read as in/hr.
  Matching the nearest forecast hour means an ETA of 14:10 uses the 13:00–14:00 total. This is an accepted
  approximation of conditions at arrival.

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
- The API returns the grid values for each hour (risk, wind, gust, rain, snow and the wind components) as a
  separate request, and the result does not contain them.

### Not modelled

Ice, freezing rain, fog, temperature, road closures and chain laws. The risk comes only from wind, rain and snow
rates. Treat the result as a planning aid and not a substitute for current conditions and a dispatcher's judgement.

### Service limits

- **Open-Meteo free tier:** 600 locations a minute, 5,000 an hour and 10,000 a day, where every location counts as
  one call. A plan needs roughly 650 locations for an 800-mile trip and 1,400 for a cross-country one. The server
  paces itself and answers `503` instead of waiting an hour (see the README).
- **TomTom:** a new plan costs about 5 to 7 routing calls. The daily limit is not tracked.
- **This API:** 60 searches, 60 map-point lookups, 6 plans and 120 status polls a minute per client.
- **Retention:** a plan is kept for 24 hours and a weather download for 6 hours (forecasts are revised).
