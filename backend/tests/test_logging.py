import logging
from unittest import mock

import requests

from routing import tomtom
from tests.conftest import TEST_API_KEY

PATCH_TARGET = "planner.views.tomtom.geocode"


def test_tomtom_error_is_logged_at_error_level(api, app_logs):
    with mock.patch(PATCH_TARGET, side_effect=tomtom.TomTomError("quota exceeded")):
        api.get("/api/geocode", {"q": "Dallas"})
    records = [r for r in app_logs.records if r.name == "planner.views"]
    assert any(r.levelno == logging.ERROR and "quota exceeded" in r.getMessage() for r in records)


def test_request_exception_logs_only_the_type_not_the_api_key(api, app_logs):
    error = requests.ConnectionError(f"https://api.tomtom.com/search?key={TEST_API_KEY}")
    with mock.patch(PATCH_TARGET, side_effect=error):
        api.get("/api/geocode", {"q": "Dallas"})
    assert "ConnectionError" in app_logs.text
    assert TEST_API_KEY not in app_logs.text


def test_success_and_cache_hit_are_logged(api, app_logs):
    with mock.patch(PATCH_TARGET, return_value=[{"label": "x", "lat": 1, "lon": 2, "type": "t"}]):
        api.get("/api/geocode", {"q": "Dallas"})
        api.get("/api/geocode", {"q": "Dallas"})
    assert "geocode ok: 1 result(s)" in app_logs.text
    assert "geocode cache hit" in app_logs.text


def test_logging_config_keeps_urllib3_quiet_and_sets_app_level():
    from config.logging_config import build_logging

    cfg = build_logging("WARNING")
    assert cfg["loggers"]["planner"]["level"] == "WARNING"
    assert cfg["loggers"]["routing"]["level"] == "WARNING"
    assert cfg["loggers"]["urllib3"]["level"] == "WARNING"
