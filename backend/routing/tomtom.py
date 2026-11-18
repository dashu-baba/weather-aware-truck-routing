import logging
import time

import requests

from . import config

logger = logging.getLogger(__name__)

class TomTomError(RuntimeError):
    pass

def geocode(query: str, *, typeahead: bool = False, limit: int = 5, country_set: str = "US",
            session: requests.Session | None = None) -> list[dict]:
    """Fuzzy Search. typeahead=True for autocomplete (debounce in the UI - every call costs quota)."""
    _require_key()
    http = session or requests
    url = f"{config.TOMTOM_SEARCH_URL}/{requests.utils.quote(query, safe="")}.json"
    params = {"key": config.TOMTOM_API_KEY, "limit": limit, "typeahead": str(typeahead).lower()}
    if country_set:
        params["countrySet"] = country_set
    started = time.monotonic()
    r = http.get(url, params=params, timeout=config.HTTP_TIMEOUT_S)
    logger.debug("TomTom search -> HTTP %s in %.2fs", r.status_code, time.monotonic() - started)
    _raise_for(r)
    return [
        {
            "label": res.get("address", {}).get("freeformAddress") or res.get("poi", {}).get("name", ""),
            "lat": res["position"]["lat"],
            "lon": res["position"]["lon"],
            "type": res.get("type"),
        }
        for res in r.json().get("results", [])
        if "position" in res
    ]

def _require_key() -> None:
    if not config.TOMTOM_API_KEY:
        raise TomTomError("TOMTOM_API_KEY is not set (copy .env.example to .env)")

def _raise_for(r: requests.Response) -> None:
    if r.ok:
        return
    msg = r.text[:300]
    logger.warning("TomTom returned HTTP %s", r.status_code)
    try:
        body = r.json()
        detailed = body.get("detailedError")
        err = body.get("error")
        msg = (detailed.get("message") if isinstance(detailed, dict) else None) \
            or (err.get("description") if isinstance(err, dict) else err) \
            or body.get("errorText") or msg
    except (ValueError, AttributeError):
        pass
    raise TomTomError(f"TomTom HTTP {r.status_code}: {msg}")
