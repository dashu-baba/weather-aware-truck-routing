"""Buffered convex hull and legacy route-band heatmap grids (pure geometry)."""

from __future__ import annotations

from itertools import pairwise
from math import ceil, cos, floor, radians
from typing import Sequence, TypedDict

from . import config
from .geo import LatLon, destination, haversine_m, lerp, simplify

STEP_LADDER = (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5, 2.0)
M_PER_DEG_LAT = 111_320.0


def _densify(pts: Sequence[LatLon], spacing_m: float) -> list[LatLon]:
    out = [pts[0]]
    for a, b in pairwise(pts):
        d = haversine_m(a, b)
        n = max(1, ceil(d / spacing_m))
        out.extend(lerp(a, b, k / n) for k in range(1, n + 1))
    return out


def cells_for_step(routes: Sequence[Sequence[LatLon]], step: float, buffer_mi: float) -> set[tuple[int, int]]:
    buffer_m = buffer_mi * config.M_PER_MI
    cells: set[tuple[int, int]] = set()
    for pts in routes:
        if not pts:
            continue
        coarse = simplify(pts, step / 4)
        for s in _densify(coarse, spacing_m=step * M_PER_DEG_LAT / 2):
            ci, cj = round(s[0] / step), round(s[1] / step)
            ri = ceil(buffer_m / M_PER_DEG_LAT / step) + 1
            rj = ceil(buffer_m / (M_PER_DEG_LAT * max(0.2, cos(radians(s[0])))) / step) + 1
            for i in range(ci - ri, ci + ri + 1):
                for j in range(cj - rj, cj + rj + 1):
                    if (i, j) in cells:
                        continue
                    if haversine_m(s, (i * step, j * step)) <= buffer_m:
                        cells.add((i, j))
    return cells


def corridor_grid(
    routes: Sequence[Sequence[LatLon]],
    buffer_mi: float = config.CORRIDOR_BUFFER_MI,
    max_cells: int = config.HEATMAP_MAX_CELLS,
    min_step: float = config.HEATMAP_MIN_STEP_DEG,
) -> tuple[list[LatLon], float]:
    """Returns (cell centres as (lat, lon), step_deg). Coarsens the grid until it fits max_cells."""
    ladder = [s for s in STEP_LADDER if s >= min_step] or [min_step]
    cells: set[tuple[int, int]] = set()
    step = ladder[0]
    for step in ladder:
        cells = cells_for_step(routes, step, buffer_mi)
        if len(cells) <= max_cells:
            break
    centres = sorted((round(i * step, 4), round(j * step, 4)) for i, j in cells)
    return centres, step


class HullGrid(TypedDict):
    lat0: float
    lon0: float
    step: float
    nrows: int
    ncols: int
    fetch_mask: list[bool]


def convex_hull(points: list[LatLon]) -> list[LatLon]:
    """Monotone chain in (lon*cos(mean latitude), lat); unclosed, no collinear vertices."""
    if not points:
        return []
    scale = cos(radians(sum(lat for lat, lon in points) / len(points)))
    ordered = sorted(set(points), key=lambda p: (p[1] * scale, p[0]))
    if len(ordered) <= 1:
        return ordered

    def cross(a: LatLon, b: LatLon, c: LatLon) -> float:
        ay, ax = a
        by, bx = b
        cy, cx = c
        return ((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) * scale

    lower: list[LatLon] = []
    upper: list[LatLon] = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def corridor_hull(
    routes: Sequence[Sequence[LatLon]],
    buffer_mi: float = config.HULL_BUFFER_MI,
) -> list[LatLon]:
    """One closed hull, buffered by geodesic circles around its simplified vertices."""
    if buffer_mi < 0:
        raise ValueError("buffer_mi must be non-negative")
    hull = convex_hull([p for route in routes for p in simplify(route, config.HULL_SIMPLIFY_DEG)])
    buffered = convex_hull(
        [
            destination(vertex, i * 360 / config.HULL_BUFFER_POINTS, buffer_mi * config.M_PER_MI)
            for vertex in hull
            for i in range(config.HULL_BUFFER_POINTS)
        ]
    )
    return buffered + buffered[:1]


def point_in_polygon(lat: float, lon: float, polygon: Sequence[LatLon]) -> bool:
    """Ray casting, including boundary points. Coordinates are (lat, lon)."""
    if not polygon:
        return False
    inside = False
    for (ay, ax), (by, bx) in zip(polygon, [*polygon[1:], polygon[0]], strict=True):
        cross = (lon - ax) * (by - ay) - (lat - ay) * (bx - ax)
        if (
            abs(cross) <= 1e-10
            and min(ax, bx) - 1e-10 <= lon <= max(ax, bx) + 1e-10
            and min(ay, by) - 1e-10 <= lat <= max(ay, by) + 1e-10
        ):
            return True
        if (ay > lat) != (by > lat) and lon < ax + (lat - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def hull_grid(
    polygon: Sequence[LatLon],
    max_cells: int = config.HEATMAP_MAX_CELLS,
    min_step: float = config.HEATMAP_MIN_STEP_DEG,
) -> HullGrid:
    """South-first rectangular grid, padded by one cell; fetch inside plus 8 neighbours.

    Continue coarsening beyond STEP_LADDER if necessary: the fetch budget is a hard cap.
    lat0/lon0 locate the southwest cell CENTRE, on global multiples of step.
    """
    if min_step <= 0 or max_cells < 1:
        raise ValueError("min_step and max_cells must be positive")
    if not polygon:
        return dict(lat0=0.0, lon0=0.0, step=min_step, nrows=0, ncols=0, fetch_mask=[])
    lats, lons = zip(*polygon, strict=True)
    ladder = iter(s for s in STEP_LADDER if s >= min_step)
    step = next(ladder, min_step)
    while True:
        south, north = floor(min(lats) / step) - 1, ceil(max(lats) / step) + 1
        west, east = floor(min(lons) / step) - 1, ceil(max(lons) / step) + 1
        nrows, ncols = north - south + 1, east - west + 1
        inside = {
            (r, c)
            for r in range(nrows)
            for c in range(ncols)
            if point_in_polygon((south + r) * step, (west + c) * step, polygon)
        }
        fetch = {
            (r + dr, c + dc)
            for r, c in inside
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if 0 <= r + dr < nrows and 0 <= c + dc < ncols
        }
        if len(fetch) <= max_cells:
            return dict(
                lat0=round(south * step, 10),
                lon0=round(west * step, 10),
                step=step,
                nrows=nrows,
                ncols=ncols,
                fetch_mask=[(r, c) in fetch for r in range(nrows) for c in range(ncols)],
            )
        if max_cells < 9:
            raise ValueError("max_cells must allow an inside cell and its 1-cell ring (at least 9)")
        step = next(ladder, step * 2)
