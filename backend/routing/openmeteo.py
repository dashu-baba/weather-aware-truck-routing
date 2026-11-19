"""Open-Meteo hourly forecast client + a small cache keyed by rounded lat/lon.

open-meteo Key facts:
  * Free, no key, NON-commercial; < 10,000 calls/day, 5,000/hour, 600/minute. Attribution required.
  * Each LOCATION in a multi-location request counts as a call -> we throttle by locations per
    minute and retry on HTTP 429 (see OpenMeteoProvider).
  * Many locations per request (comma-separated latitude/longitude) -> list of results, same order.
  * Ask for mph and inches so values compare directly with the brief's thresholds.
  * Hourly rain / snowfall are totals for the preceding hour == in/hr.
  * timezone=GMT -> every "time" string is UTC ("2026-11-20T14:00").
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Protocol

import requests

from . import config

logger = logging.getLogger(__name__)

HOURLY_VARS = ("wind_speed_10m", "wind_gusts_10m", "wind_direction_10m", "rain", "snowfall")
Key = tuple[float, float]


def weather_key(lat: float, lon: float) -> Key:
    d = config.WEATHER_KEY_DECIMALS
    return (round(lat, d), round(lon, d))


def hour_str(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00")


def nearest_hour(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    base = dt.replace(minute=0, second=0, microsecond=0)
    return base + timedelta(hours=1) if dt.minute >= 30 else base


class Provider(Protocol):
    def fetch(self, keys: list[Key], start: datetime, end: datetime) -> dict[Key, dict]: ...


class RateLimited(RuntimeError):
    pass


class OpenMeteoProvider:
    """Real API. Returns {key: {"time": [...], "wind_speed_10m": [...], ...}}.

    Throttles to config.OPEN_METEO_MAX_LOCATIONS_PER_MIN locations per rolling minute and
    retries HTTP 429 after a pause. `sleep`/`clock` are injectable for tests.
    """

    def __init__(self, session: requests.Session | None = None, sleep=time.sleep, clock=time.monotonic):
        self.http = session or requests.Session()
        self.sleep, self.clock = sleep, clock
        self._sent: deque[tuple[float, int]] = deque()  # (timestamp, locations) in the last 60 s

    def _throttle(self, n: int) -> None:
        limit = config.OPEN_METEO_MAX_LOCATIONS_PER_MIN
        while True:
            now = self.clock()
            while self._sent and now - self._sent[0][0] >= 60:
                self._sent.popleft()
            used = sum(c for _, c in self._sent)
            if used + n <= limit or not self._sent:
                self._sent.append((now, n))
                return
            wait = 60 - (now - self._sent[0][0]) + 0.5
            logger.info("weather: rate limit - waiting %.0f s (%d locations sent last minute)", wait, used)
            self.sleep(wait)

    def fetch(self, keys: list[Key], start: datetime, end: datetime) -> dict[Key, dict]:
        out: dict[Key, dict] = {}
        for i in range(0, len(keys), config.OPEN_METEO_BATCH):
            batch = keys[i : i + config.OPEN_METEO_BATCH]
            out.update(self._fetch_batch(batch, start, end))
        return out

    def _fetch_batch(self, batch: list[Key], start: datetime, end: datetime) -> dict[Key, dict]:
        params = {
            "latitude": ",".join(str(k[0]) for k in batch),
            "longitude": ",".join(str(k[1]) for k in batch),
            "hourly": ",".join(HOURLY_VARS),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "start_hour": hour_str(start),
            "end_hour": hour_str(end),
        }
        for attempt in range(config.OPEN_METEO_RETRIES + 1):
            self._throttle(len(batch))
            started = time.monotonic()
            r = self.http.get(config.OPEN_METEO_URL, params=params, timeout=config.HTTP_TIMEOUT_S)
            logger.debug(
                "weather: HTTP %s for %d location(s) in %.2fs",
                r.status_code,
                len(batch),
                time.monotonic() - started,
            )
            if r.status_code == 429:
                reason = r.text[:200]
                if "inute" not in reason:  # hourly / daily limit: waiting a minute won't help
                    raise RateLimited(
                        f"Open-Meteo hourly/daily limit reached - wait, or rerun later "
                        f"(already-fetched batches are cached): {reason}"
                    )
                if attempt == config.OPEN_METEO_RETRIES:
                    raise RateLimited(f"Open-Meteo rate limit after {attempt + 1} attempts: {reason}")
                logger.warning("weather: HTTP 429 per-minute limit - waiting 65 s then retrying")
                self.sleep(65)
                continue
            if not r.ok:
                logger.error("weather: Open-Meteo returned HTTP %s", r.status_code)
                raise RuntimeError(f"Open-Meteo HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            results = data if isinstance(data, list) else [data]
            if len(results) != len(batch):
                raise RuntimeError(f"Open-Meteo returned {len(results)} results for {len(batch)} locations")
            return {k: res["hourly"] for k, res in zip(batch, results, strict=True)}
        raise RateLimited("Open-Meteo rate limit")  # pragma: no cover


class WeatherStore:
    """Fetch each rounded location ONCE for a time window, then answer point/hour lookups from memory.

    Optional JSON disk cache: one file per location and time window.
    """

    def __init__(self, provider: Provider, cache_dir: Path | None = None):
        self.provider = provider
        self.cache_dir = cache_dir
        self.series: dict[Key, dict] = {}
        self.calls = 0

    def prefetch(self, points: Iterable[tuple[float, float]], start: datetime, end: datetime) -> None:
        keys = sorted({weather_key(lat, lon) for lat, lon in points} - set(self.series))
        if not keys:
            return
        cached = self._load_cache(keys, start, end)
        self.series.update(cached)
        missing = [k for k in keys if k not in cached]
        step = config.OPEN_METEO_BATCH
        for i in range(0, len(missing), step):  # save each batch, so a failure keeps progress
            chunk = missing[i : i + step]
            fetched = self.provider.fetch(chunk, start, end)
            self.calls += len(chunk)
            self._save_cache(fetched, start, end)
            self.series.update(fetched)
            logger.info("weather: %d/%d new locations fetched", min(i + step, len(missing)), len(missing))
        logger.info("weather: %d locations (%d from cache, %d fetched)", len(keys), len(cached), len(missing))

    def at(self, lat: float, lon: float, when: datetime) -> dict | None:
        """Weather at the nearest forecast hour, or None if outside the fetched window."""
        s = self.series.get(weather_key(lat, lon))
        if not s:
            return None
        try:
            i = s["time"].index(hour_str(nearest_hour(when)))
        except ValueError:
            return None
        return {
            "time": s["time"][i],
            "wind_mph": s["wind_speed_10m"][i],
            "gust_mph": s["wind_gusts_10m"][i],
            "direction_deg": s.get("wind_direction_10m", [None] * len(s["time"]))[i],
            "rain_in": s["rain"][i],
            "snow_in": s["snowfall"][i],
        }

    def hours(self, lat: float, lon: float, start: datetime, n: int) -> list[dict | None]:
        return [self.at(lat, lon, start + timedelta(hours=h)) for h in range(n)]

    def _path(self, k: Key, start: datetime, end: datetime) -> Path:
        assert self.cache_dir is not None
        return self.cache_dir / f"{k[0]}_{k[1]}_{hour_str(start)}_{hour_str(end)}.json".replace(":", "")

    def _load_cache(self, keys: list[Key], start: datetime, end: datetime) -> dict[Key, dict]:
        if not self.cache_dir:
            return {}
        out = {}
        for k in keys:
            p = self._path(k, start, end)
            try:
                series = json.loads(p.read_text())
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as exc:
                logger.warning("weather: ignoring unreadable cache file %s (%s)", p.name, type(exc).__name__)
                continue
            if all(name in series for name in HOURLY_VARS):
                out[k] = series
        return out

    def _save_cache(self, data: dict[Key, dict], start: datetime, end: datetime) -> None:
        if not self.cache_dir:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for k, v in data.items():
            self._path(k, start, end).write_text(json.dumps(v))
