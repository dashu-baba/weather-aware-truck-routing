"""Turn a routed polyline into evenly spaced checkpoints with ETAs.

Two steps:
  1. times_per_point(): give EVERY polyline vertex a cumulative travel time, by
     spreading each TomTom progress-point interval over haversine distance.
  2. build_checkpoints(): walk the polyline by distance and drop a checkpoint every
     N miles, interpolating position and time inside the segment that crosses the mark.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Sequence

from . import config
from .geo import LatLon, haversine_m, lerp

logger = logging.getLogger(__name__)

Progress = Sequence[tuple[int, float]]  # (path index, cumulative seconds)


def times_per_point(pts: Sequence[LatLon], progress: Progress, total_s: float | None = None) -> list[float]:
    """Cumulative travel time (s) at every vertex.

    progress: sorted (index, seconds) pairs from TomTom; must include first and last point.
    If progress is empty, falls back to spreading total_s uniformly by distance (less accurate:
    ignores that highways are faster than city streets) and logs a warning.
    """
    n = len(pts)
    if n == 0:
        return []
    anchors = sorted({int(i): float(t) for i, t in progress}.items())
    if not anchors:
        if total_s is None:
            raise ValueError("no progress points and no total travel time")
        logger.warning("no TomTom progress points: spreading %.0f s uniformly over %d vertices", total_s, n)
        anchors = [(0, 0.0), (n - 1, float(total_s))]
    if anchors[0][0] != 0:
        anchors.insert(0, (0, 0.0))
    if anchors[-1][0] != n - 1:
        if total_s is None:
            raise ValueError("progress does not reach the last point and total time unknown")
        anchors.append((n - 1, float(total_s)))

    times = [0.0] * n
    for (i0, t0), (i1, t1) in pairwise(anchors):
        if i1 <= i0:
            continue
        seg = [haversine_m(pts[k], pts[k + 1]) for k in range(i0, i1)]
        total = sum(seg)
        times[i0] = t0
        acc = 0.0
        for k in range(i0, i1):
            acc += seg[k - i0]
            f = acc / total if total > 0 else (k + 1 - i0) / (i1 - i0)
            times[k + 1] = t0 + (t1 - t0) * f
    return times


def build_checkpoints(
    pts: Sequence[LatLon],
    times: Sequence[float],
    interval_mi: float,
    departure: datetime | None = None,
) -> list[dict]:
    """Checkpoints at mile 0, every `interval_mi` along the route, and the destination.

    Each checkpoint: mile, lat, lon, elapsed_s, eta (ISO, if departure given) and
    segment_mi = miles since the previous checkpoint. A checkpoint's risk is applied
    to its segment_mi when summing Severe / High miles.
    """
    if len(pts) != len(times):
        raise ValueError("pts and times must have the same length")
    if not pts:
        return []
    step = interval_mi * config.M_PER_MI

    def make(mile_m: float, p: LatLon, t: float) -> dict:
        cp = {"mile": round(mile_m / config.M_PER_MI, 3), "lat": p[0], "lon": p[1], "elapsed_s": round(t, 1)}
        if departure is not None:
            cp["eta"] = (departure + timedelta(seconds=round(t))).isoformat(timespec="seconds")
        return cp

    cps = [make(0.0, pts[0], times[0])]
    walked = 0.0
    next_mark = step
    for i in range(1, len(pts)):
        seg = haversine_m(pts[i - 1], pts[i])
        if seg <= 0:
            continue
        while walked + seg >= next_mark:  # one long segment can hold several checkpoints
            f = (next_mark - walked) / seg
            t = times[i - 1] + f * (times[i] - times[i - 1])
            cps.append(make(next_mark, lerp(pts[i - 1], pts[i], f), t))
            next_mark += step
        walked += seg

    if walked - (next_mark - step) > 1.0:  # destination, unless a mark landed on it
        cps.append(make(walked, pts[-1], times[-1]))

    cps[0]["segment_mi"] = 0.0
    for k in range(1, len(cps)):
        cps[k]["segment_mi"] = round(cps[k]["mile"] - cps[k - 1]["mile"], 3)
    return cps
