"""Total rain includes convective showers and invalidates incomplete disk caches."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from routing import config
from routing.openmeteo import HOURLY_VARS, OpenMeteoProvider, WeatherStore, hour_str, weather_key
from routing.risk import HIGH, MODERATE, classify

START = datetime(2026, 11, 20, 8, tzinfo=timezone.utc)
END = START + timedelta(hours=1)
KEY = weather_key(35, -100)
MISSING = object()


def series(rain=0.2, showers=0.15):
    data = {name: [0] for name in HOURLY_VARS}
    data["time"] = [hour_str(START)]
    for name, value in [("rain", rain), ("showers", showers)]:
        if value is MISSING:
            data.pop(name)
        else:
            data[name] = [value]
    return data


@pytest.mark.parametrize(
    ("rain", "showers", "total"),
    [
        (0.2, 0.15, 0.35),
        (None, 0.3, 0.3),
        (0.2, None, 0.2),
        (None, None, None),
        (0.2, MISSING, 0.2),
        (MISSING, 0.3, 0.3),
        (MISSING, MISSING, None),
        (0, 0, 0),
    ],
    ids=[
        "combined",
        "showers-only",
        "rain-only",
        "both-null",
        "old-series",
        "missing-rain",
        "both-missing",
        "dry",
    ],
)
def test_total_rain(rain, showers, total):
    store = WeatherStore(None)
    store.series[KEY] = series(rain, showers)
    weather = store.at(*KEY, START)
    if total is None:
        assert weather["rain_in"] is None
    else:
        assert weather["rain_in"] == pytest.approx(total)


def test_showers_raise_rain_risk(monkeypatch):
    monkeypatch.setattr(config, "WIND_METRIC", "sustained")
    store = WeatherStore(None)
    store.series[KEY] = series()
    weather = store.at(*KEY, START)
    assert classify(weather, 0)["risk"] == HIGH
    assert classify({**weather, "rain_in": 0.2}, 0)["risk"] == MODERATE


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


def test_provider_requests_showers():
    http = HTTP()
    result = OpenMeteoProvider(session=http).fetch([KEY], START, END)
    assert "showers" in http.params[0]["hourly"].split(",")
    assert result[KEY]["showers"] == [0.15]


def test_old_cache_is_ignored_and_refetched(tmp_path):
    http = HTTP()
    store = WeatherStore(OpenMeteoProvider(session=http), cache_dir=tmp_path)
    path = store._path(KEY, START, END)
    path.write_text(json.dumps(series(showers=MISSING)))
    assert store._load_cache([KEY], START, END) == {}
    store.prefetch([KEY], START, END)
    assert len(http.params) == store.calls == 1
    assert store.at(*KEY, START)["rain_in"] == pytest.approx(0.35)
    assert json.loads(path.read_text())["showers"] == [0.15]
    # A fresh store reuses the replacement file without spending another location call.
    cached = WeatherStore(OpenMeteoProvider(session=http), cache_dir=tmp_path)
    cached.prefetch([KEY], START, END)
    assert len(http.params) == 1
    assert cached.calls == 0
