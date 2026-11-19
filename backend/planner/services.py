"""Plan orchestration: caching, weather store setup and upstream error translation.

Views stay thin: they validate input, call get_plan() and map the exceptions below to HTTP statuses.
"""

import logging
import tempfile
from pathlib import Path

import requests
from django.core.cache import cache

from routing import tomtom
from routing.openmeteo import OpenMeteoProvider, RateLimited, WeatherStore
from routing.pipeline import plan as build_plan

from .cache import cache_key

logger = logging.getLogger(__name__)

PLAN_CACHE_TTL_S = 60 * 10
WEATHER_CACHE_DIR = Path(tempfile.gettempdir()) / "weather-cache"

# Shared across requests so the Open-Meteo per-minute throttle sees all traffic.
weather_provider = OpenMeteoProvider()


class PlanError(Exception):
    """Base class for failures the caller should report to the client."""


class WeatherBusy(PlanError):
    """Open-Meteo rate limit hit."""


class UpstreamTimeout(PlanError):
    """An upstream request timed out."""


class NoRoute(PlanError):
    """TomTom can't route between the requested points (the caller's input, not an upstream fault)."""


class UpstreamFailure(PlanError):
    """TomTom or Open-Meteo failed in any other way."""


def get_plan(data: dict) -> dict:
    """Return the plan for validated request data, from cache when possible."""
    key = cache_key("plan:", data)
    result = cache.get(key)
    if result is not None:
        logger.debug("plan cache hit")
        return result

    logger.info("plan requested: load=%.0f lb, departure=%s", data["load_lb"], data["departure"].isoformat())
    store = WeatherStore(weather_provider, cache_dir=WEATHER_CACHE_DIR)
    try:
        result = build_plan(
            dict(data["origin"]),
            dict(data["destination"]),
            data["departure"],
            data["load_lb"],
            tomtom.three_routes,
            store,
        )
    except RateLimited as exc:
        logger.warning("plan failed, weather rate limited: %s", exc)
        raise WeatherBusy from exc
    except requests.Timeout as exc:
        logger.error("plan failed: upstream request timed out")
        raise UpstreamTimeout from exc
    except requests.RequestException as exc:
        # Log only the exception type: str(exc) contains the URL, and the URL contains the API key.
        logger.error("plan failed, request error: %s", type(exc).__name__)
        raise UpstreamFailure from exc
    except tomtom.TomTomError as exc:
        if exc.code in tomtom.NO_ROUTE_CODES:
            logger.warning("plan failed, no route: %s", exc.code)
            raise NoRoute from exc
        logger.error("plan failed: %s", exc)
        raise UpstreamFailure from exc
    except RuntimeError as exc:
        logger.error("plan failed: %s", exc)
        raise UpstreamFailure from exc

    cache.set(key, result, PLAN_CACHE_TTL_S)
    logger.info("plan ok: %d route(s)", len(result["routes"]))
    return result
