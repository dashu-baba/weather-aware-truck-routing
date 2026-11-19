"""Weather risk classification - the brief's tables, encoded once.

Levels (ints, so they can be averaged):
    0 Low, 1 Moderate, 2 High, 3 Severe, 4 No Travel

Boundary policy (the brief's ranges overlap at the edges, so we decide explicitly):
  * A value equal to a range's LOWER bound belongs to that (higher) level.
      wind 25 -> Moderate, rain 0.25 -> High, snow 1.0 -> High.
  * No Travel follows the brief's own symbols:
      wind >= 55 (inclusive), rain > 1.00 (exclusive), snow > 3.0 (exclusive).
      So rain 1.00 is Severe, rain 1.01 is No Travel.
"""

from __future__ import annotations

from . import config

LEVELS = ("Low", "Moderate", "High", "Severe", "No Travel")
LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = range(5)

# (Moderate from, High from, Severe from, No Travel threshold, No Travel inclusive?)
WIND_MPH = (25.0, 35.0, 45.0, 55.0, True)
RAIN_IN_HR = (0.10, 0.25, 0.50, 1.00, False)
SNOW_IN_HR = (0.5, 1.0, 2.0, 3.0, False)


def level_for(value: float | None, table: tuple) -> int:
    if value is None:
        return LOW
    moderate, high, severe, no_travel, inclusive = table
    if (value >= no_travel) if inclusive else (value > no_travel):
        return NO_TRAVEL
    if value >= severe:
        return SEVERE
    if value >= high:
        return HIGH
    if value >= moderate:
        return MODERATE
    return LOW


def wind_value(w: dict) -> float | None:
    """Which wind number the thresholds are applied to (config.WIND_METRIC)."""
    sustained, gust = w.get("wind_mph"), w.get("gust_mph")
    if config.WIND_METRIC == "gust":
        return gust if gust is not None else sustained
    if config.WIND_METRIC == "max":
        vals = [v for v in (sustained, gust) if v is not None]
        return max(vals) if vals else None
    return sustained


def classify(w: dict, load_lb: float) -> dict:
    """w: {"wind_mph", "gust_mph", "rain_in", "snow_in"} for ONE hour at ONE place.

    Returns {"risk": int, "levels": {...}, "reasons": [...]} - reasons are shown in the UI popup.
    """
    wind = wind_value(w)
    lv_wind = level_for(wind, WIND_MPH)
    lv_rain = level_for(w.get("rain_in"), RAIN_IN_HR)
    lv_snow = level_for(w.get("snow_in"), SNOW_IN_HR)
    reasons: list[str] = []

    # Load rules (wind only). >=55 mph is already No Travel for any load.
    if lv_wind == SEVERE and load_lb > 30_000:
        lv_wind = NO_TRAVEL
        reasons.append(f"wind {wind:.0f} mph (45-54) with load {load_lb:,.0f} lb > 30,000 lb -> No Travel")
    elif lv_wind == HIGH and load_lb > 40_000:
        lv_wind = SEVERE
        reasons.append(f"wind {wind:.0f} mph (35-44) with load {load_lb:,.0f} lb > 40,000 lb -> Severe")

    risk = max(lv_wind, lv_rain, lv_snow)
    if risk > LOW:
        by_hazard = (("wind", lv_wind), ("rain", lv_rain), ("snow", lv_snow))
        drivers = [name for name, lv in by_hazard if lv == risk]
        reasons.append(f"{LEVELS[risk]} driven by {', '.join(drivers)}")
    return {
        "risk": risk,
        "levels": {"wind": lv_wind, "rain": lv_rain, "snow": lv_snow},
        "reasons": reasons,
    }
