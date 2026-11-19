"""TomTom client: geocoding (Search API v2) and TRUCK routing (Routing API v1).

Key facts:
  * Truck routing exists only on /routing/1/calculateRoute ("TomTom Maps").
    The Orbis endpoints (/maps/orbis/...) are car-only - never use them here.
  * vehicleWeight is GROSS weight in kg (truck + load), not the load.
  * Response field names for progress points have differed between docs/SDKs
    (progressPoints/pathIndex/travelDurationInSeconds vs progress/pointIndex/travelTimeInSeconds).
    parse_route() accepts both - log one real response and pin the real shape in a test.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import requests

from . import config
from .geo import LatLon, bearing_deg, cumulative_m, destination, haversine_m, lerp

logger = logging.getLogger(__name__)


class TomTomError(RuntimeError):
    """TomTom failed. `code` is TomTom's detailedError.code (e.g. NO_ROUTE_FOUND) when it sent one."""

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.code = code


# Codes that mean the user's points can't be routed, as opposed to a TomTom or configuration failure.
NO_ROUTE_CODES = frozenset({"NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"})


def geocode(
    query: str,
    *,
    typeahead: bool = False,
    limit: int = 5,
    country_set: str = "US",
    session: requests.Session | None = None,
) -> list[dict]:
    """Fuzzy Search. typeahead=True for autocomplete (debounce in the UI - every call costs quota)."""
    _require_key()
    http = session or requests
    url = f"{config.TOMTOM_SEARCH_URL}/{requests.utils.quote(query, safe='')}.json"
    params = {"key": config.TOMTOM_API_KEY, "limit": limit, "typeahead": str(typeahead).lower()}
    if country_set:
        params["countrySet"] = country_set
    started = time.monotonic()
    r = http.get(url, params=params, timeout=config.HTTP_TIMEOUT_S)
    logger.debug("TomTom search -> HTTP %s in %.2fs", r.status_code, time.monotonic() - started)
    _raise_for(r)
    return [
        {
            "label": res.get("address", {}).get("freeformAddress") or res.get("poi", {}).get("name", ""),
            "lat": res["position"]["lat"],
            "lon": res["position"]["lon"],
            "type": res.get("type"),
        }
        for res in r.json().get("results", [])
        if "position" in res
    ]


def reverse_geocode(lat: float, lon: float, *, session: requests.Session | None = None) -> dict | None:
    """The nearest address to a point, for labelling a pin dropped on the map.

    Returns None when TomTom knows no address there (open water, wilderness). Not limited to one country.
    """
    _require_key()
    http = session or requests
    url = f"{config.TOMTOM_REVERSE_URL}/{lat},{lon}.json"
    started = time.monotonic()
    r = http.get(url, params={"key": config.TOMTOM_API_KEY}, timeout=config.HTTP_TIMEOUT_S)
    logger.debug("TomTom reverse geocode -> HTTP %s in %.2fs", r.status_code, time.monotonic() - started)
    _raise_for(r)
    addresses = r.json().get("addresses") or []
    address = (addresses[0].get("address") or {}) if addresses else {}
    label = address.get("freeformAddress")
    if not label:
        return None
    return {"label": label, "country": address.get("countryCode")}


def gross_weight_kg(load_lb: float) -> int:
    return round((load_lb + config.TRUCK_TARE_LB) * config.KG_PER_LB)


def calculate_route(
    locations: list[LatLon],
    depart_at: str,
    load_lb: float,
    *,
    max_alternatives: int,
    session: requests.Session | None = None,
) -> dict:
    """Raw /calculateRoute call. depart_at: RFC 3339 WITH offset, e.g. 2026-11-20T08:00:00Z."""
    _require_key()
    http = session or requests
    locs = ":".join(f"{lat:.6f},{lon:.6f}" for lat, lon in locations)
    params: list[tuple[str, Any]] = [
        ("key", config.TOMTOM_API_KEY),
        ("travelMode", "truck"),
        ("vehicleWeight", gross_weight_kg(load_lb)),
        ("vehicleCommercial", "true"),
        ("routeType", "fastest"),  # 'shortest' can time out on long routes
        ("traffic", "false"),  # future departures: historic speeds, not live traffic
        ("departAt", depart_at),
        ("maxAlternatives", max_alternatives),
        ("routeRepresentation", "polyline"),
        ("extendedRouteRepresentation", "distance"),  # repeated param ->
        ("extendedRouteRepresentation", "travelTime"),  # progress points with time + distance
        ("computeTravelTimeFor", "all"),
        ("sectionType", "travelMode"),
        ("report", "effectiveSettings"),
    ]
    if max_alternatives > 0:  # TomTom rejects alternativeType when maxAlternatives is 0
        params.append(("alternativeType", "anyRoute"))
    started = time.monotonic()
    r = http.get(f"{config.TOMTOM_ROUTING_URL}/{locs}/json", params=params, timeout=config.HTTP_TIMEOUT_S)
    logger.debug(
        "TomTom routing (%d waypoints, maxAlternatives=%d) -> HTTP %s in %.2fs",
        len(locations),
        max_alternatives,
        r.status_code,
        time.monotonic() - started,
    )
    _raise_for(r)
    return r.json()


@dataclass
class ParsedRoute:
    points: list[LatLon]  # full resolution, (lat, lon)
    progress: list[tuple[int, float]]  # (path index, cumulative seconds)
    length_m: float
    duration_s: float
    departure: str | None
    arrival: str | None
    traffic_delay_s: float = 0.0
    warnings: list[str] = field(default_factory=list)
    source: str = "tomtom"


def _progress_entries(raw: list[dict], index_offset: int = 0) -> list[tuple[int, float]]:
    out = []
    for p in raw or []:
        idx = p.get("pathIndex", p.get("pointIndex"))
        t = p.get("travelDurationInSeconds", p.get("travelTimeInSeconds"))
        if idx is not None and t is not None:
            out.append((int(idx) + index_offset, float(t)))
    return out


def parse_route(route: dict) -> ParsedRoute:
    """One element of response["routes"] -> ParsedRoute (joins legs, normalises progress)."""
    pts: list[LatLon] = []
    leg_offsets: list[int] = []
    for leg in route.get("legs", []):
        leg_offsets.append(len(pts))
        # Keep the duplicated junction vertex: TomTom's progress and section indices count it.
        pts.extend((p["latitude"], p["longitude"]) for p in leg.get("points", []))

    summary = route.get("summary", {})
    warnings: list[str] = []

    progress = _progress_entries(route.get("progressPoints") or route.get("progress") or [])
    if not progress:  # some shapes put progress on each leg with leg-relative indices
        for leg, off in zip(route.get("legs", []), leg_offsets, strict=True):
            progress += _progress_entries(leg.get("progressPoints") or leg.get("progress") or [], off)
    if not progress:
        warnings.append("no progress points in response; ETAs spread uniformly by distance")

    others = [
        s
        for s in route.get("sections", [])
        if s.get("sectionType") == "TRAVEL_MODE" and str(s.get("travelMode", "")).lower() == "other"
    ]
    if others:
        warnings.append(f"{len(others)} section(s) where truck mode could not be applied (travelMode=other)")

    length_m = float(summary.get("lengthInMeters", 0))
    hav = cumulative_m(pts)[-1] if pts else 0.0
    if length_m and pts and abs(hav - length_m) / length_m > 0.02:
        warnings.append(f"haversine length {hav:.0f} m differs from summary {length_m:.0f} m by >2%")

    return ParsedRoute(
        points=pts,
        progress=sorted(set(progress)),
        length_m=length_m,
        duration_s=float(summary.get("travelTimeInSeconds", 0)),
        departure=summary.get("departureTime"),
        arrival=summary.get("arrivalTime"),
        traffic_delay_s=float(summary.get("trafficDelayInSeconds", 0)),
        warnings=warnings,
    )


def check_effective_settings(response: dict) -> list[str]:
    """Confirm TomTom really used truck mode (report=effectiveSettings)."""
    settings = {s.get("key"): s.get("value") for s in response.get("report", {}).get("effectiveSettings", [])}
    if settings and settings.get("travelMode") != "truck":
        return [f"TomTom used travelMode={settings.get('travelMode')!r}, not truck"]
    return []


def overlap_ratio(a: list[LatLon], b: list[LatLon], tol_deg: float = 0.01) -> float:
    """Share of route a's length lying within ~1 km of route b (grid-hash, fast)."""

    def densify(pts, spacing_m=500.0):
        out = []
        for p, q in pairwise(pts):
            n = max(1, int(haversine_m(p, q) // spacing_m))
            out.extend(lerp(p, q, k / n) for k in range(n))
        return out + pts[-1:]

    cells = {(round(p[0] / tol_deg), round(p[1] / tol_deg)) for p in densify(b)}
    samples = densify(a, 2000.0)
    if not samples:
        return 0.0
    hit = 0
    for p in samples:
        ci, cj = round(p[0] / tol_deg), round(p[1] / tol_deg)
        if any((ci + di, cj + dj) in cells for di in (-1, 0, 1) for dj in (-1, 0, 1)):
            hit += 1
    return hit / len(samples)


def pick_distinct(routes: list[ParsedRoute], k: int = config.TARGET_ROUTES) -> list[ParsedRoute]:
    """Keep up to k routes, skipping near-duplicates. TomTom returns the main route first."""
    kept: list[ParsedRoute] = []
    for r in routes:
        if all(overlap_ratio(r.points, other.points) < config.DUPLICATE_OVERLAP for other in kept):
            kept.append(r)
        if len(kept) == k:
            break
    return kept


def via_point_candidates(main: ParsedRoute) -> list[LatLon]:
    """Points offset sideways from the main route's midpoint, to force a different corridor."""
    pts = main.points
    cum = cumulative_m(pts)
    half = cum[-1] / 2
    i = next(k for k, d in enumerate(cum) if d >= half)
    mid = pts[i]
    heading = bearing_deg(pts[max(0, i - 5)], pts[min(len(pts) - 1, i + 5)])
    crow = haversine_m(pts[0], pts[-1])
    out = []
    for frac in (0.12, 0.22):
        off = min(max(frac * crow, 15_000), 120_000)
        out += [destination(mid, heading + 90, off), destination(mid, heading - 90, off)]
    return out


def three_routes(
    origin: LatLon, dest: LatLon, depart_at: str, load_lb: float, session: requests.Session | None = None
) -> tuple[list[ParsedRoute], list[str]]:
    """Main entry: up to 3 distinct truck routes + warnings for the UI/logs."""
    warnings: list[str] = []
    resp = None
    timeout: requests.Timeout | None = None
    for alts in (config.MAX_ALTERNATIVES, 0):  # the alternatives search is the slow part, so retry without it
        try:
            resp = calculate_route([origin, dest], depart_at, load_lb, max_alternatives=alts, session=session)
            break
        except requests.Timeout as exc:
            timeout = exc
            logger.warning("TomTom routing timed out with maxAlternatives=%d", alts)
            warnings.append(f"TomTom timed out with maxAlternatives={alts}; retrying with fewer")
    if resp is None:
        raise timeout  # callers map requests.Timeout to 504
    warnings += check_effective_settings(resp)
    routes = pick_distinct([parse_route(r) for r in resp.get("routes", [])])
    if not routes:
        raise TomTomError("TomTom returned no route", code="NO_ROUTE_FOUND")

    for via in via_point_candidates(routes[0]):  # top up to 3 with forced detours
        if len(routes) >= config.TARGET_ROUTES:
            break
        try:
            extra = calculate_route(
                [origin, via, dest], depart_at, load_lb, max_alternatives=0, session=session
            )
        except requests.Timeout:
            # TomTom is slow: return what we have instead of waiting out every remaining candidate.
            logger.warning("via-point route timed out; skipping the remaining detours")
            warnings.append("via-point route timed out; fewer than 3 routes returned")
            break
        except TomTomError as exc:
            logger.warning("via-point route failed: %s", exc)
            warnings.append(f"via-point route failed: {exc}")
            continue
        for r in extra.get("routes", []):
            cand = parse_route(r)
            cand.source = "tomtom-via"
            if all(overlap_ratio(cand.points, o.points) < config.DUPLICATE_OVERLAP for o in routes):
                routes.append(cand)
                break
    logger.info("TomTom: %d distinct route(s) found", len(routes))
    if len(routes) < config.TARGET_ROUTES:
        warnings.append(f"only {len(routes)} distinct route(s) found")
    for r in routes:
        warnings += r.warnings
    return routes, warnings


def _require_key() -> None:
    if not config.TOMTOM_API_KEY:
        raise TomTomError("TOMTOM_API_KEY is not set (copy .env.example to .env)")


def _raise_for(r: requests.Response) -> None:
    if r.ok:
        return
    msg = r.text[:300]
    code = None
    logger.warning("TomTom returned HTTP %s", r.status_code)
    try:
        body = r.json()
        detailed = body.get("detailedError")
        if isinstance(detailed, dict):
            code = detailed.get("code")
        err = body.get("error")
        msg = (
            (detailed.get("message") if isinstance(detailed, dict) else None)
            or (err.get("description") if isinstance(err, dict) else err)
            or body.get("errorText")
            or msg
        )
    except (ValueError, AttributeError):
        pass
    raise TomTomError(f"TomTom HTTP {r.status_code}: {msg}", code=code)
