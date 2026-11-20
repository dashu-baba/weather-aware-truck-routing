"""travelMode=other sections: short connections are ignored, long stretches become one route note."""

import json
from pathlib import Path

import pytest

from routing import config, tomtom
from routing.geo import cumulative_m
from routing.pipeline import _route_warnings

FIXTURE = Path(__file__).parent / "fixtures" / "tomtom_multi_leg.json"
STEP_DEG = 0.001  # ~0.069 mi of latitude per point


def straight_route(n_points: int, sections: list[dict], legs: int = 1) -> dict:
    points = [{"latitude": 35 + i * STEP_DEG, "longitude": -100.0} for i in range(n_points)]
    size = -(-n_points // legs)
    return {
        "summary": {"lengthInMeters": cumulative_m([(p["latitude"], p["longitude"]) for p in points])[-1]},
        "legs": [{"points": points[i : i + size]} for i in range(0, n_points, size)],
        "sections": sections,
    }


def other(start, end):
    return {
        "sectionType": "TRAVEL_MODE",
        "travelMode": "other",
        "startPointIndex": start,
        "endPointIndex": end,
    }


def miles(start, end):
    return (end - start) * STEP_DEG * 111_195 / config.M_PER_MI


def test_short_connection_is_ignored():
    parsed = tomtom.parse_route(straight_route(100, [other(0, 3)]))
    assert parsed.non_truck_mi == 0
    assert not any("truck" in w for w in parsed.warnings)
    assert _route_warnings(parsed) == []


def test_long_stretch_becomes_one_note_with_its_miles():
    end = 26  # ~1.8 mi
    parsed = tomtom.parse_route(straight_route(100, [other(0, 3), other(40, 40 + end)]))
    assert parsed.non_truck_mi == pytest.approx(round(miles(40, 40 + end), 1))
    assert parsed.non_truck_mi == pytest.approx(1.8, abs=0.1)
    note = _route_warnings(parsed)
    assert note == [
        f"{parsed.non_truck_mi:.1f} mi of this route may not suit trucks (TomTom could not apply truck rules)"
    ]


def test_several_legs_with_short_ends_give_no_note():
    sections = [other(0, 2), other(48, 50), other(50, 52), other(97, 99)]
    parsed = tomtom.parse_route(straight_route(100, sections, legs=2))
    assert parsed.non_truck_mi == 0


@pytest.mark.parametrize(
    "section",
    [
        {"sectionType": "TRAVEL_MODE", "travelMode": "other"},
        other(5, 2),
        other(0, 500),
        {**other(0, 50), "startPointIndex": "0"},
    ],
    ids=["no-indexes", "reversed", "out-of-range", "not-an-int"],
)
def test_unusable_indexes_are_ignored_safely(section):
    assert tomtom.parse_route(straight_route(100, [section])).non_truck_mi == 0


def test_truck_sections_do_not_count():
    section = {"sectionType": "TRAVEL_MODE", "travelMode": "truck", "startPointIndex": 0, "endPointIndex": 99}
    assert tomtom.parse_route(straight_route(100, [section])).non_truck_mi == 0


def test_real_response_has_only_a_short_start_connection():
    raw = json.loads(FIXTURE.read_text())
    parsed = tomtom.parse_route(raw["routes"][0])
    assert parsed.non_truck_mi == 0
    assert not any("travelMode" in w for w in parsed.warnings)
