"""End-to-end planner: routes -> checkpoints -> weather -> risk -> ranking -> heatmap.

The work is split in three so the slow part can be shared between loads and run in the background:

  prepare()        routes, per-vertex times, checkpoints and the heatmap grid. No weather, no scoring.
  fetch_weather()  one prefetch for every location the plan needs. This is the slow, quota-bound part.
  score_plan()     weather -> risk -> ranking -> heatmap for ONE load. Pure in-memory work, so scoring
                   the same PreparedPlan again with another load is cheap and never touches the network.

plan() runs the three in order. It never calls an API directly - it receives a `route_source` and a
`WeatherStore`, so tests can swap in fakes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from math import cos, radians, sin
from typing import Callable

from . import config
from .checkpoints import build_checkpoints, times_per_point
from .corridor import corridor_grid, corridor_hull, hull_grid
from .geo import LatLon, simplify_indices, to_lonlat
from .openmeteo import WeatherStore
from .ranking import explain, rank, score_route
from .risk import LEVELS, classify
from .tomtom import ParsedRoute, gross_weight_kg

logger = logging.getLogger(__name__)

RouteSource = Callable[[LatLon, LatLon, str, float], tuple[list[ParsedRoute], list[str]]]


@dataclass
class PreparedRoute:
    id: str
    route: ParsedRoute
    times: list[float]
    checkpoints: dict[int, list[dict]]  # interval (miles) -> checkpoints with no weather yet; never mutated


@dataclass
class PreparedPlan:
    """Everything that does not depend on the load or on the forecast values."""

    origin: dict
    destination: dict
    departure: datetime  # UTC
    depart_iso: str
    intervals: tuple[int, ...]
    source_label: str
    routes: list[PreparedRoute]
    route_warnings: list[str]
    cells: list[LatLon]  # heatmap locations to fetch
    start: datetime  # forecast window: the hour of departure ...
    end: datetime  # ... until an hour after the last arrival (at least HEATMAP_HOURS)
    polygon: list[LatLon] | None = None  # "hull" mode
    grid: dict | None = None  # "hull" mode
    step: float | None = None  # "band" mode

    def checkpoint_points(self, intervals: tuple[int, ...] | None = None) -> list[LatLon]:
        """Locations of the checkpoints of the given intervals (all by default), across every route."""
        wanted = self.intervals if intervals is None else intervals
        return [(c["lat"], c["lon"]) for pr in self.routes for iv in wanted for c in pr.checkpoints[iv]]

    def restricted(self, intervals: tuple[int, ...]) -> PreparedPlan:
        """The same plan limited to some checkpoint intervals, to score only what is already fetched."""
        routes = [replace(pr, checkpoints={iv: pr.checkpoints[iv] for iv in intervals}) for pr in self.routes]
        return replace(self, intervals=intervals, routes=routes)


def _round_weather(w: dict | None) -> dict | None:
    if w is None:
        return None
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in w.items()}


def _round(value: float | None, ndigits: int) -> float | None:
    return None if value is None else round(value, ndigits)


def wind_components(
    speed_mph: float | None, direction_deg: float | None
) -> tuple[float | None, float | None]:
    """Meteorological FROM bearing -> eastward u, northward v (mph)."""
    if speed_mph is None or direction_deg is None:
        return None, None
    direction = radians(direction_deg)
    return round(-speed_mph * sin(direction), 1), round(-speed_mph * cos(direction), 1)


def prepare(
    origin: dict,
    destination: dict,
    departure: datetime,
    load_lb: float,
    route_source: RouteSource,
    intervals: tuple[int, ...] = config.INTERVALS_MI,
    source_label: str = "live",
) -> PreparedPlan:
    """Get the routes (load_lb only matters to the route source: TomTom takes the truck weight)."""
    if departure.tzinfo is None:
        raise ValueError("departure must be timezone-aware (send ISO 8601 with an offset)")
    departure = departure.astimezone(timezone.utc)
    depart_iso = departure.isoformat().replace("+00:00", "Z")

    # 1. Routes
    o, d = (origin["lat"], origin["lon"]), (destination["lat"], destination["lon"])
    routes, route_warnings = route_source(o, d, depart_iso, load_lb)
    logger.info("plan: %d route(s), %d route warning(s)", len(routes), len(route_warnings))
    if not routes:
        logger.warning("plan: route source returned no routes")

    # 2. Per-vertex times and checkpoints for every interval
    prepared_routes = []
    for idx, r in enumerate(routes):
        times = times_per_point(r.points, r.progress, r.duration_s)
        cps = {iv: build_checkpoints(r.points, times, iv, departure) for iv in intervals}
        prepared_routes.append(PreparedRoute(chr(ord("A") + idx), r, times, cps))

    # 3. Heatmap grid and the forecast window
    polygon = grid = step = None
    if config.CORRIDOR_MODE == "hull":
        polygon = corridor_hull([r.points for r in routes])
        grid = hull_grid(polygon)
        cells = [
            (
                grid["lat0"] + (i // grid["ncols"]) * grid["step"],
                grid["lon0"] + (i % grid["ncols"]) * grid["step"],
            )
            for i, fetch in enumerate(grid["fetch_mask"])
            if fetch
        ]
    elif config.CORRIDOR_MODE == "band":
        cells, step = corridor_grid([r.points for r in routes])
    else:
        raise ValueError('CORRIDOR_MODE must be "hull" or "band"')
    start = departure.replace(minute=0, second=0, microsecond=0)
    last_eta = max((departure + timedelta(seconds=r.duration_s) for r in routes), default=departure)
    end = max(start + timedelta(hours=config.HEATMAP_HOURS), last_eta + timedelta(hours=1))

    prepared = PreparedPlan(
        origin=origin,
        destination=destination,
        departure=departure,
        depart_iso=depart_iso,
        intervals=intervals,
        source_label=source_label,
        routes=prepared_routes,
        route_warnings=route_warnings,
        cells=cells,
        start=start,
        end=end,
        polygon=polygon,
        grid=grid,
        step=step,
    )
    logger.info(
        "plan: %d heatmap cell(s), %d checkpoint(s), %s mode",
        len(cells),
        len(prepared.checkpoint_points()),
        config.CORRIDOR_MODE,
    )
    return prepared


def fetch_weather(prepared: PreparedPlan, weather: WeatherStore) -> None:
    """A single prefetch for every checkpoint and heatmap cell of the plan."""
    weather.prefetch(prepared.checkpoint_points() + prepared.cells, prepared.start, prepared.end)


def route_entry(prepared: PreparedPlan, pr: PreparedRoute) -> dict:
    """A route as the API shows it before any scoring: summary and map geometry. Needs no weather."""
    r = pr.route
    arrival_iso = (prepared.departure + timedelta(seconds=round(r.duration_s))).isoformat(timespec="seconds")
    keep = simplify_indices(r.points, config.FRONTEND_SIMPLIFY_DEG)
    return {
        "id": pr.id,
        "label": f"Route {pr.id}",
        "source": r.source,
        "summary": {
            "distance_mi": round(r.length_m / config.M_PER_MI, 1),
            "duration_s": round(r.duration_s),
            "departure": r.departure or prepared.depart_iso,
            "arrival": r.arrival or arrival_iso,
        },
        "geometry": to_lonlat(r.points[i] for i in keep),
        "times": [round(pr.times[i]) for i in keep],  # lets the UI place a truck at slider time
    }


def _heatmap(prepared: PreparedPlan, weather: WeatherStore, load_lb: float) -> dict:
    """Rectangular hour-major field ("hull"), or the legacy cell-major layout ("band")."""
    start, cells = prepared.start, prepared.cells
    if config.CORRIDOR_MODE == "hull":
        grid = prepared.grid
        size = grid["nrows"] * grid["ncols"]
        values = {
            name: [[None] * size for _ in range(config.HEATMAP_HOURS)]
            for name in ("risk", "wind", "gust", "rain", "snow", "u", "v")
        }
        fetched_indices = (i for i, fetch in enumerate(grid["fetch_mask"]) if fetch)
        for i, (lat, lon) in zip(fetched_indices, cells, strict=True):
            for hour, w in enumerate(weather.hours(lat, lon, start, config.HEATMAP_HOURS)):
                if w is None:
                    continue
                values["risk"][hour][i] = classify(w, load_lb)["risk"]
                u, v = wind_components(w["wind_mph"], w.get("direction_deg"))
                values["u"][hour][i], values["v"][hour][i] = u, v
                for name, field, decimals in (
                    ("wind", "wind_mph", 1),
                    ("gust", "gust_mph", 1),
                    ("rain", "rain_in", 3),
                    ("snow", "snow_in", 3),
                ):
                    values[name][hour][i] = _round(w[field], decimals)
        return {
            "mode": "hull",
            "start": start.isoformat().replace("+00:00", "Z"),
            "hours": config.HEATMAP_HOURS,
            "polygon": to_lonlat(prepared.polygon),
            "grid": {key: value for key, value in grid.items() if key != "fetch_mask"},
            "vars": values,
        }
    heat = {
        "start": start.isoformat().replace("+00:00", "Z"),
        "hours": config.HEATMAP_HOURS,
        "step_deg": prepared.step,
        "cells": [[c[0], c[1]] for c in cells],
        "risk": [],
        "wind": [],
        "rain": [],
        "snow": [],
    }
    for lat, lon in cells:
        series = weather.hours(lat, lon, start, config.HEATMAP_HOURS)
        heat["risk"].append([classify(w, load_lb)["risk"] if w else None for w in series])
        heat["wind"].append([_round(w["wind_mph"], 1) if w else None for w in series])
        heat["rain"].append([_round(w["rain_in"], 3) if w else None for w in series])
        heat["snow"].append([_round(w["snow_in"], 3) if w else None for w in series])
    return heat


def score_plan(
    prepared: PreparedPlan, weather: WeatherStore, load_lb: float, *, include_heatmap: bool = True
) -> dict:
    """Weather and risk at each checkpoint, ranking and heatmap for one load. Leaves `prepared` untouched.

    include_heatmap=False skips the heatmap (and leaves the key out), which is what scoring a partly
    fetched plan needs: the checkpoints of some intervals are in, the heatmap cells are not yet.
    """
    depart_iso = prepared.depart_iso
    warnings: list[str] = []
    gross_lb = load_lb + config.TRUCK_TARE_LB
    if gross_lb > config.MAX_GROSS_LB:
        logger.warning("gross weight %.0f lb exceeds the %d lb limit", gross_lb, config.MAX_GROSS_LB)
        warnings.append(f"gross weight {gross_lb:,.0f} lb exceeds the 80,000 lb federal limit")
    warnings += prepared.route_warnings

    # 4. Weather and risk at each checkpoint's ETA
    missing = 0
    out_routes, rec = [], {}
    for pr in prepared.routes:
        r = pr.route
        entry = route_entry(prepared, pr)
        entry["by_interval"] = {}
        for iv, prepared_cps in pr.checkpoints.items():
            cps = [dict(c) for c in prepared_cps]  # copies: the next load scores the same checkpoints
            for c in cps:
                w = weather.at(c["lat"], c["lon"], datetime.fromisoformat(c["eta"]))
                if w is None:
                    missing += 1
                    c.update(weather=None, risk=0, levels=None, reasons=["no forecast for this hour"])
                    continue
                c["weather"] = _round_weather(w)
                c.update(classify(w, load_lb))
                c["risk_label"] = LEVELS[c["risk"]]
            entry["by_interval"][str(iv)] = {"checkpoints": cps, "score": score_route(cps, r.duration_s)}
        out_routes.append(entry)
    if missing:
        logger.warning("plan: %d checkpoint(s) had no forecast and were scored Low", missing)
        warnings.append(f"{missing} checkpoint(s) had no forecast (beyond forecast range?), scored Low")

    # 5. Ranking per interval
    for iv in prepared.intervals:
        scores = {e["id"]: e["by_interval"][str(iv)]["score"] for e in out_routes}
        order = rank(scores)
        reason = ""
        if order:
            runner_up = scores[order[1]] if len(order) > 1 else None
            reason = explain(scores[order[0]], runner_up)
        rec[str(iv)] = {
            "best": order[0] if order else None,
            "order": order,
            "reason": reason,
            "all_blocked": bool(order) and not scores[order[0]]["drivable"],
        }
        logger.debug("plan: interval %d mi -> best=%s (%s)", iv, rec[str(iv)]["best"], reason)

    result = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": prepared.source_label,
            "departure": depart_iso,
            "load_lb": load_lb,
            "gross_weight_kg": gross_weight_kg(load_lb),
            "intervals": list(prepared.intervals),
            "default_interval": config.DEFAULT_INTERVAL_MI,
            "levels": list(LEVELS),
            "assumptions": {
                "truck_tare_lb": config.TRUCK_TARE_LB,
                "wind_metric": config.WIND_METRIC,
                "avg_risk_tie_eps": config.AVG_RISK_TIE_EPS,
                "checkpoint_weight": "each checkpoint's risk covers the miles since the previous checkpoint",
                "slider_hour_0": "departure time (rounded down to the hour, UTC)",
            },
            "weather_locations_fetched": weather.calls,
            "warnings": warnings,
        },
        "origin": prepared.origin,
        "destination": prepared.destination,
        "routes": out_routes,
        "recommendation": rec,
    }
    if include_heatmap:
        result["heatmap"] = _heatmap(prepared, weather, load_lb)
    return result


def plan(
    origin: dict,
    destination: dict,
    departure: datetime,
    load_lb: float,
    route_source: RouteSource,
    weather: WeatherStore,
    intervals: tuple[int, ...] = config.INTERVALS_MI,
    source_label: str = "live",
) -> dict:
    """origin/destination: {"label", "lat", "lon"}. departure: timezone-aware datetime."""
    started = time.monotonic()
    prepared = prepare(origin, destination, departure, load_lb, route_source, intervals, source_label)
    fetch_weather(prepared, weather)
    result = score_plan(prepared, weather, load_lb)
    logger.info(
        "plan done in %.2fs: %d route(s), %d weather location(s) fetched, %d warning(s)",
        time.monotonic() - started,
        len(result["routes"]),
        weather.calls,
        len(result["meta"]["warnings"]),
    )
    return result
