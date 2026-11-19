"""Job and plan keys: what two requests must have in common to share a weather job or a whole plan."""

from datetime import datetime, timedelta, timezone

import pytest

from planner.trips import departure_hour, job_key, plan_key

DALLAS = {"lat": 32.7767, "lon": -96.797}
ATLANTA = {"lat": 33.749, "lon": -84.388}
EIGHT = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)


def test_job_key_ignores_the_load_but_plan_key_does_not():
    assert job_key(DALLAS, ATLANTA, EIGHT) == job_key(DALLAS, ATLANTA, EIGHT)
    assert plan_key(DALLAS, ATLANTA, EIGHT, 30_000) != plan_key(DALLAS, ATLANTA, EIGHT, 31_000)
    assert plan_key(DALLAS, ATLANTA, EIGHT, 30_000).startswith(job_key(DALLAS, ATLANTA, EIGHT))


def test_minutes_of_the_departure_do_not_matter_but_the_hour_does():
    assert job_key(DALLAS, ATLANTA, EIGHT + timedelta(minutes=5)) == job_key(
        DALLAS, ATLANTA, EIGHT + timedelta(minutes=59, seconds=59)
    )
    assert job_key(DALLAS, ATLANTA, EIGHT) != job_key(DALLAS, ATLANTA, EIGHT + timedelta(hours=1))


def test_the_plan_key_follows_the_departure_minute_but_the_job_key_does_not():
    """ETAs and routes depend on the exact minute, so two minutes are two plans. The forecast is hourly."""
    early, late = EIGHT + timedelta(minutes=5), EIGHT + timedelta(minutes=55)

    assert plan_key(DALLAS, ATLANTA, early, 30_000) != plan_key(DALLAS, ATLANTA, late, 30_000)
    assert job_key(DALLAS, ATLANTA, early) == job_key(DALLAS, ATLANTA, late)  # one weather download
    assert plan_key(DALLAS, ATLANTA, early, 30_000).startswith(job_key(DALLAS, ATLANTA, early))


def test_seconds_of_the_departure_do_not_make_a_new_plan():
    base = EIGHT + timedelta(minutes=5)

    assert plan_key(DALLAS, ATLANTA, base, 30_000) == plan_key(
        DALLAS, ATLANTA, base + timedelta(seconds=59, microseconds=999), 30_000
    )


def test_the_plan_key_minute_is_read_in_utc_so_half_hour_zones_match():
    india = timezone(timedelta(hours=5, minutes=30))  # 13:35 in India is 08:05 UTC

    assert plan_key(DALLAS, ATLANTA, datetime(2026, 11, 20, 13, 35, tzinfo=india), 30_000) == plan_key(
        DALLAS, ATLANTA, EIGHT + timedelta(minutes=5), 30_000
    )


def test_departure_is_compared_in_utc():
    eastern = timezone(timedelta(hours=-5))

    assert job_key(DALLAS, ATLANTA, datetime(2026, 11, 20, 3, 30, tzinfo=eastern)) == job_key(
        DALLAS, ATLANTA, EIGHT
    )
    assert departure_hour(datetime(2026, 11, 20, 3, 30, tzinfo=eastern)) == EIGHT


def test_points_within_four_decimals_match_and_further_ones_do_not():
    nudged = {"lat": 32.77671, "lon": -96.79699}  # about a metre away
    moved = {"lat": 32.7769, "lon": -96.797}  # about 20 m away

    assert job_key(nudged, ATLANTA, EIGHT) == job_key(DALLAS, ATLANTA, EIGHT)
    assert job_key(moved, ATLANTA, EIGHT) != job_key(DALLAS, ATLANTA, EIGHT)


def test_a_point_either_side_of_zero_is_the_same_point():
    south = {"lat": -0.00001, "lon": 10.0}
    north = {"lat": 0.00001, "lon": 10.0}

    assert job_key(south, ATLANTA, EIGHT) == job_key(north, ATLANTA, EIGHT)


def test_direction_matters():
    assert job_key(DALLAS, ATLANTA, EIGHT) != job_key(ATLANTA, DALLAS, EIGHT)


def test_equal_loads_written_differently_match():
    assert plan_key(DALLAS, ATLANTA, EIGHT, 30_000) == plan_key(DALLAS, ATLANTA, EIGHT, 30_000.0)
    assert plan_key(DALLAS, ATLANTA, EIGHT, 30_000) != plan_key(DALLAS, ATLANTA, EIGHT, 30_000.5)


def test_naive_departure_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        job_key(DALLAS, ATLANTA, datetime(2026, 11, 20, 8))


def test_keys_fit_their_database_columns_even_at_the_extremes():
    far = {"lat": -89.9999, "lon": -179.9999}

    assert len(job_key(far, far, EIGHT)) <= 80
    assert len(plan_key(far, far, EIGHT, 60_000)) <= 100
