"""TomTom routing: pinned against a real multi-leg truck response saved in tests/fixtures."""

import copy
import json
from pathlib import Path

import pytest
import requests

from routing import tomtom
from routing.checkpoints import times_per_point

FIXTURE = Path(__file__).parent / "fixtures" / "tomtom_multi_leg.json"
ORIGIN, DEST = (32.7767, -96.797), (32.80, -96.80)


@pytest.fixture
def raw():
    return json.loads(FIXTURE.read_text())


class FakeResponse:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeSession:
    """Records every request and answers with canned payloads, one per call."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, list(params)))
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload)


def shifted(payload, dlat):
    """Copy of a response with every vertex moved north, so it counts as a different route."""
    out = copy.deepcopy(payload)
    for leg in out["routes"][0]["legs"]:
        for p in leg["points"]:
            p["latitude"] += dlat
    return out


def test_multi_leg_progress_indices_match_the_joined_points(raw):
    parsed = tomtom.parse_route(raw["routes"][0])

    # TomTom counts the duplicated junction vertex, so indices must too (this used to be off by one).
    assert len(parsed.points) == sum(len(leg["points"]) for leg in raw["routes"][0]["legs"])
    assert max(i for i, _ in parsed.progress) == len(parsed.points) - 1
    assert parsed.progress[0] == (0, 0.0)


def test_multi_leg_times_cover_every_vertex(raw):
    parsed = tomtom.parse_route(raw["routes"][0])

    times = times_per_point(parsed.points, parsed.progress, parsed.duration_s)

    assert len(times) == len(parsed.points)
    assert times[0] == 0
    assert times[-1] == pytest.approx(parsed.duration_s)
    assert times == sorted(times)


def test_parse_route_reads_real_summary(raw):
    parsed = tomtom.parse_route(raw["routes"][0])

    assert parsed.length_m == raw["routes"][0]["summary"]["lengthInMeters"]
    assert parsed.duration_s == raw["routes"][0]["summary"]["travelTimeInSeconds"]
    assert parsed.source == "tomtom"


def test_effective_settings_confirm_truck_mode(raw):
    assert tomtom.check_effective_settings(raw) == []
    raw["report"]["effectiveSettings"] = [{"key": "travelMode", "value": "car"}]
    assert "not truck" in tomtom.check_effective_settings(raw)[0]


@pytest.mark.parametrize(("alternatives", "expect_type"), [(0, False), (2, True)])
def test_alternative_type_is_sent_only_with_alternatives(raw, alternatives, expect_type):
    session = FakeSession(raw)

    tomtom.calculate_route(
        [ORIGIN, DEST], "2026-11-20T09:00:00Z", 30_000, max_alternatives=alternatives, session=session
    )

    params = dict(session.calls[0][1])
    assert ("alternativeType" in params) is expect_type
    assert params["maxAlternatives"] == alternatives


def test_gross_weight_adds_truck_tare():
    assert tomtom.gross_weight_kg(30_000) == 29_484


def test_three_routes_tops_up_with_via_point_routes(raw):
    main = {**raw, "routes": raw["routes"][:1]}
    session = FakeSession(main, shifted(raw, 0.5), shifted(raw, -0.5))

    routes, warnings = tomtom.three_routes(ORIGIN, DEST, "2026-11-20T09:00:00Z", 30_000, session=session)

    assert [r.source for r in routes] == ["tomtom", "tomtom-via", "tomtom-via"]
    assert not [w for w in warnings if "via-point route failed" in w]
    for _, params in session.calls[1:]:
        assert dict(params)["maxAlternatives"] == 0
        assert "alternativeType" not in dict(params)


def test_main_route_timeout_is_raised_as_a_timeout_after_one_retry():
    session = FakeSession(requests.Timeout("slow"), requests.Timeout("slow"))

    with pytest.raises(requests.Timeout):
        tomtom.three_routes(ORIGIN, DEST, "2026-11-20T09:00:00Z", 30_000, session=session)

    assert [dict(params)["maxAlternatives"] for _, params in session.calls] == [2, 0]


def test_main_route_retries_without_alternatives_after_a_timeout(raw):
    main = {**raw, "routes": raw["routes"][:1]}
    session = FakeSession(requests.Timeout("slow"), main, shifted(raw, 0.5), shifted(raw, -0.5))

    routes, warnings = tomtom.three_routes(ORIGIN, DEST, "2026-11-20T09:00:00Z", 30_000, session=session)

    assert len(routes) == 3
    assert any("timed out" in w for w in warnings)


def test_via_point_timeout_stops_the_top_up(raw):
    main = {**raw, "routes": raw["routes"][:1]}
    session = FakeSession(main, requests.Timeout("slow"))

    routes, warnings = tomtom.three_routes(ORIGIN, DEST, "2026-11-20T09:00:00Z", 30_000, session=session)

    assert len(routes) == 1
    assert len(session.calls) == 2  # no further detours attempted
    assert any("via-point route timed out" in w for w in warnings)


def test_three_routes_raises_when_tomtom_returns_nothing():
    session = FakeSession({"routes": [], "report": {}})

    with pytest.raises(tomtom.TomTomError, match="no route") as info:
        tomtom.three_routes(ORIGIN, DEST, "2026-11-20T09:00:00Z", 30_000, session=session)

    assert info.value.code == "NO_ROUTE_FOUND"


class ErrorResponse:
    ok = False
    status_code = 400
    text = "{}"

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def test_error_response_keeps_tomtoms_error_code():
    body = {"detailedError": {"code": "NO_ROUTE_FOUND", "message": "Cannot find a route"}}

    with pytest.raises(tomtom.TomTomError, match="Cannot find a route") as info:
        tomtom._raise_for(ErrorResponse(body))

    assert info.value.code == "NO_ROUTE_FOUND"


def test_error_response_without_detail_has_no_code():
    with pytest.raises(tomtom.TomTomError) as info:
        tomtom._raise_for(ErrorResponse({"error": {"description": "bad key"}}))

    assert info.value.code is None
