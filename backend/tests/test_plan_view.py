"""POST /api/plan and the plan endpoints: routes at once, weather in the background, scored when it is in.

TomTom is mocked with the real multi-leg fixture route; the job worker is driven by hand with a fake forecast.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
import requests

from planner import jobs, plans
from planner.models import PlanRequest, WeatherJob
from routing import tomtom
from routing.openmeteo import RateLimited, WeatherStore
from routing.pipeline import plan as direct_plan
from tests.test_pipeline import FakeProvider as ForecastProvider
from tests.test_pipeline import route_source, without_timestamp

pytestmark = pytest.mark.django_db

URL = "/api/plan"


def body(**overrides):
    data = {
        "origin": {"label": "Dallas", "lat": 32.7767, "lon": -96.797},
        "destination": {"label": "Atlanta", "lat": 33.749, "lon": -84.388},
        "departure": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "load_lb": 30_000,
    }
    data.update(overrides)
    return data


class Worker(ForecastProvider):
    """A fake forecast the job worker fetches from. Hooks let a test look in or fail on a given call."""

    def __init__(self, on_fetch=None, fail_on=None):
        super().__init__()
        self.batches, self.on_fetch, self.fail_on = 0, on_fetch, fail_on

    def fetch(self, keys, start, end):
        self.batches += 1
        if self.on_fetch:
            self.on_fetch(self.batches)
        if self.fail_on and self.batches == self.fail_on[0]:
            raise self.fail_on[1]
        return super().fetch(keys, start, end)


@pytest.fixture(autouse=True)
def tomtom_routes():
    with mock.patch("planner.services.tomtom.three_routes", side_effect=route_source) as patched:
        yield patched


@pytest.fixture(autouse=True)
def fresh_plan_memory(monkeypatch):
    monkeypatch.setattr(plans, "_prepared", plans.OrderedDict())
    monkeypatch.setattr(plans, "_runner", None)


def start(api, **overrides):
    return api.post(URL, body(**overrides), format="json")


def status_of(api, plan_id):
    return api.get(f"{URL}/{plan_id}")


def run_worker(provider=None):
    provider = provider or Worker()
    jobs.run_pending(provider)
    return provider


def expected(payload):
    """What the old synchronous pipeline gives for this request: (result without heatmap, heatmap)."""
    result = direct_plan(
        payload["origin"],
        payload["destination"],
        datetime.fromisoformat(payload["departure"]),
        payload["load_lb"],
        route_source,
        WeatherStore(ForecastProvider()),
    )
    result = json.loads(json.dumps(result))  # the API returns JSON, so compare JSON with JSON
    return without_timestamp({k: v for k, v in result.items() if k != "heatmap"}), result["heatmap"]


# --- starting a plan ----------------------------------------------------------------------------


def test_the_routes_come_back_at_once_while_the_weather_is_queued(api, tomtom_routes):
    response = start(api)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "weather"
    assert [r["id"] for r in data["routes"]] == ["A", "B", "C"]
    assert all(r["geometry"] and r["summary"]["distance_mi"] > 0 for r in data["routes"])
    assert not any("by_interval" in r for r in data["routes"])
    assert (data["result"], data["partial"], data["heatmap_url"], data["error"]) == (None, None, None, None)
    assert data["progress"]["done"] == 0
    assert data["progress"]["total"] > 0
    assert data["progress"]["queued"] is True
    assert data["poll_after_ms"] == 2000
    assert WeatherJob.objects.get().status == "queued"
    assert tomtom_routes.call_count == 1


def test_the_same_request_is_the_same_plan_and_does_not_ask_tomtom_again(api, tomtom_routes):
    payload = body()

    first = api.post(URL, payload, format="json").json()
    second = api.post(URL, payload, format="json").json()

    assert first["plan_id"] == second["plan_id"]
    assert tomtom_routes.call_count == 1
    assert (PlanRequest.objects.count(), WeatherJob.objects.count()) == (1, 1)


def test_unknown_request_fields_do_not_make_a_different_plan(api):
    payload = body()

    first = api.post(URL, payload, format="json").json()
    second = api.post(URL, {**payload, "junk": 1}, format="json").json()

    assert first["plan_id"] == second["plan_id"]


# --- progress and the finished plan -------------------------------------------------------------


def test_polling_returns_the_scored_plan_once_the_worker_is_done(api):
    payload = body()
    plan_id = api.post(URL, payload, format="json").json()["plan_id"]
    run_worker()

    response = status_of(api, plan_id)

    data = response.json()
    assert (response.status_code, data["status"], data["poll_after_ms"]) == (200, "done", None)
    assert data["progress"]["percent"] == 100
    assert data["heatmap_url"] == f"/api/plan/{plan_id}/heatmap"
    assert "heatmap" not in data["result"]
    want, _ = expected(payload)
    assert without_timestamp(data["result"]) == want


def test_the_heatmap_is_a_separate_request_that_waits_for_the_weather(api):
    payload = body()
    plan_id = api.post(URL, payload, format="json").json()["plan_id"]

    waiting = api.get(f"{URL}/{plan_id}/heatmap")
    run_worker()
    ready = api.get(f"{URL}/{plan_id}/heatmap")

    assert (waiting.status_code, waiting.json()) == (409, {"detail": "The heatmap is not ready yet."})
    assert ready.status_code == 200
    _, want = expected(payload)
    assert ready.json() == want


def test_the_second_poll_of_a_finished_plan_reuses_the_stored_result(api):
    plan_id = start(api).json()["plan_id"]
    run_worker()
    first = status_of(api, plan_id).json()

    with mock.patch("planner.plans.pipeline.score_plan") as scorer:
        second = status_of(api, plan_id).json()

    scorer.assert_not_called()
    assert second["result"] == first["result"]


def test_partial_recommendations_appear_while_the_weather_arrives(api):
    plan_id = start(api).json()["plan_id"]
    snapshots = []
    worker = Worker(on_fetch=lambda n: snapshots.append(status_of(api, plan_id).json()))

    run_worker(worker)

    final = status_of(api, plan_id).json()
    assert all(s["status"] == "weather" for s in snapshots)
    assert snapshots[0]["partial"] is None
    early = next(s for s in snapshots if s["partial"])
    assert early["progress"]["percent"] < 100
    partial = early["partial"]["intervals"]["25"]
    assert set(partial["scores"]) == {"A", "B", "C"}
    assert (
        partial["recommendation"] == final["result"]["recommendation"]["25"]
    )  # the same answer as at the end
    percents = [s["progress"]["percent"] for s in snapshots]
    assert percents == sorted(percents)


# --- sharing the weather between loads ---------------------------------------------------------


def test_another_load_on_the_same_trip_reuses_the_finished_weather(api, tomtom_routes):
    start(api, load_lb=30_000)
    run_worker()

    response = start(api, load_lb=60_000)

    data = response.json()
    assert (response.status_code, data["status"]) == (200, "done")  # scored at once, no waiting
    assert data["result"]["meta"]["load_lb"] == 60_000
    assert any("95,000 lb exceeds" in w for w in data["result"]["meta"]["warnings"])
    assert (WeatherJob.objects.count(), PlanRequest.objects.count()) == (1, 2)
    assert tomtom_routes.call_count == 2  # TomTom is asked per load: it takes the truck weight
    assert run_worker(Worker()).locations == 0  # nothing left to fetch


def test_two_loads_share_one_job_while_it_is_still_queued(api):
    light = start(api, load_lb=30_000).json()
    heavy = start(api, load_lb=60_000).json()

    assert light["plan_id"] != heavy["plan_id"]
    assert (WeatherJob.objects.count(), PlanRequest.objects.count()) == (1, 2)
    assert light["progress"]["total"] == heavy["progress"]["total"]


# --- failures -----------------------------------------------------------------------------------


def test_a_failed_job_reports_a_safe_message_and_posting_again_resumes_it(api):
    plan_id = start(api).json()["plan_id"]
    run_worker(Worker(fail_on=(2, RateLimited("busy", retry_after=120))))

    failed = status_of(api, plan_id).json()
    assert (failed["status"], failed["poll_after_ms"]) == ("failed", None)
    assert "about 2 minute(s)" in failed["error"]
    assert failed["result"] is None

    again = start(api)
    assert (again.status_code, again.json()["status"]) == (202, "weather")
    resumed = run_worker(Worker())

    assert 0 < resumed.locations < failed["progress"]["total"]  # it kept what it already had
    assert status_of(api, plan_id).json()["status"] == "done"


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (tomtom.TomTomError("NO_ROUTE_FOUND", code="NO_ROUTE_FOUND"), 422),
        (tomtom.TomTomError("MAP_MATCHING_FAILURE", code="MAP_MATCHING_FAILURE"), 422),
        (requests.Timeout("slow"), 504),
        (requests.ConnectionError("https://example.test?key=SECRET"), 502),
        (tomtom.TomTomError("TomTom HTTP 401: Forbidden", code="FORBIDDEN"), 502),
        (RuntimeError("boom"), 502),
    ],
)
def test_routing_failures_map_to_status_codes_and_leave_nothing_behind(
    api, tomtom_routes, error, status_code
):
    tomtom_routes.side_effect = error

    response = start(api)

    assert response.status_code == status_code
    assert response.json().keys() == {"detail"}
    assert "SECRET" not in response.content.decode()
    assert (PlanRequest.objects.count(), WeatherJob.objects.count()) == (0, 0)


def test_a_routing_failure_is_not_remembered_so_the_next_request_can_succeed(api, tomtom_routes):
    tomtom_routes.side_effect = tomtom.TomTomError("x")
    first = start(api)
    tomtom_routes.side_effect = route_source

    second = start(api)

    assert (first.status_code, second.status_code) == (502, 202)


def test_a_trip_longer_than_the_forecast_window_is_refused(api, settings):
    settings.JOB_WINDOW_HOURS = 1

    response = start(api)

    assert response.status_code == 422
    assert "forecast window" in response.json()["detail"]
    assert PlanRequest.objects.count() == 0


# --- input and lookups --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"load_lb": -1}, "load_lb"),
        ({"load_lb": 60_001}, "load_lb"),
        ({"load_lb": None}, "load_lb"),
        ({"origin": {"lat": 91, "lon": 0}}, "origin"),
        ({"origin": {"lat": 0, "lon": 181}}, "origin"),
        ({"origin": "Dallas"}, "origin"),
        ({"departure": "tomorrow"}, "departure"),
        ({"departure": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}, "departure"),
        ({"departure": (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()}, "departure"),
        ({"destination": {"lat": 32.7767, "lon": -96.797}}, "non_field_errors"),
    ],
)
def test_invalid_input_is_rejected_before_any_upstream_call(api, tomtom_routes, overrides, field):
    response = start(api, **overrides)

    assert response.status_code == 400
    assert field in response.json()
    tomtom_routes.assert_not_called()


@pytest.mark.parametrize("payload", [{}, [1, 2], None])
def test_non_object_or_empty_bodies_are_rejected(api, tomtom_routes, payload):
    assert api.post(URL, payload, format="json").status_code == 400
    tomtom_routes.assert_not_called()


def test_only_post_is_allowed_on_the_plan_url(api):
    assert api.get(URL).status_code == 405


def test_unknown_or_expired_plans_are_404(api):
    plan_id = start(api).json()["plan_id"]
    PlanRequest.objects.filter(pk=plan_id).update(
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    unknown = uuid.uuid4()
    for url in (
        f"{URL}/{unknown}",
        f"{URL}/{unknown}/heatmap",
        f"{URL}/{plan_id}",
        f"{URL}/{plan_id}/heatmap",
    ):
        response = api.get(url)
        assert response.status_code == 404
        assert "expired" in response.json()["detail"]
    assert api.get(f"{URL}/not-a-uuid").status_code == 404


def test_an_expired_plan_is_replaced_by_a_new_one(api):
    old_id = start(api, load_lb=1000).json()["plan_id"]
    PlanRequest.objects.filter(pk=old_id).update(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))

    new = start(api, load_lb=1000).json()

    assert new["plan_id"] != old_id


# --- surviving restarts and cleanup ------------------------------------------------------------


def test_a_plan_can_be_rebuilt_from_its_saved_routes_after_a_restart(api):
    plan_id = start(api).json()["plan_id"]
    run_worker()
    before = status_of(api, plan_id).json()

    plans._prepared.clear()  # as if the process had restarted: nothing in memory
    PlanRequest.objects.filter(pk=plan_id).update(result_path="", heatmap_path="")
    after = status_of(api, plan_id).json()

    assert without_timestamp(after["result"]) == without_timestamp(before["result"])
    assert after["routes"] == before["routes"]


def test_routes_round_trip_through_json_unchanged():
    routes, warnings = route_source(None, None, "", 0)

    stored = json.loads(json.dumps(plans._routes_to_json(routes, warnings)))
    back, back_warnings = plans._routes_from_json(stored)

    assert back == routes
    assert back_warnings == warnings


def test_a_finished_plan_keeps_its_result_after_its_job_has_expired(api):
    plan_id = start(api).json()["plan_id"]
    run_worker()
    assert status_of(api, plan_id).json()["status"] == "done"  # the result is stored on first read
    WeatherJob.objects.all().delete()

    data = status_of(api, plan_id).json()

    assert data["status"] == "done"
    assert api.get(f"{URL}/{plan_id}/heatmap").status_code == 200


def test_a_plan_whose_job_expired_before_finishing_says_so_and_can_be_restarted(api):
    plan_id = start(api).json()["plan_id"]
    WeatherJob.objects.all().delete()

    gone = status_of(api, plan_id).json()
    assert (gone["status"], "expired" in gone["error"]) == ("failed", True)

    again = start(api)
    assert (again.status_code, again.json()["plan_id"]) == (202, plan_id)
    run_worker()
    assert status_of(api, plan_id).json()["status"] == "done"


# --- the background worker and throttling ------------------------------------------------------


class FakeRunner:
    started = 0

    def __init__(self, provider):
        self.provider, self.running = provider, False

    def start(self):
        FakeRunner.started += 1
        self.running = True

    @property
    def alive(self):
        return self.running


def test_the_worker_thread_is_started_once_when_the_first_plan_is_requested(api, settings, monkeypatch):
    settings.JOB_WORKER = "thread"
    FakeRunner.started = 0
    monkeypatch.setattr(jobs, "JobRunner", FakeRunner)

    start(api, load_lb=1000)
    start(api, load_lb=2000)

    assert FakeRunner.started == 1


def test_an_external_worker_setting_never_starts_a_thread(api, settings, monkeypatch):
    settings.JOB_WORKER = "external"
    FakeRunner.started = 0
    monkeypatch.setattr(jobs, "JobRunner", FakeRunner)

    start(api)

    assert FakeRunner.started == 0


def test_starting_plans_is_throttled_but_polling_has_its_own_allowance(api):
    plan_id = start(api, load_lb=1000).json()["plan_id"]
    codes = [start(api, load_lb=2000 + i).status_code for i in range(6)]

    assert codes == [202] * 5 + [429]
    assert status_of(api, plan_id).status_code == 200
    assert api.get(f"{URL}/{plan_id}/heatmap").status_code == 409
