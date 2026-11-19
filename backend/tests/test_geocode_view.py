from unittest import mock

import pytest
import requests

from routing import tomtom

HITS = [{"label": "Dallas, TX", "lat": 32.77, "lon": -96.79, "type": "Geography"}]
PATCH_TARGET = "planner.views.tomtom.geocode"


@pytest.mark.parametrize("q", ["", "  ", "ab", " a "])
def test_short_query_is_rejected(api, q):
    with mock.patch(PATCH_TARGET) as geocode:
        response = api.get("/api/geocode", {"q": q})
    assert response.status_code == 400
    assert "3 characters" in response.json()["detail"]
    geocode.assert_not_called()


def test_missing_query_is_rejected(api):
    assert api.get("/api/geocode").status_code == 400


def test_success_returns_hits(api):
    with mock.patch(PATCH_TARGET, return_value=HITS) as geocode:
        response = api.get("/api/geocode", {"q": "Dallas"})
    assert response.status_code == 200
    assert response.json() == HITS
    geocode.assert_called_once_with("Dallas", typeahead=False, limit=5)


def test_typeahead_flag_is_passed_through(api):
    with mock.patch(PATCH_TARGET, return_value=HITS) as geocode:
        api.get("/api/geocode", {"q": "Dallas", "typeahead": "true"})
    assert geocode.call_args.kwargs["typeahead"] is True


def test_repeat_request_is_served_from_cache(api):
    with mock.patch(PATCH_TARGET, return_value=HITS) as geocode:
        first = api.get("/api/geocode", {"q": "Dallas"})
        second = api.get("/api/geocode", {"q": "Dallas"})
    assert first.json() == second.json() == HITS
    assert geocode.call_count == 1


def test_cache_ignores_query_case_and_whitespace(api):
    with mock.patch(PATCH_TARGET, return_value=HITS) as geocode:
        api.get("/api/geocode", {"q": "Dallas"})
        api.get("/api/geocode", {"q": "  dallas "})
    assert geocode.call_count == 1


def test_typeahead_is_part_of_the_cache_key(api):
    with mock.patch(PATCH_TARGET, return_value=HITS) as geocode:
        api.get("/api/geocode", {"q": "Dallas"})
        api.get("/api/geocode", {"q": "Dallas", "typeahead": "true"})
    assert geocode.call_count == 2


@pytest.mark.parametrize(
    "error", [tomtom.TomTomError("boom"), requests.ConnectionError("down"), requests.Timeout("slow")]
)
def test_upstream_errors_become_502(api, error):
    with mock.patch(PATCH_TARGET, side_effect=error):
        response = api.get("/api/geocode", {"q": "Dallas"})
    assert response.status_code == 502
    assert response.json() == {"detail": "Geocoding service failed."}


def test_failures_are_not_cached(api):
    with mock.patch(PATCH_TARGET, side_effect=[tomtom.TomTomError("boom"), HITS]) as geocode:
        assert api.get("/api/geocode", {"q": "Dallas"}).status_code == 502
        assert api.get("/api/geocode", {"q": "Dallas"}).status_code == 200
    assert geocode.call_count == 2
