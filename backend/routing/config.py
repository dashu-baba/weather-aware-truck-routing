"""All tunable assumptions live here, so they are easy to find, test and document.

Every value below is referenced from docs/01-requirements.md ("Assumptions").
Change a value here -> update that table too.
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # optional: load poc/backend/.env or repo-root .env if python-dotenv is installed
    from dotenv import load_dotenv

    _here = Path(__file__).resolve()
    for candidate in (_here.parents[1] / ".env", _here.parents[2] / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
except ImportError:  # pragma: no cover
    pass

# --- API keys / endpoints -------------------------------------------------
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "")
# Truck routing exists ONLY on the classic v1 endpoint. Orbis endpoints are car-only.
TOMTOM_ROUTING_URL = "https://api.tomtom.com/routing/1/calculateRoute"
TOMTOM_SEARCH_URL = "https://api.tomtom.com/search/2/search"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

HTTP_TIMEOUT_S = 40  # TomTom cancels long alternative searches at ~30 s
OPEN_METEO_BATCH = 50  # locations per Open-Meteo request
# Open-Meteo counts EACH LOCATION as one call: free tier = 600/min, 5,000/hour, 10,000/day.
OPEN_METEO_MAX_LOCATIONS_PER_MIN = 500  # stay safely under 600/min
OPEN_METEO_RETRIES = 3  # on HTTP 429, wait and retry

# --- Units ------------------------------------------------------------------
M_PER_MI = 1609.344
KG_PER_LB = 0.45359237

# --- Truck assumptions --------------------------------------------------------
# The form asks for LOAD weight. TomTom needs GROSS vehicle weight.
TRUCK_TARE_LB = 35_000  # typical empty tractor + 53' trailer (assumption)
MAX_GROSS_LB = 80_000  # US federal gross limit, used only for a UI warning

# --- Sampling -----------------------------------------------------------------
INTERVALS_MI = (10, 25, 50)
DEFAULT_INTERVAL_MI = 25
WEATHER_KEY_DECIMALS = 1  # round lat/lon to 0.1 deg (~7 mi) for weather cache keys

# --- Risk -------------------------------------------------------------------
# "sustained" -> wind_speed_10m, "gust" -> wind_gusts_10m, "max" -> max of both
WIND_METRIC = os.getenv("WIND_METRIC", "sustained")
# Tolerance when comparing average risk between routes (0 = strict brief).
AVG_RISK_TIE_EPS = float(os.getenv("AVG_RISK_TIE_EPS", "0"))

# --- Heatmap corridor -----------------------------------------------------------
HEATMAP_HOURS = 48
CORRIDOR_MODE = "hull"  # "hull" or legacy "band"
HULL_BUFFER_MI = 25
HULL_SIMPLIFY_DEG = 0.0015
HULL_BUFFER_POINTS = 16
CORRIDOR_BUFFER_MI = 30
HEATMAP_MIN_STEP_DEG = 0.2
HEATMAP_MAX_CELLS = 450  # each cell is one Open-Meteo "call" - keep the weather budget small

# --- Route selection --------------------------------------------------------------
TARGET_ROUTES = 3
MAX_ALTERNATIVES = 2  # 1 main + 2 alternatives; raise to 5 to choose the 3 most distinct
DUPLICATE_OVERLAP = 0.85  # routes sharing >85% of their length count as the same route
FRONTEND_SIMPLIFY_DEG = 0.0015  # ~150 m, only for the geometry sent to the browser
