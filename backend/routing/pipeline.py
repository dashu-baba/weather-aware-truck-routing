"""End-to-end planner: routes -> checkpoints -> weather -> risk -> ranking -> heatmap.

This is the service layer: views call plan() and return its dict. It never calls an API
directly - it receives a `route_source` and a `WeatherStore`, so tests can swap in fakes.
"""

from __future__ import annotations

import logging
import time
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
    if departure.tzinfo is None:
        raise ValueError("departure must be timezone-aware (send ISO 8601 with an offset)")
    started = time.monotonic()
    departure = departure.astimezone(timezone.utc)
    depart_iso = departure.isoformat().replace("+00:00", "Z")
    warnings: list[str] = []
    gross_lb = load_lb + config.TRUCK_TARE_LB
    if gross_lb > config.MAX_GROSS_LB:
        logger.warning("gross weight %.0f lb exceeds the %d lb limit", gross_lb, config.MAX_GROSS_LB)
        warnings.append(f"gross weight {gross_lb:,.0f} lb exceeds the 80,000 lb federal limit")

    # 1. Routes
    o, d = (origin["lat"], origin["lon"]), (destination["lat"], destination["lon"])
    routes, route_warnings = route_source(o, d, depart_iso, load_lb)
    warnings += route_warnings
    logger.info("plan: %d route(s), %d route warning(s)", len(routes), len(route_warnings))
    if not routes:
        logger.warning("plan: route source returned no routes")

    # 2. Per-vertex times and checkpoints for every interval
    prepared = []
    for idx, r in enumerate(routes):
        times = times_per_point(r.points, r.progress, r.duration_s)
        cps = {iv: build_checkpoints(r.points, times, iv, departure) for iv in intervals}
        prepared.append((chr(ord("A") + idx), r, times, cps))

    # 3. Heatmap grid and a single weather prefetch for everything
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
    all_points = [(c["lat"], c["lon"]) for _, _, _, by in prepared for cps in by.values() for c in cps]
    logger.info(
        "plan: %d heatmap cell(s), %d checkpoint(s), %s mode",
        len(cells),
        len(all_points),
        config.CORRIDOR_MODE,
    )
    weather.prefetch(all_points + cells, start, end)

    # 4. Weather and risk at each checkpoint's ETA
    missing = 0
    out_routes, rec = [], {}
    for rid, r, times, by_iv in prepared:
        arrival_iso = (departure + timedelta(seconds=round(r.duration_s))).isoformat(timespec="seconds")
        entry = {
            "id": rid,
            "label": f"Route {rid}",
            "source": r.source,
            "summary": {
                "distance_mi": round(r.length_m / config.M_PER_MI, 1),
                "duration_s": round(r.duration_s),
                "departure": r.departure or depart_iso,
                "arrival": r.arrival or arrival_iso,
            },
            "by_interval": {},
        }
        keep = simplify_indices(r.points, config.FRONTEND_SIMPLIFY_DEG)
        entry["geometry"] = to_lonlat(r.points[i] for i in keep)
        entry["times"] = [round(times[i]) for i in keep]  # lets the UI place a truck at slider time
        for iv, cps in by_iv.items():
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
    for iv in intervals:
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

    # 6. Heatmap: rectangular hour-major field ("hull"), or the legacy cell-major layout ("band")
    if config.CORRIDOR_MODE == "hull":
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
        heat = {
            "mode": "hull",
            "start": start.isoformat().replace("+00:00", "Z"),
            "hours": config.HEATMAP_HOURS,
            "polygon": to_lonlat(polygon),
            "grid": {key: value for key, value in grid.items() if key != "fetch_mask"},
            "vars": values,
        }
    else:
        heat = {
            "start": start.isoformat().replace("+00:00", "Z"),
            "hours": config.HEATMAP_HOURS,
            "step_deg": step,
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

    logger.info(
        "plan done in %.2fs: %d route(s), %d weather location(s) fetched, %d warning(s)",
        time.monotonic() - started,
        len(out_routes),
        weather.calls,
        len(warnings),
    )
    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": source_label,
            "departure": depart_iso,
            "load_lb": load_lb,
            "gross_weight_kg": gross_weight_kg(load_lb),
            "intervals": list(intervals),
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
        "origin": origin,
        "destination": destination,
        "routes": out_routes,
        "recommendation": rec,
        "heatmap": heat,
    }
