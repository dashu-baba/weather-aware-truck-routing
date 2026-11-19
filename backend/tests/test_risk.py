"""Exact hazard boundaries, strict load cutoffs and wind selection."""

import pytest

from routing import config
from routing.risk import (
    HIGH,
    LOW,
    MODERATE,
    NO_TRAVEL,
    RAIN_IN_HR,
    SEVERE,
    SNOW_IN_HR,
    WIND_MPH,
    classify,
    level_for,
    wind_value,
)


@pytest.fixture(autouse=True)
def sustained_wind(monkeypatch):
    monkeypatch.setattr(config, "WIND_METRIC", "sustained")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, LOW),
        (0, LOW),
        (24.9, LOW),
        (25, MODERATE),
        (34.9, MODERATE),
        (35, HIGH),
        (44.9, HIGH),
        (45, SEVERE),
        (54.9, SEVERE),
        (55, NO_TRAVEL),
        (80, NO_TRAVEL),
    ],
    ids=[
        "missing",
        "calm",
        "below-moderate",
        "moderate",
        "below-high",
        "high",
        "below-severe",
        "severe",
        "below-no-travel",
        "no-travel",
        "extreme",
    ],
)
def test_wind_boundaries(value, expected):
    assert level_for(value, WIND_MPH) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, LOW),
        (0.099, LOW),
        (0.10, MODERATE),
        (0.249, MODERATE),
        (0.25, HIGH),
        (0.499, HIGH),
        (0.50, SEVERE),
        (1.00, SEVERE),
        (1.001, NO_TRAVEL),
    ],
    ids=[
        "dry",
        "below-moderate",
        "moderate",
        "below-high",
        "high",
        "below-severe",
        "severe",
        "no-travel-boundary-exclusive",
        "no-travel",
    ],
)
def test_rain_boundaries(value, expected):
    assert level_for(value, RAIN_IN_HR) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.49, LOW),
        (0.5, MODERATE),
        (0.99, MODERATE),
        (1, HIGH),
        (1.99, HIGH),
        (2, SEVERE),
        (3, SEVERE),
        (3.01, NO_TRAVEL),
    ],
    ids=[
        "below-moderate",
        "moderate",
        "below-high",
        "high",
        "below-severe",
        "severe",
        "no-travel-boundary-exclusive",
        "no-travel",
    ],
)
def test_snow_boundaries(value, expected):
    assert level_for(value, SNOW_IN_HR) == expected


@pytest.mark.parametrize(
    ("wind", "load", "expected", "reason"),
    [
        (45, 0, SEVERE, None),
        (45, 30000, SEVERE, None),
        (45, 30001, NO_TRAVEL, ("No Travel", "30,000")),
        (54.9, 30001, NO_TRAVEL, ("No Travel", "30,000")),
        (35, 40000, HIGH, None),
        (35, 40001, SEVERE, ("Severe", "40,000")),
        (44.9, 60000, SEVERE, ("Severe", "40,000")),
        (34.9, 60000, MODERATE, None),
        (55, 0, NO_TRAVEL, None),
        (24.9, 60000, LOW, None),
    ],
    ids=[
        "severe-empty",
        "thirty-thousand-exact",
        "over-thirty-thousand",
        "severe-band-top",
        "forty-thousand-exact",
        "over-forty-thousand",
        "high-band-top",
        "moderate-heavy",
        "no-travel-empty",
        "low-heavy",
    ],
)
def test_load_rules(wind, load, expected, reason):
    result = classify({"wind_mph": wind, "rain_in": 0, "snow_in": 0}, load)
    assert result["risk"] == result["levels"]["wind"] == expected
    if reason:
        assert all(text in " ".join(result["reasons"]) for text in reason)


@pytest.mark.parametrize(
    ("hazard", "value", "expected"),
    [("rain", 0.6, SEVERE), ("snow", 1.5, HIGH)],
    ids=["rain-heavy-load", "snow-heavy-load"],
)
def test_load_does_not_escalate_precipitation(hazard, value, expected):
    result = classify({"wind_mph": 0, f"{hazard}_in": value}, 60000)
    assert result["risk"] == result["levels"][hazard] == expected
    assert result["levels"]["wind"] == LOW


@pytest.mark.parametrize(
    ("wind", "reason"),
    [(10, "High driven by rain"), (36, "High driven by wind, rain")],
    ids=["worst-hazard", "tied-hazards"],
)
def test_hazard_reasons(wind, reason):
    result = classify({"wind_mph": wind, "rain_in": 0.3, "snow_in": 0}, 0)
    assert result["risk"] == HIGH
    assert reason in result["reasons"]


def test_all_missing_is_low():
    result = classify(dict.fromkeys(["wind_mph", "gust_mph", "rain_in", "snow_in"]), 60000)
    assert result == {"risk": LOW, "levels": {"wind": LOW, "rain": LOW, "snow": LOW}, "reasons": []}


@pytest.mark.parametrize(
    ("metric", "wind", "gust", "expected"),
    [
        ("sustained", 20, 50, 20),
        ("gust", 20, 50, 50),
        ("gust", 20, None, 20),
        ("max", 20, 50, 50),
        ("max", 50, 20, 50),
        ("max", None, 20, 20),
        ("max", 20, None, 20),
        ("max", None, None, None),
    ],
    ids=[
        "sustained",
        "gust",
        "gust-fallback",
        "max-gust",
        "max-sustained",
        "max-missing-wind",
        "max-missing-gust",
        "max-both-missing",
    ],
)
def test_wind_metric(monkeypatch, metric, wind, gust, expected):
    monkeypatch.setattr(config, "WIND_METRIC", metric)
    assert wind_value({"wind_mph": wind, "gust_mph": gust}) == expected


def test_sustained_ignores_strong_gust_for_heavy_load():
    assert classify({"wind_mph": 20, "gust_mph": 50, "rain_in": 0, "snow_in": 0}, 60000)["risk"] == LOW
