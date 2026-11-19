"""Planning pipeline: prepare -> fetch_weather -> score_plan, and plan() as their composition.

Runs on the real multi-leg TomTom route in tests/fixtures with a deterministic fake forecast.
"""

import copy
import dataclasses
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from routing import config, tomtom
from routing.openmeteo import WeatherStore
from routing.pipeline import PreparedPlan, fetch_weather, plan, prepare, route_entry, score_plan

FIXTURE = Path(__file__).parent / "fixtures" / "tomtom_multi_leg.json"
ORIGIN = {"label": "A", "lat": 32.7767, "lon": -96.797}
DEST = {"label": "B", "lat": 33.749, "lon": -84.388}
DEPARTURE = datetime(2026, 11, 20, 8, 30, tzinfo=timezone.utc)
LIGHT, HEAVY = 30_000, 60_000


class FakeProvider:
    """Deterministic forecast with a few missing values. Counts the locations it was asked for."""

    def __init__(self, empty=False):
        self.empty = empty
        self.locations = 0

    def fetch(self, keys, start, end):
        self.locations += len(keys)
        if self.empty:
            return {k: {} for k in keys}
        hours = int((end - start).total_seconds() // 3600) + 1
        times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00") for h in range(hours)]
        out = {}
        for lat, lon in keys:
            seed = lat * 7 + lon * 3
            wind = [round(abs(math.sin(seed + h * 0.3)) * 45, 1) for h in range(hours)]
            rain = [round(max(0.0, math.sin(seed * 2 + h * 0.2)) * 0.2, 3) for h in range(hours)]
            snow = [round(max(0.0, math.sin(seed * 3 + h * 0.1)) * 0.15, 3) for h in range(hours)]
            for h in range(hours):
                if (h + int(abs(lat * 10))) % 97 == 0:
                    rain[h] = None
            out[(lat, lon)] = {
                "time": times,
                "wind_speed_10m": wind,
                "wind_gusts_10m": [round(w * 1.4, 1) for w in wind],
                "wind_direction_10m": [(int(seed * 10) + h * 7) % 360 for h in range(hours)],
                "rain": rain,
                "snowfall": snow,
            }
        return out


def route_source(origin, dest, depart_iso, load_lb):
    """Three routes from the real fixture: the original and two copies shifted north and south."""
    main = tomtom.parse_route(json.loads(FIXTURE.read_text())["routes"][0])
    north = dataclasses.replace(
        main,
        points=[(la + 0.4, lo) for la, lo in main.points],
        source="tomtom-via",
        duration_s=main.duration_s * 1.1,
    )
    south = dataclasses.replace(
        main,
        points=[(la - 0.4, lo) for la, lo in main.points],
        source="tomtom-via",
        duration_s=main.duration_s * 1.2,
    )
    return [main, north, south], ["synthetic route warning"]


def without_timestamp(result):
    result = copy.deepcopy(result)
    result["meta"].pop("generated_at")
    return result


def full_plan(load_lb, provider=None):
    store = WeatherStore(provider or FakeProvider())
    return plan(ORIGIN, DEST, DEPARTURE, load_lb, route_source, store)


def prepared_plan(load_lb=LIGHT):
    return prepare(ORIGIN, DEST, DEPARTURE, load_lb, route_source)


# --- the split ----------------------------------------------------------------------------------


def test_plan_is_prepare_then_fetch_then_score():
    prepared = prepared_plan()
    store = WeatherStore(FakeProvider())
    fetch_weather(prepared, store)

    composed = score_plan(prepared, store, LIGHT)

    assert without_timestamp(composed) == without_timestamp(full_plan(LIGHT))


def test_one_prepared_plan_scores_any_load_like_a_separate_plan():
    provider = FakeProvider()
    store = WeatherStore(provider)
    prepared = prepared_plan()
    fetch_weather(prepared, store)

    light = score_plan(prepared, store, LIGHT)
    heavy = score_plan(prepared, store, HEAVY)

    assert without_timestamp(light) == without_timestamp(full_plan(LIGHT))
    assert without_timestamp(heavy) == without_timestamp(full_plan(HEAVY))


def test_scoring_another_load_makes_no_weather_calls():
    provider = FakeProvider()
    store = WeatherStore(provider)
    prepared = prepared_plan()
    fetch_weather(prepared, store)
    fetched = (provider.locations, store.calls)

    score_plan(prepared, store, LIGHT)
    score_plan(prepared, store, HEAVY)

    assert (provider.locations, store.calls) == fetched


def test_scoring_leaves_the_prepared_plan_untouched():
    store = WeatherStore(FakeProvider())
    prepared = prepared_plan()
    fetch_weather(prepared, store)
    before = copy.deepcopy([pr.checkpoints for pr in prepared.routes])

    score_plan(prepared, store, HEAVY)

    assert [pr.checkpoints for pr in prepared.routes] == before
    scored_keys = {"weather", "risk", "levels", "reasons", "risk_label"}
    assert not any(
        scored_keys & set(c) for pr in prepared.routes for cps in pr.checkpoints.values() for c in cps
    )


def test_prepare_does_not_depend_on_the_load():
    light, heavy = prepared_plan(LIGHT), prepared_plan(HEAVY)

    assert light.checkpoint_points() == heavy.checkpoint_points()
    assert light.cells == heavy.cells
    assert (light.start, light.end) == (heavy.start, heavy.end)


def test_fetch_weather_asks_for_every_checkpoint_and_cell_once():
    provider = FakeProvider()
    store = WeatherStore(provider)
    prepared = prepared_plan()

    fetch_weather(prepared, store)

    wanted = {(round(la, 1), round(lo, 1)) for la, lo in prepared.checkpoint_points() + prepared.cells}
    assert provider.locations == len(wanted) == store.calls
    fetch_weather(prepared, store)  # already in the store: nothing new is requested
    assert provider.locations == len(wanted)


def test_checkpoint_points_can_be_limited_to_some_intervals():
    prepared = prepared_plan()

    every = prepared.checkpoint_points()
    only_25 = prepared.checkpoint_points((25,))

    assert len(every) == sum(len(prepared.checkpoint_points((iv,))) for iv in prepared.intervals)
    assert 0 < len(only_25) < len(every)
    assert set(only_25) <= set(every)


def test_forecast_window_covers_the_departure_hour_and_the_last_arrival():
    prepared = prepared_plan()

    assert isinstance(prepared, PreparedPlan)
    assert prepared.start == DEPARTURE.replace(minute=0)
    assert prepared.end - prepared.start >= timedelta(hours=config.HEATMAP_HOURS)


# --- scoring what has arrived so far ------------------------------------------------------------


def fetched_plan():
    prepared = prepared_plan()
    store = WeatherStore(FakeProvider())
    fetch_weather(prepared, store)
    return prepared, store


def test_route_entry_needs_no_weather_and_matches_the_scored_route():
    prepared = prepared_plan()
    scored = full_plan(LIGHT)["routes"]

    for pr, scored_route in zip(prepared.routes, scored, strict=True):
        entry = route_entry(prepared, pr)
        assert {key: scored_route[key] for key in entry} == entry
        assert "by_interval" not in entry


def test_the_heatmap_can_be_left_out_without_changing_anything_else():
    prepared, store = fetched_plan()

    with_heatmap = score_plan(prepared, store, LIGHT)
    without = score_plan(prepared, store, LIGHT, include_heatmap=False)

    assert "heatmap" not in without
    rest = {key: value for key, value in with_heatmap.items() if key != "heatmap"}
    assert without_timestamp(rest) == without_timestamp(without)


def test_a_restricted_plan_scores_only_its_intervals_exactly_like_the_full_plan():
    prepared, store = fetched_plan()
    full = score_plan(prepared, store, LIGHT, include_heatmap=False)

    part = score_plan(prepared.restricted((25,)), store, LIGHT, include_heatmap=False)

    assert set(part["recommendation"]) == {"25"}
    assert part["meta"]["intervals"] == [25]
    assert all(set(r["by_interval"]) == {"25"} for r in part["routes"])
    assert part["recommendation"]["25"] == full["recommendation"]["25"]
    assert [r["by_interval"]["25"] for r in part["routes"]] == [
        r["by_interval"]["25"] for r in full["routes"]
    ]


def test_restricting_a_plan_leaves_the_original_whole():
    prepared = prepared_plan()

    prepared.restricted((25,))

    assert prepared.intervals == (10, 25, 50)
    assert all(set(pr.checkpoints) == {10, 25, 50} for pr in prepared.routes)


# --- what the load changes ----------------------------------------------------------------------


def test_heavier_load_raises_risk_without_lowering_it():
    light, heavy = full_plan(LIGHT), full_plan(HEAVY)

    pairs = [
        (a["risk"], b["risk"])
        for ra, rb in zip(light["routes"], heavy["routes"], strict=True)
        for iv in ra["by_interval"]
        for a, b in zip(
            ra["by_interval"][iv]["checkpoints"], rb["by_interval"][iv]["checkpoints"], strict=True
        )
    ]
    assert all(b >= a for a, b in pairs)
    assert any(b > a for a, b in pairs)
    assert light["heatmap"]["vars"]["risk"] != heavy["heatmap"]["vars"]["risk"]


def test_load_does_not_change_geometry_or_weather_values():
    light, heavy = full_plan(LIGHT), full_plan(HEAVY)

    assert [r["geometry"] for r in light["routes"]] == [r["geometry"] for r in heavy["routes"]]
    for name in ("wind", "gust", "rain", "snow", "u", "v"):
        assert light["heatmap"]["vars"][name] == heavy["heatmap"]["vars"][name]


def test_overweight_warning_depends_on_the_load():
    light, heavy = full_plan(LIGHT), full_plan(HEAVY)

    assert not any("federal limit" in w for w in light["meta"]["warnings"])
    assert any("95,000 lb exceeds" in w for w in heavy["meta"]["warnings"])
    assert "synthetic route warning" in light["meta"]["warnings"]
    assert heavy["meta"]["load_lb"] == HEAVY


# --- result shape and edge cases ----------------------------------------------------------------


def test_result_has_routes_recommendations_and_a_48_hour_heatmap():
    result = full_plan(LIGHT)

    assert [r["id"] for r in result["routes"]] == ["A", "B", "C"]
    assert set(result["recommendation"]) == {"10", "25", "50"}
    assert all(rec["best"] in {"A", "B", "C"} for rec in result["recommendation"].values())
    heat = result["heatmap"]
    assert heat["mode"] == "hull"
    assert set(heat["vars"]) == {"risk", "wind", "gust", "rain", "snow", "u", "v"}
    assert all(len(layer) == config.HEATMAP_HOURS for layer in heat["vars"].values())


def test_missing_forecast_is_scored_low_with_a_warning():
    result = full_plan(LIGHT, FakeProvider(empty=True))

    warning = next(w for w in result["meta"]["warnings"] if "had no forecast" in w)
    assert "scored Low" in warning
    checkpoints = [
        c for r in result["routes"] for cps in r["by_interval"].values() for c in cps["checkpoints"]
    ]
    assert all(c["risk"] == 0 and c["weather"] is None for c in checkpoints)


def test_naive_departure_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        prepare(ORIGIN, DEST, datetime(2026, 11, 20, 8), LIGHT, route_source)


def test_unknown_corridor_mode_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "CORRIDOR_MODE", "mystery")

    with pytest.raises(ValueError, match="CORRIDOR_MODE"):
        prepared_plan()


def test_band_mode_still_produces_a_cell_major_heatmap(monkeypatch):
    monkeypatch.setattr(config, "CORRIDOR_MODE", "band")

    heat = full_plan(LIGHT)["heatmap"]

    assert {"cells", "risk", "wind", "rain", "snow", "step_deg"} <= set(heat)
    assert len(heat["risk"]) == len(heat["cells"]) > 0


def test_no_routes_gives_an_empty_plan_instead_of_crashing():
    store = WeatherStore(FakeProvider())

    result = plan(ORIGIN, DEST, DEPARTURE, LIGHT, lambda *args: ([], []), store)

    assert result["routes"] == []
    assert all(rec["best"] is None for rec in result["recommendation"].values())
