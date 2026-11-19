"""Keys that decide when two requests can share work.

job key   origin + destination + departure hour. The forecast depends on where and when, never on the
          load, so every load on the same trip shares one weather job.
plan key  the job key plus the load. TomTom takes the truck weight, so routes and scores are per load.
"""

from datetime import datetime, timezone


def departure_hour(departure: datetime) -> datetime:
    """The UTC hour the forecast window starts at. Forecasts are hourly, so minutes do not matter."""
    if departure.tzinfo is None:
        raise ValueError("departure must be timezone-aware")
    return departure.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _coord(value: float) -> str:
    # 4 decimals is about 11 m. "+ 0.0" turns -0.0 into 0.0 so a point just either side of zero matches.
    return f"{round(value, 4) + 0.0:.4f}"


def job_key(origin: dict, destination: dict, departure: datetime) -> str:
    hour = departure_hour(departure).strftime("%Y-%m-%dT%H")
    start = f"{_coord(origin['lat'])},{_coord(origin['lon'])}"
    end = f"{_coord(destination['lat'])},{_coord(destination['lon'])}"
    return f"{start}>{end}@{hour}"


def plan_key(origin: dict, destination: dict, departure: datetime, load_lb: float) -> str:
    return f"{job_key(origin, destination, departure)}|{load_lb:.1f}"
