"""GET /api/reverse: the label for a point picked on the map."""

import math
from unittest import mock

import pytest
import requests

from routing import tomtom
from tests.conftest import TEST_API_KEY

PATCH_TARGET = "planner.views.tomtom.reverse_geocode"
FOUND = {"label": "1400 Young Street, Dallas, TX 75201", "country": "US"}
URL = "/api/reverse"


def ask(api, lat="32.7767", lon="-96.797"):
    return api.get(URL, {"lat": lat, "lon": lon})


def test_a_point_with_an_address_returns_its_label_and_country(api):
    with mock.patch(PATCH_TARGET, return_value=FOUND) as reverse:
        response = ask(api)

    assert response.status_code == 200
    assert response.json() == {
        "label": "1400 Young Street, Dallas, TX 75201",
        "lat": 32.7767,
        "lon": -96.797,
        "country": "US",
        "found": True,
    }
    reverse.assert_called_once_with(32.7767, -96.797)


def test_a_point_with_nothing_there_falls_back_to_its_coordinates(api):
    with mock.patch(PATCH_TARGET, return_value=None):
        response = ask(api, "0", "0")

    assert response.status_code == 200
    assert response.json() == {
        "label": "0.0000, 0.0000",
        "lat": 0.0,
        "lon": 0.0,
        "country": None,
        "found": False,
    }


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (None, "-96.8"),
        ("32.8", None),
        ("", "-96.8"),
        ("north", "-96.8"),
        ("32.8", "1,5"),
        ("90.0001", "0"),
        ("-91", "0"),
        ("0", "180.5"),
        ("0", "-181"),
        ("nan", "0"),
        ("0", "inf"),
        ("1e309", "0"),
    ],
)
def test_bad_coordinates_are_rejected_before_any_upstream_call(api, lat, lon):
    params = {k: v for k, v in {"lat": lat, "lon": lon}.items() if v is not None}
    with mock.patch(PATCH_TARGET) as reverse:
        response = api.get(URL, params)

    assert response.status_code == 400
    assert set(response.json()) == {"detail"}
    reverse.assert_not_called()


def test_the_edges_of_the_valid_range_are_accepted(api):
    with mock.patch(PATCH_TARGET, return_value=None):
        assert ask(api, "90", "180").status_code == 200
        assert ask(api, "-90", "-180").status_code == 200


def test_a_repeat_request_and_a_point_a_few_metres_away_are_served_from_the_cache(api):
    with mock.patch(PATCH_TARGET, return_value=FOUND) as reverse:
        first = ask(api, "32.77670", "-96.79700")
        same = ask(api, "32.7767", "-96.797")
        nearby = ask(api, "32.776704", "-96.797004")  # under 1 m away: same 4-decimal cell

    assert first.json() == same.json()
    assert nearby.json()["label"] == FOUND["label"]
    assert reverse.call_count == 1


def test_a_point_in_another_cell_asks_again_and_keeps_its_own_coordinates(api):
    with mock.patch(PATCH_TARGET, return_value=FOUND) as reverse:
        ask(api, "32.7767", "-96.797")
        other = ask(api, "32.7769", "-96.797")

    assert reverse.call_count == 2
    assert other.json()["lat"] == 32.7769  # the point the user chose, not a snapped one


def test_a_missing_address_is_cached_too(api):
    with mock.patch(PATCH_TARGET, return_value=None) as reverse:
        ask(api, "0", "0")
        ask(api, "0", "0")

    assert reverse.call_count == 1


@pytest.mark.parametrize(
    "error", [tomtom.TomTomError("boom"), requests.ConnectionError("down"), requests.Timeout("slow")]
)
def test_upstream_errors_become_a_generic_502(api, error):
    with mock.patch(PATCH_TARGET, side_effect=error):
        response = ask(api)

    assert response.status_code == 502
    assert response.json() == {"detail": "Geocoding service failed."}


def test_failures_are_not_cached(api):
    with mock.patch(PATCH_TARGET, side_effect=[tomtom.TomTomError("boom"), FOUND]) as reverse:
        assert ask(api).status_code == 502
        assert ask(api).status_code == 200
    assert reverse.call_count == 2


def test_the_api_key_never_reaches_the_response_or_the_log(api, app_logs):
    leaky = requests.ConnectionError(f"https://api.tomtom.com/x?key={TEST_API_KEY}")
    with mock.patch(PATCH_TARGET, side_effect=leaky):
        response = ask(api)

    assert TEST_API_KEY not in response.content.decode()
    assert TEST_API_KEY not in app_logs.text


def test_a_tiny_negative_coordinate_does_not_print_as_negative_zero(api):
    with mock.patch(PATCH_TARGET, return_value=None):
        body = ask(api, "1e-7", "-1e-7").json()

    assert not math.isnan(body["lat"])
    assert body["label"] == "0.0000, 0.0000"


def test_reverse_is_limited_to_60_per_minute_separately_from_search(api):
    with (
        mock.patch(PATCH_TARGET, return_value=FOUND),
        mock.patch("planner.views.tomtom.geocode", return_value=[]),
    ):
        for _ in range(60):
            assert api.get("/api/geocode", {"q": "Dallas"}).status_code == 200
        statuses = [ask(api, f"32.{i:04d}", "-96.8").status_code for i in range(61)]

    assert statuses[:60] == [200] * 60  # 60 searches did not use up the map-pick budget
    assert statuses[60] == 429
