"""Open-Meteo hourly forecast client + a small cache keyed by rounded lat/lon.

open-meteo Key facts:
  * Free, no key, NON-commercial; < 10,000 calls/day, 5,000/hour, 600/minute. Attribution required.
  * Each LOCATION in a multi-location request counts as a call -> we throttle by locations per
    minute and retry on HTTP 429 (see OpenMeteoProvider).
  * Many locations per request (comma-separated latitude/longitude) -> list of results, same order.
  * Ask for mph and inches so values compare directly with the brief's thresholds.
  * Rain = precipitation - snowfall / 7: the liquid part of the total, so thunderstorm showers count and
    snow is not counted twice. Precipitation, rain and snowfall are totals for the preceding hour, so they
    read as in/hr. Snowfall is new-snow depth in inches, not water.
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

HOURLY_VARS = ("wind_speed_10m", "wind_gusts_10m", "wind_direction_10m", "precipitation", "rain", "snowfall")
# Open-Meteo snowfall depth / 7 = its water equivalent ("7 cm snow = 10 mm precipitation water equivalent").
SNOW_TO_WATER = 7.0
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


HOUR_S = 3600
DAY_S = 86400
MAX_RESET_AHEAD_S = 120  # a Reset further away than this means a skewed clock: ignore the headers


class RateLimited(RuntimeError):
    """Open-Meteo quota reached. `retry_after` is the suggested wait in seconds, when known."""

    def __init__(self, message: str = "", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class OpenMeteoProvider:
    """Real API. Returns {key: {"time": [...], "wind_speed_10m": [...], ...}}.

    Open-Meteo counts every location as one call (free tier: 600/min, 5,000/hour, 10,000/day per IP).
    Three layers keep us inside it:
      * minute: trust the X-RateLimit-Remaining / -Reset headers of the last response, which are the
        server's own count. Before the first response, or when the headers are missing or implausible,
        fall back to a local rolling window of config.OPEN_METEO_MAX_LOCATIONS_PER_MIN.
      * hour / day: a local budget below the real limits. It raises RateLimited(retry_after=...)
        instead of sleeping for an hour. The counters live in memory, so they reset on restart.
      * HTTP 429: wait for the reset time and retry.
    `sleep`, `clock` (monotonic) and `wall_clock` (epoch, compared with the Reset header) are injectable.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
        wall_clock=time.time,
    ):
        self.http = session or requests.Session()
        self.sleep, self.clock, self.wall_clock = sleep, clock, wall_clock
        self._history: deque[tuple[float, int]] = deque()  # (timestamp, locations) sent in the last 24 h
        self._remaining: float | None = None  # from X-RateLimit-Remaining, reduced as we send
        self._reset_at: float | None = None  # from X-RateLimit-Reset (epoch seconds)
        self._minute_floor = float("-inf")  # history before this belongs to a window the server reset

    def _throttle(self, n: int) -> None:
        while True:
            now = self.clock()
            self._prune(now)
            self._check_budgets(now, n)
            wait = self._minute_wait(now, n)
            if wait <= 0:
                self._history.append((now, n))
                if self._remaining is not None:
                    self._remaining -= n
                return
            logger.info("weather: rate limit - waiting %.0f s before sending %d locations", wait, n)
            self.sleep(wait)

    def _prune(self, now: float) -> None:
        while self._history and now - self._history[0][0] >= DAY_S:
            self._history.popleft()

    def _check_budgets(self, now: float, n: int) -> None:
        for window, budget, name in (
            (HOUR_S, config.OPEN_METEO_HOURLY_BUDGET, "hourly"),
            (DAY_S, config.OPEN_METEO_DAILY_BUDGET, "daily"),
        ):
            inside = [(t, c) for t, c in self._history if now - t < window]
            used = sum(c for _, c in inside)
            if inside and used + n > budget:
                retry_after = inside[0][0] + window - now
                logger.warning("weather: %s budget reached (%d of %d locations)", name, used, budget)
                raise RateLimited(
                    f"Open-Meteo {name} budget of {budget} locations reached ({used} used)",
                    retry_after=retry_after,
                )

    def _minute_wait(self, now: float, n: int) -> float:
        """Seconds to wait before n more locations fit in the per-minute limit (0 = go ahead)."""
        wall = self.wall_clock()
        if self._remaining is not None and self._reset_at is not None:
            if wall < self._reset_at:
                return 0.0 if self._remaining >= n else self._reset_at - wall + 0.5
            # The server's window rolled over: its count is fresh, so ignore what we sent before.
            self._remaining = self._reset_at = None
            self._minute_floor = now
        recent = [(t, c) for t, c in self._history if now - t < 60 and t >= self._minute_floor]
        if not recent or sum(c for _, c in recent) + n <= config.OPEN_METEO_MAX_LOCATIONS_PER_MIN:
            return 0.0
        return 60 - (now - recent[0][0]) + 0.5

    def _read_rate_limit_headers(self, r) -> None:
        headers = getattr(r, "headers", None) or {}
        try:
            remaining = float(headers["X-RateLimit-Remaining"])
            reset_at = float(headers["X-RateLimit-Reset"])
        except (KeyError, TypeError, ValueError):
            return
        if reset_at - self.wall_clock() > MAX_RESET_AHEAD_S:
            logger.warning("weather: ignoring rate-limit headers, reset time is implausibly far ahead")
            return
        self._remaining, self._reset_at = remaining, reset_at

    def _reset_wait(self) -> float | None:
        """Seconds until the server's minute window resets, when the headers told us."""
        if self._reset_at is None:
            return None
        wait = self._reset_at - self.wall_clock()
        return wait + 1 if wait > 0 else None

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
            self._read_rate_limit_headers(r)
            if r.status_code == 429:
                reason = r.text[:200]
                if "inute" not in reason:  # hourly / daily limit: waiting a minute won't help
                    raise RateLimited(
                        f"Open-Meteo hourly/daily limit reached - wait, or rerun later "
                        f"(already-fetched batches are cached): {reason}"
                    )
                if attempt == config.OPEN_METEO_RETRIES:
                    raise RateLimited(f"Open-Meteo rate limit after {attempt + 1} attempts: {reason}")
                wait = self._reset_wait() or 65
                logger.warning("weather: HTTP 429 per-minute limit - waiting %.0f s then retrying", wait)
                self.sleep(wait)
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


def liquid_rain(precip: float | None, rain: float | None, snow: float | None) -> float | None:
    """Rain in in/hr: total precipitation minus the water in the snow, never below 0.

    `precipitation` covers rain, showers and snow, so this counts thunderstorm showers and never counts snow
    as rain. Without `precipitation`, fall back to `rain` (None when unknown).
    """
    if precip is None:
        return rain
    return max(0.0, precip - (snow or 0.0) / SNOW_TO_WATER)


def _total_rain(series: dict, i: int) -> float | None:
    """Liquid rain for hour i. Older series without `precipitation` fall back to rain + showers."""

    def value(name: str) -> float | None:
        return series[name][i] if name in series else None

    if value("precipitation") is not None:
        return liquid_rain(value("precipitation"), value("rain"), value("snowfall"))
    known = [v for v in (value("rain"), value("showers")) if v is not None]
    return sum(known) if known else None


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
            "rain_in": _total_rain(s, i),
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
