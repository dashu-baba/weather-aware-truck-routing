"""POST /api/plan: validation, caching and upstream error mapping (pipeline mocked)."""

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
import requests

from routing import tomtom
from routing.openmeteo import RateLimited

URL = "/api/plan"
RESULT = {"routes": [{"id": "A"}]}


def body(**overrides):
    data = {
        "origin": {"label": "Dallas", "lat": 32.7767, "lon": -96.797},
        "destination": {"label": "Fort Worth", "lat": 32.7555, "lon": -97.3308},
        "departure": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "load_lb": 30_000,
    }
    data.update(overrides)
    return data


@pytest.fixture
def pipeline():
    with mock.patch("planner.services.build_plan", return_value=RESULT) as patched:
        yield patched


def test_valid_request_returns_the_plan(api, pipeline):
    response = api.post(URL, body(), format="json")

    assert response.status_code == 200
    assert response.json() == RESULT
    assert pipeline.call_count == 1


def test_identical_request_is_served_from_cache(api, pipeline):
    payload = body()

    api.post(URL, payload, format="json")
    second = api.post(URL, payload, format="json")

    assert second.json() == RESULT
    assert pipeline.call_count == 1


def test_unknown_fields_do_not_bypass_the_cache(api, pipeline):
    payload = body()

    api.post(URL, payload, format="json")
    api.post(URL, {**payload, "junk": 1}, format="json")

    assert pipeline.call_count == 1


@pytest.mark.parametrize(
    ("exc", "status_code"),
    [
        (RateLimited("busy"), 503),
        (requests.Timeout("slow"), 504),
        (requests.ConnectionError("https://example.test?key=SECRET"), 502),
        (tomtom.TomTomError("NO_ROUTE_FOUND"), 502),
        (RuntimeError("boom"), 502),
    ],
)
def test_upstream_failures_map_to_status_codes(api, exc, status_code):
    with mock.patch("planner.services.build_plan", side_effect=exc):
        response = api.post(URL, body(), format="json")

    assert response.status_code == status_code
    assert response.json().keys() == {"detail"}
    assert "SECRET" not in response.content.decode()


def test_failures_are_not_cached(api):
    with mock.patch("planner.services.build_plan", side_effect=[tomtom.TomTomError("x"), RESULT]):
        first = api.post(URL, body(), format="json")
        second = api.post(URL, body(), format="json")

    assert (first.status_code, second.status_code) == (502, 200)


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"load_lb": -1}, "load_lb"),
        ({"load_lb": 60_001}, "load_lb"),
        ({"load_lb": None}, "load_lb"),
        ({"origin": {"lat": 91, "lon": 0}}, "origin"),
        ({"origin": {"lat": 0, "lon": 181}}, "origin"),
        ({"origin": "Dallas"}, "origin"),
        ({"departure": "tomorrow"}, "departure"),
        ({"departure": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}, "departure"),
        ({"departure": (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()}, "departure"),
        ({"destination": {"lat": 32.7767, "lon": -96.797}}, "non_field_errors"),
    ],
)
def test_invalid_input_is_rejected_before_any_upstream_call(api, pipeline, overrides, field):
    response = api.post(URL, body(**overrides), format="json")

    assert response.status_code == 400
    assert field in response.json()
    pipeline.assert_not_called()


@pytest.mark.parametrize("payload", [{}, [1, 2], None])
def test_non_object_or_empty_bodies_are_rejected(api, pipeline, payload):
    response = api.post(URL, payload, format="json")

    assert response.status_code == 400
    pipeline.assert_not_called()


def test_only_post_is_allowed(api):
    assert api.get(URL).status_code == 405


def test_plan_is_throttled_to_six_per_minute(api, pipeline):
    codes = [api.post(URL, body(load_lb=1000 + i), format="json").status_code for i in range(8)]

    assert codes == [200] * 6 + [429] * 2
