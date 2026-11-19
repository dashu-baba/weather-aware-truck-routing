"""The TomTom side of a plan: get the routes and turn upstream failures into errors the API can report.

Views stay thin: they validate input, call plans.start_plan() and map the exceptions below to HTTP statuses.
"""

import logging

import requests

from routing import tomtom
from routing.tomtom import ParsedRoute

logger = logging.getLogger(__name__)


class PlanError(Exception):
    """Base class for failures the caller should report to the client."""


class UpstreamTimeout(PlanError):
    """An upstream request timed out."""


class NoRoute(PlanError):
    """TomTom can't route between the requested points (the caller's input, not an upstream fault)."""


class TripTooLong(PlanError):
    """The trip outlasts the forecast window a weather job covers."""


class UpstreamFailure(PlanError):
    """TomTom failed in any other way."""


def fetch_routes(
    origin: dict, destination: dict, depart_iso: str, load_lb: float
) -> tuple[list[ParsedRoute], list[str]]:
    """Up to three truck routes from TomTom, with its warnings."""
    try:
        return tomtom.three_routes(
            (origin["lat"], origin["lon"]), (destination["lat"], destination["lon"]), depart_iso, load_lb
        )
    except requests.Timeout as exc:
        logger.error("routing failed: upstream request timed out")
        raise UpstreamTimeout from exc
    except requests.RequestException as exc:
        # Log only the exception type: str(exc) contains the URL, and the URL contains the API key.
        logger.error("routing failed, request error: %s", type(exc).__name__)
        raise UpstreamFailure from exc
    except tomtom.TomTomError as exc:
        if exc.code in tomtom.NO_ROUTE_CODES:
            logger.warning("routing failed, no route: %s", exc.code)
            raise NoRoute from exc
        logger.error("routing failed: %s", exc)
        raise UpstreamFailure from exc
    except RuntimeError as exc:
        logger.error("routing failed: %s", exc)
        raise UpstreamFailure from exc
