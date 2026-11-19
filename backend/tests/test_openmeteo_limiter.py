"""Open-Meteo provider: header-aware per-minute limiter, hourly/daily budgets and 429 handling.

A fake server counts locations like the real API (600/min window, X-RateLimit-* headers) and a fake
clock makes every wait instant, so the tests run offline in milliseconds.
"""

from datetime import datetime, timedelta, timezone

import pytest

from routing import config
from routing.openmeteo import DAY_S, HOUR_S, OpenMeteoProvider, RateLimited

START = datetime(2026, 11, 20, 8, tzinfo=timezone.utc)
END = START + timedelta(hours=48)
HOURLY = {
    "time": ["2026-11-20T08:00"],
    "wind_speed_10m": [5.0],
    "wind_gusts_10m": [9.0],
    "wind_direction_10m": [180],
    "rain": [0.0],
    "showers": [0.0],
    "snowfall": [0.0],
}
MINUTELY_BODY = '{"reason":"Minutely API request limit exceeded. Try again in one minute.","error":true}'
HOURLY_BODY = '{"reason":"Hourly API request limit exceeded. Try again in one hour.","error":true}'


class Clock:
    """Monotonic and wall clocks that only move when a test (or a provider sleep) moves them."""

    def __init__(self):
        self.mono = 1_000.0
        self.wall = 1_700_000_000.0
        self.slept = []

    def monotonic(self):
        return self.mono

    def time(self):
        return self.wall

    def advance(self, seconds):
        self.mono += seconds
        self.wall += seconds

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.advance(seconds)


class FakeResponse:
    def __init__(self, status=200, headers=None, text="", payload=None):
        self.status_code = status
        self.headers = headers or {}
        self.text = text
        self.payload = payload

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self.payload


def ok_payload(n):
    return [{"hourly": HOURLY} for _ in range(n)]


class FakeServer:
    """Counts locations per window the way Open-Meteo does and answers with X-RateLimit-* headers.

    header_mode: "ok" (real-looking headers), "none", "bad" (unparseable) or "skewed" (Reset far ahead).
    """

    def __init__(self, clock, limit=600, header_mode="ok", reset_after=60):
        self.clock, self.limit, self.header_mode, self.reset_after = clock, limit, header_mode, reset_after
        self.used, self.reset = 0, None
        self.calls, self.rejected = [], 0

    def get(self, url, params, timeout):
        n = len(params["latitude"].split(","))
        now = self.clock.time()
        if self.reset is None or now >= self.reset:
            self.used, self.reset = 0, now + self.reset_after
        self.calls.append(n)
        if self.used + n > self.limit:
            self.rejected += 1
            return FakeResponse(429, self._headers(0), MINUTELY_BODY)
        self.used += n
        return FakeResponse(200, self._headers(self.limit - self.used), payload=ok_payload(n))

    def _headers(self, remaining):
        if self.header_mode == "none":
            return {}
        if self.header_mode == "bad":
            return {"X-RateLimit-Remaining": "abc", "X-RateLimit-Reset": "soon"}
        reset = self.reset + (10_000 if self.header_mode == "skewed" else 0)
        return {"X-RateLimit-Remaining": f"{float(remaining)}", "X-RateLimit-Reset": str(int(reset))}


class Scripted:
    """Answers with the given responses, in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append(len(params["latitude"].split(",")))
        return self.responses.pop(0)


@pytest.fixture
def clock():
    return Clock()


def provider(clock, http):
    return OpenMeteoProvider(session=http, sleep=clock.sleep, clock=clock.monotonic, wall_clock=clock.time)


def keys(n, first=0):
    return [(30.0 + i * 0.1, -100.0 + i * 0.1) for i in range(first, first + n)]


# --- per-minute limit, driven by the server's headers -------------------------------------------


def test_headers_allow_the_full_600_per_minute(clock):
    server = FakeServer(clock)

    result = provider(clock, server).fetch(keys(600), START, END)

    assert len(result) == 600
    assert server.calls == [50] * 12
    assert clock.slept == []  # the old local limit of 500 would have slept here
    assert server.rejected == 0


def test_waits_exactly_until_the_reset_when_the_minute_is_used_up(clock):
    server = FakeServer(clock)

    result = provider(clock, server).fetch(keys(650), START, END)

    assert len(result) == 650
    assert clock.slept == [pytest.approx(60.5)]  # reset is 60 s after the first call, plus 0.5 s margin
    assert server.rejected == 0  # we waited instead of being refused


def test_no_headers_falls_back_to_the_local_500_per_minute(clock):
    server = FakeServer(clock, header_mode="none")

    provider(clock, server).fetch(keys(550), START, END)

    assert server.calls == [50] * 11
    assert clock.slept == [pytest.approx(60.5)]


def test_unparseable_headers_fall_back_to_the_local_limit(clock):
    server = FakeServer(clock, header_mode="bad")

    provider(clock, server).fetch(keys(550), START, END)

    assert clock.slept == [pytest.approx(60.5)]


def test_implausibly_distant_reset_is_ignored(clock):
    server = FakeServer(clock, header_mode="skewed")

    provider(clock, server).fetch(keys(550), START, END)

    # Trusting a reset 10,000 s away would have meant waiting almost 3 hours.
    assert clock.slept == [pytest.approx(60.5)]


def test_stale_history_is_ignored_once_the_servers_window_resets(clock):
    server = FakeServer(clock, reset_after=20)  # the server's window is shorter than our local 60 s
    api = provider(clock, server)
    api.fetch(keys(500), START, END)
    clock.advance(25)

    api.fetch(keys(50, first=500), START, END)

    assert clock.slept == []


def test_fetch_splits_locations_into_batches_of_50(clock):
    server = FakeServer(clock)

    result = provider(clock, server).fetch(keys(120), START, END)

    assert server.calls == [50, 50, 20]
    assert set(result) == set(keys(120))


# --- HTTP 429 -----------------------------------------------------------------------------------


def test_minute_429_waits_for_the_reset_header_then_retries(clock):
    headers = {"X-RateLimit-Remaining": "0.0", "X-RateLimit-Reset": str(int(clock.wall) + 30)}
    http = Scripted(FakeResponse(429, headers, MINUTELY_BODY), FakeResponse(200, payload=ok_payload(2)))

    result = provider(clock, http).fetch(keys(2), START, END)

    assert len(result) == 2
    assert http.calls == [2, 2]
    assert clock.slept == [pytest.approx(31)]


def test_minute_429_without_headers_waits_65_seconds(clock):
    http = Scripted(FakeResponse(429, text=MINUTELY_BODY), FakeResponse(200, payload=ok_payload(1)))

    provider(clock, http).fetch(keys(1), START, END)

    assert clock.slept == [65]


def test_hourly_429_raises_without_waiting(clock):
    http = Scripted(FakeResponse(429, text=HOURLY_BODY))

    with pytest.raises(RateLimited, match="hourly/daily limit"):
        provider(clock, http).fetch(keys(1), START, END)

    assert clock.slept == []


def test_repeated_minute_429s_give_up_after_the_retries(clock):
    http = Scripted(*[FakeResponse(429, text=MINUTELY_BODY) for _ in range(config.OPEN_METEO_RETRIES + 1)])

    with pytest.raises(RateLimited, match=f"after {config.OPEN_METEO_RETRIES + 1} attempts"):
        provider(clock, http).fetch(keys(1), START, END)

    assert clock.slept == [65] * config.OPEN_METEO_RETRIES


# --- hourly and daily budgets -------------------------------------------------------------------


def test_hourly_budget_raises_with_the_time_until_it_frees_up(clock, monkeypatch):
    monkeypatch.setattr(config, "OPEN_METEO_HOURLY_BUDGET", 100)
    server = FakeServer(clock)

    with pytest.raises(RateLimited, match="hourly budget of 100") as info:
        provider(clock, server).fetch(keys(150), START, END)

    assert server.calls == [50, 50]  # the third batch was never sent
    assert info.value.retry_after == pytest.approx(HOUR_S)


def test_hourly_budget_frees_up_after_an_hour(clock, monkeypatch):
    monkeypatch.setattr(config, "OPEN_METEO_HOURLY_BUDGET", 100)
    api = provider(clock, FakeServer(clock))
    api.fetch(keys(100), START, END)
    clock.advance(HOUR_S + 1)

    assert len(api.fetch(keys(50, first=100), START, END)) == 50


def test_daily_budget_raises_even_when_the_hour_is_clear(clock, monkeypatch):
    monkeypatch.setattr(config, "OPEN_METEO_DAILY_BUDGET", 100)
    api = provider(clock, FakeServer(clock))
    api.fetch(keys(100), START, END)
    clock.advance(2 * HOUR_S)

    with pytest.raises(RateLimited, match="daily budget of 100") as info:
        api.fetch(keys(50, first=100), START, END)

    assert info.value.retry_after == pytest.approx(DAY_S - 2 * HOUR_S)


def test_daily_budget_frees_up_after_a_day(clock, monkeypatch):
    monkeypatch.setattr(config, "OPEN_METEO_DAILY_BUDGET", 100)
    api = provider(clock, FakeServer(clock))
    api.fetch(keys(100), START, END)
    clock.advance(DAY_S + 1)

    assert len(api.fetch(keys(100, first=100), START, END)) == 100


def test_a_batch_is_allowed_when_nothing_was_sent_yet(clock, monkeypatch):
    monkeypatch.setattr(config, "OPEN_METEO_HOURLY_BUDGET", 10)  # smaller than one batch

    assert len(provider(clock, FakeServer(clock)).fetch(keys(50), START, END)) == 50


# --- errors -------------------------------------------------------------------------------------


def test_result_count_mismatch_is_an_error(clock):
    http = Scripted(FakeResponse(200, payload=ok_payload(1)))

    with pytest.raises(RuntimeError, match="1 results for 2 locations"):
        provider(clock, http).fetch(keys(2), START, END)


def test_server_error_is_reported(clock):
    http = Scripted(FakeResponse(500, text="boom"))

    with pytest.raises(RuntimeError, match="HTTP 500"):
        provider(clock, http).fetch(keys(1), START, END)


def test_rate_limited_keeps_its_old_signature():
    assert RateLimited("busy").retry_after is None
    assert RateLimited("busy", retry_after=5).retry_after == 5
    assert str(RateLimited("busy")) == "busy"
