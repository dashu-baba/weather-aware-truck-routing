"""Small geometry helpers.

CONVENTION: inside Python every point is a (lat, lon) tuple.
GeoJSON / MapLibre use [lon, lat]; convert ONLY at the boundary with to_lonlat().
"""

from __future__ import annotations

from math import asin, atan2, cos, degrees, radians, sin, sqrt
from typing import Iterable, Sequence

LatLon = tuple[float, float]
EARTH_R_M = 6_371_000.0


def haversine_m(a: LatLon, b: LatLon) -> float:
    """Great-circle distance in meters between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R_M * asin(min(1.0, sqrt(h)))


def lerp(a: LatLon, b: LatLon, f: float) -> LatLon:
    """Linear interpolation between two close points (fine for road vertices)."""
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def cumulative_m(pts: Sequence[LatLon]) -> list[float]:
    """Running distance along a polyline: out[i] = meters from pts[0] to pts[i]."""
    out = [0.0]
    for i in range(1, len(pts)):
        out.append(out[-1] + haversine_m(pts[i - 1], pts[i]))
    return out


def destination(p: LatLon, bearing_deg: float, dist_m: float) -> LatLon:
    """Point reached from p after travelling dist_m on the given bearing."""
    lat1, lon1, brg = radians(p[0]), radians(p[1]), radians(bearing_deg)
    d = dist_m / EARTH_R_M
    lat2 = asin(sin(lat1) * cos(d) + cos(lat1) * sin(d) * cos(brg))
    lon2 = lon1 + atan2(sin(brg) * sin(d) * cos(lat1), cos(d) - sin(lat1) * sin(lat2))
    return (degrees(lat2), (degrees(lon2) + 540) % 360 - 180)


def bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lat2 = radians(a[0]), radians(b[0])
    dlon = radians(b[1] - a[1])
    y = sin(dlon) * cos(lat2)
    x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    return (degrees(atan2(y, x)) + 360) % 360


def _perp_dist_deg(p: LatLon, a: LatLon, b: LatLon) -> float:
    """Distance (in degrees, lon scaled by cos(lat)) from p to segment ab. For simplification only."""
    k = cos(radians(p[0]))
    px, py = p[1] * k, p[0]
    ax, ay = a[1] * k, a[0]
    bx, by = b[1] * k, b[0]
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return sqrt((px - ax) ** 2 + (py - ay) ** 2)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return sqrt((px - cx) ** 2 + (py - cy) ** 2)


def simplify_indices(pts: Sequence[LatLon], tolerance_deg: float) -> list[int]:
    """Douglas-Peucker (iterative); returns the indices of the vertices to keep."""
    n = len(pts)
    if n < 3:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        best_i, best_d = -1, -1.0
        for i in range(s + 1, e):
            d = _perp_dist_deg(pts[i], pts[s], pts[e])
            if d > best_d:
                best_i, best_d = i, d
        if best_d > tolerance_deg:
            keep[best_i] = True
            stack.append((s, best_i))
            stack.append((best_i, e))
    return [i for i, k in enumerate(keep) if k]


def simplify(pts: Sequence[LatLon], tolerance_deg: float) -> list[LatLon]:
    """Use ONLY for drawing / coarse work; do all distance and time maths on full-resolution points."""
    return [pts[i] for i in simplify_indices(pts, tolerance_deg)]


def to_lonlat(pts: Iterable[LatLon], ndigits: int = 5) -> list[list[float]]:
    """(lat, lon) -> GeoJSON [lon, lat]."""
    return [[round(p[1], ndigits), round(p[0], ndigits)] for p in pts]
