"""Checkpoint spacing, distance interpolation and arrival times."""

from datetime import datetime, timedelta, timezone
from itertools import pairwise

import pytest

from routing import config
from routing.checkpoints import build_checkpoints, times_per_point
from routing.geo import cumulative_m, destination, haversine_m


def line(miles=101.3, segments=202):
    return [
        destination((35.0, -100.0), 0, miles * config.M_PER_MI * i / segments) for i in range(segments + 1)
    ]


@pytest.mark.parametrize("interval", [10, 25, 50], ids=["ten-mile", "twenty-five-mile", "fifty-mile"])
def test_spacing_and_segment_totals(interval):
    pts = line()
    length = sum(haversine_m(a, b) for a, b in pairwise(pts)) / config.M_PER_MI
    cps = build_checkpoints(pts, times_per_point(pts, [], 7200), interval)
    marks = list(range(0, 101, interval))
    assert [cp["mile"] for cp in cps[:-1]] == pytest.approx(marks, abs=0.001)
    assert cps[-1]["mile"] == pytest.approx(length, abs=0.001)
    assert sum(cp["segment_mi"] for cp in cps) == pytest.approx(length, abs=0.01)
    assert cps[0]["segment_mi"] == 0


def test_short_route_has_origin_and_destination():
    pts = line(5, 10)
    cps = build_checkpoints(pts, times_per_point(pts, [], 600), 10)
    assert len(cps) == 2
    assert cps[-1]["mile"] == pytest.approx(haversine_m(pts[0], pts[-1]) / config.M_PER_MI, abs=0.001)


@pytest.mark.parametrize("offset_m", [-1e-7, 0, 1e-7], ids=["just-under", "exact", "just-over"])
def test_destination_on_mark_is_present_once(offset_m):
    pts = line(20 + offset_m / config.M_PER_MI, 40)
    cps = build_checkpoints(pts, times_per_point(pts, [], 1200), 10)
    assert sum(haversine_m((cp["lat"], cp["lon"]), pts[-1]) < 1 for cp in cps) == 1


def test_long_segment_contains_multiple_marks():
    pts = line(60, 1)
    cps = build_checkpoints(pts, [0, 3600], 10)
    assert [cp["mile"] for cp in cps] == pytest.approx(list(range(0, 61, 10)), abs=0.001)


def test_progress_anchors_and_distance_interpolation():
    pts = line()
    mid, last = len(pts) // 2, len(pts) - 1
    times = times_per_point(pts, [(0, 0), (mid, 1800), (last, 7200)])
    distances = cumulative_m(pts)
    assert times[0] == 0
    assert times[mid] == 1800
    assert times[last] == 7200
    assert all(a <= b for a, b in pairwise(times))
    for lo, hi in [(0, mid), (mid, last)]:
        for i in range(lo, hi + 1):
            fraction = (distances[i] - distances[lo]) / (distances[hi] - distances[lo])
            assert times[i] == pytest.approx(times[lo] + fraction * (times[hi] - times[lo]))


def test_no_progress_spreads_time_by_distance():
    pts = line()
    times = times_per_point(pts, [], total_s=3600)
    distances = cumulative_m(pts)
    assert times == pytest.approx([3600 * d / distances[-1] for d in distances])
    assert times[len(pts) // 2] == pytest.approx(1800)


def test_checkpoint_arrival_times():
    pts = line()
    departure = datetime(2026, 11, 20, 8, tzinfo=timezone.utc)
    cps = build_checkpoints(pts, times_per_point(pts, [], 7200), 10, departure)
    etas = [datetime.fromisoformat(cp["eta"]) for cp in cps]
    for cp, eta in zip(cps, etas, strict=True):
        assert eta == departure + timedelta(seconds=round(cp["elapsed_s"]))
    assert all(a <= b for a, b in pairwise(etas))


def test_mismatched_points_and_times():
    with pytest.raises(ValueError, match="same length"):
        build_checkpoints(line(5, 1), [0], 10)
