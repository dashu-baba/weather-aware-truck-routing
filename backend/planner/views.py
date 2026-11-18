import logging

import requests
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from routing import tomtom

from .cache import cache_key

logger = logging.getLogger(__name__)

GEOCODE_CACHE_TTL_S = 60 * 60 * 24


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
