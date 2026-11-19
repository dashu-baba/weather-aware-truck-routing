from unittest import mock

HITS = [{"label": "Dallas, TX", "lat": 32.77, "lon": -96.79, "type": "Geography"}]


def test_geocode_is_limited_to_60_per_minute(api):
    with mock.patch("planner.views.tomtom.geocode", return_value=HITS):
        statuses = [api.get("/api/geocode", {"q": "Dallas"}).status_code for _ in range(61)]
    assert statuses[:60] == [200] * 60
    assert statuses[60] == 429


def test_health_is_not_throttled(api):
    assert all(api.get("/api/health").status_code == 200 for _ in range(70))
