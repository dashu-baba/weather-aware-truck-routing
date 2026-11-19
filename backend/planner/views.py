import logging
import math

import requests
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from routing import tomtom

from .cache import cache_key
from .plans import find_plan, plan_heatmap, plan_status, start_plan
from .serializers import PlanRequestSerializer
from .services import NoRoute, PlanError, TripTooLong, UpstreamTimeout

logger = logging.getLogger(__name__)

GEOCODE_CACHE_TTL_S = 60 * 60 * 24

PLAN_ERRORS = {
    NoRoute: (
        "No truck route found between these points. Check that both are on or near a road.",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
    UpstreamTimeout: ("An upstream service timed out. Try again.", status.HTTP_504_GATEWAY_TIMEOUT),
}

PLAN_NOT_FOUND = {"detail": "Plan not found or expired. Submit it again."}


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class GeocodeView(APIView):
    throttle_scope = "geocode"

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if len(q) < 3:
            return Response({"detail": "Type at least 3 characters."}, status=status.HTTP_400_BAD_REQUEST)

        typeahead = request.query_params.get("typeahead") == "true"
        key = cache_key("geo:", [q.lower(), typeahead])
        hits = cache.get(key)
        if hits is not None:
            logger.debug("geocode cache hit (typeahead=%s)", typeahead)
            return Response(hits)

        try:
            hits = tomtom.geocode(q, typeahead=typeahead, limit=5)
        except tomtom.TomTomError as exc:
            logger.error("geocode failed: %s", exc)
            return Response({"detail": "Geocoding service failed."}, status=status.HTTP_502_BAD_GATEWAY)
        except requests.RequestException as exc:
            # Log only the exception type: str(exc) contains the URL, and the URL contains the API key.
            logger.error("geocode request error: %s", type(exc).__name__)
            return Response({"detail": "Geocoding service failed."}, status=status.HTTP_502_BAD_GATEWAY)

        cache.set(key, hits, GEOCODE_CACHE_TTL_S)
        logger.info("geocode ok: %d result(s) (typeahead=%s)", len(hits), typeahead)
        return Response(hits)


class ReverseGeocodeView(APIView):
    """The label for a point picked on the map. It always answers with a label, so the form can fill in."""

    throttle_scope = "reverse"

    def get(self, request):
        point = _parse_point(request.query_params)
        if point is None:
            return Response(
                {"detail": "lat (-90 to 90) and lon (-180 to 180) are required numbers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lat, lon = point
        key = cache_key("rev:", [round(lat, 4) + 0.0, round(lon, 4) + 0.0])  # 4 decimals is about 11 m
        place = cache.get(key)
        if place is None:
            try:
                hit = tomtom.reverse_geocode(lat, lon)
            except tomtom.TomTomError as exc:
                logger.error("reverse geocode failed: %s", exc)
                return Response({"detail": "Geocoding service failed."}, status=status.HTTP_502_BAD_GATEWAY)
            except requests.RequestException as exc:
                logger.error("reverse geocode request error: %s", type(exc).__name__)  # str(exc) has the key
                return Response({"detail": "Geocoding service failed."}, status=status.HTTP_502_BAD_GATEWAY)
            fallback = {"label": f"{round(lat, 4) + 0.0:.4f}, {round(lon, 4) + 0.0:.4f}", "country": None}
            place = {"found": hit is not None, **(hit or fallback)}
            cache.set(key, place, GEOCODE_CACHE_TTL_S)
            logger.info("reverse geocode ok (found=%s)", place["found"])
        # The point the user chose, not the first visitor of the cached cell.
        return Response(
            {
                "label": place["label"],
                "lat": lat,
                "lon": lon,
                "country": place["country"],
                "found": place["found"],
            }
        )


def _parse_point(params) -> tuple[float, float] | None:
    """lat and lon from the query string as floats, or None if missing, not finite or out of range."""
    try:
        lat, lon = float(params["lat"]), float(params["lon"])
    except (KeyError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return round(lat, 6) + 0.0, round(lon, 6) + 0.0  # "+ 0.0" turns -0.0 into 0.0


class PlanView(APIView):
    """Starts a plan: the routes come back at once, the weather is fetched and scored in the background."""

    throttle_scope = "plan"

    def post(self, request):
        serializer = PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = start_plan(serializer.validated_data)
        except PlanError as exc:
            if isinstance(exc, TripTooLong):
                return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
            detail, code = PLAN_ERRORS.get(
                type(exc), ("Upstream service failed.", status.HTTP_502_BAD_GATEWAY)
            )
            return Response({"detail": detail}, status=code)
        body = plan_status(plan)
        return Response(
            body, status=status.HTTP_200_OK if body["status"] == "done" else status.HTTP_202_ACCEPTED
        )


class PlanStatusView(APIView):
    """Progress, partial results and finally the scored plan. Poll it every `poll_after_ms`."""

    throttle_scope = "plan_status"

    def get(self, request, plan_id):
        plan = find_plan(plan_id)
        if plan is None:
            return Response(PLAN_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response(plan_status(plan))


class PlanHeatmapView(APIView):
    throttle_scope = "plan_status"

    def get(self, request, plan_id):
        plan = find_plan(plan_id)
        if plan is None:
            return Response(PLAN_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        heatmap = plan_heatmap(plan)
        if heatmap is None:
            return Response({"detail": "The heatmap is not ready yet."}, status=status.HTTP_409_CONFLICT)
        return Response(heatmap)
