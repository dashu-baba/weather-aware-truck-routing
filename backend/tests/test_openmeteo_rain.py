"""Rain is the liquid part of total precipitation; incomplete disk caches are refetched."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from routing import config
from routing.openmeteo import HOURLY_VARS, OpenMeteoProvider, WeatherStore, hour_str, liquid_rain, weather_key
from routing.risk import HIGH, LOW, MODERATE, classify

START = datetime(2026, 11, 20, 8, tzinfo=timezone.utc)
END = START + timedelta(hours=1)
KEY = weather_key(35, -100)
MISSING = object()


def series(precipitation=0.35, rain=0.2, snowfall=0.0, showers=MISSING):
    data = {name: [0] for name in HOURLY_VARS}
    data["time"] = [hour_str(START)]
    for name, value in [
        ("precipitation", precipitation),
        ("rain", rain),
        ("snowfall", snowfall),
        ("showers", showers),
    ]:
        if value is MISSING:
            data.pop(name, None)
        else:
            data[name] = [value]
    return data


@pytest.mark.parametrize(
    ("precip", "rain", "snow", "expected"),
    [
        (0.35, 0.20, 0.0, 0.35),
        (0.50, 0.10, 2.1, 0.20),
        (0.30, 0.0, 2.1, 0.0),
        (0.30, 0.0, 2.8, 0.0),
        (0.30, 0.0, None, 0.30),
        (None, 0.2, 0.0, 0.2),
        (None, None, None, None),
        (0.0, 0.0, 0.0, 0.0),
    ],
    ids=[
        "thunderstorm-showers-count",
        "rain-and-snow-split",
        "pure-snow-is-not-rain",
        "never-negative",
        "unknown-snow-counts-as-zero",
        "no-precipitation-falls-back-to-rain",
        "all-unknown",
        "dry",
    ],
)
def test_liquid_rain(precip, rain, snow, expected):
    result = liquid_rain(precip, rain, snow)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_store_reports_liquid_rain_and_snow_depth():
    store = WeatherStore(None)
    store.series[KEY] = series(precipitation=0.5, rain=0.1, snowfall=2.1)
    weather = store.at(*KEY, START)
    assert weather["rain_in"] == pytest.approx(0.2)
    assert weather["snow_in"] == 2.1


@pytest.mark.parametrize(
    ("rain", "showers", "expected"),
    [(0.2, 0.15, 0.35), (0.2, MISSING, 0.2), (None, None, None)],
    ids=["rain-plus-showers", "rain-only", "unknown"],
)
def test_series_without_precipitation_falls_back(rain, showers, expected):
    store = WeatherStore(None)
    store.series[KEY] = series(precipitation=MISSING, rain=rain, showers=showers)
    weather = store.at(*KEY, START)
    if expected is None:
        assert weather["rain_in"] is None
    else:
        assert weather["rain_in"] == pytest.approx(expected)


def test_thunderstorm_showers_raise_rain_risk(monkeypatch):
    monkeypatch.setattr(config, "WIND_METRIC", "sustained")
    store = WeatherStore(None)
    store.series[KEY] = series(precipitation=0.35, rain=0.2)
    weather = store.at(*KEY, START)
    assert classify(weather, 0)["risk"] == HIGH
    assert classify({**weather, "rain_in": 0.2}, 0)["risk"] == MODERATE


def test_snow_does_not_become_rain(monkeypatch):
    monkeypatch.setattr(config, "WIND_METRIC", "sustained")
    store = WeatherStore(None)
    store.series[KEY] = series(precipitation=1.5 / 7, rain=0.0, snowfall=1.5)
    result = classify(store.at(*KEY, START), 0)
    assert result["levels"]["snow"] == HIGH
    assert result["levels"]["rain"] == LOW


class Response:
    ok = True
    status_code = 200
    headers = {}

    def json(self):
        return {"hourly": series()}


class HTTP:
    def __init__(self):
        self.params = []

    def get(self, url, params, timeout):
        self.params.append(params)
        return Response()


def test_provider_requests_precipitation():
    http = HTTP()
    result = OpenMeteoProvider(session=http).fetch([KEY], START, END)
    hourly = http.params[0]["hourly"].split(",")
    assert {"precipitation", "rain", "snowfall"} <= set(hourly)
    assert result[KEY]["precipitation"] == [0.35]


def test_old_cache_is_ignored_and_refetched(tmp_path):
    http = HTTP()
    store = WeatherStore(OpenMeteoProvider(session=http), cache_dir=tmp_path)
    path = store._path(KEY, START, END)
    path.write_text(json.dumps(series(precipitation=MISSING, showers=0.15)))
    assert store._load_cache([KEY], START, END) == {}
    store.prefetch([KEY], START, END)
    assert len(http.params) == store.calls == 1
    assert store.at(*KEY, START)["rain_in"] == pytest.approx(0.35)
    assert json.loads(path.read_text())["precipitation"] == [0.35]
    # A fresh store reuses the replacement file without spending another location call.
    cached = WeatherStore(OpenMeteoProvider(session=http), cache_dir=tmp_path)
    cached.prefetch([KEY], START, END)
    assert len(http.params) == 1
    assert cached.calls == 0
