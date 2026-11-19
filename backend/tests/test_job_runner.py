"""Weather jobs: work lists, staged fetching, progress, failures, resuming, the queue and the worker."""

import time
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest import mock

import pytest
import requests
from django.core.management import call_command
from django.utils import timezone as dj_timezone

from planner import jobs, storage
from planner.models import WeatherJob
from routing.openmeteo import RateLimited, weather_key
from routing.pipeline import score_plan
from tests.test_pipeline import HEAVY, LIGHT, full_plan, prepared_plan, without_timestamp
from tests.test_pipeline import FakeProvider as ForecastProvider

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 20, 8, tzinfo=timezone.utc)
END = START + timedelta(hours=48)
SERIES = {
    "time": ["2026-11-20T08:00"],
    "wind_speed_10m": [5.0],
    "wind_gusts_10m": [9.0],
    "wind_direction_10m": [180],
    "rain": [0.0],
    "snowfall": [0.0],
}


@pytest.fixture(autouse=True)
def data_dir(settings, tmp_path):
    settings.PLAN_DATA_DIR = tmp_path / "plan-data"
    return settings.PLAN_DATA_DIR


class FakeProvider:
    """Records every batch it is asked for. Hooks let a test fail or react on a given call."""

    def __init__(self, fail_on=None, on_fetch=None, empty=False):
        self.calls, self.fail_on, self.on_fetch, self.empty = [], fail_on, on_fetch, empty

    def fetch(self, keys, start, end):
        self.calls.append(list(keys))
        if self.on_fetch:
            self.on_fetch(len(self.calls))
        if self.fail_on and len(self.calls) == self.fail_on[0]:
            raise self.fail_on[1]
        return {} if self.empty else {k: SERIES for k in keys}

    @property
    def locations(self):
        return [k for call in self.calls for k in call]


def points(n, first=0):
    """n distinct locations, far enough apart that rounding to 0.1 degree keeps them distinct."""
    return [(30.0 + i * 0.5, -100.0 + i * 0.5) for i in range(first, first + n)]


def keys(pts):
    return [weather_key(*p) for p in pts]


def make_job(name="trip"):
    return WeatherJob.objects.create(job_key=name, departure_hour=START)


def queued_job(stages, name="trip"):
    return jobs.enqueue_locations(make_job(name), stages, START, END)


def run(job, provider):
    claimed = jobs.claim_next()
    assert claimed is not None
    assert claimed.pk == job.pk
    return jobs.process_job(claimed, provider)


def wait_until_done(job, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and WeatherJob.objects.get(pk=job.pk).status != "done":
        time.sleep(0.05)
    return WeatherJob.objects.get(pk=job.pk).status


# --- the work list ------------------------------------------------------------------------------


def test_enqueue_stores_a_deduplicated_work_list_and_the_total():
    job = queued_job({"checkpoints_25": points(3) + points(3), "heatmap": points(5)})

    work = storage.read_json(str(storage.data_dir() / jobs.work_name(job)))
    assert (job.total_locations, job.done_locations, job.status) == (5, 0, "queued")
    assert len(work["stages"]["checkpoints_25"]) == 3
    assert len(work["stages"]["heatmap"]) == 5


def test_enqueue_rejects_unknown_stages_and_a_different_window():
    job = queued_job({"checkpoints_25": points(2)})

    with pytest.raises(ValueError, match="unknown stage"):
        jobs.enqueue_locations(job, {"mystery": points(1)}, START, END)
    with pytest.raises(ValueError, match="different hour"):
        jobs.enqueue_locations(job, {"heatmap": points(1)}, START + timedelta(hours=1), END)
    with pytest.raises(ValueError, match="ends earlier"):
        jobs.enqueue_locations(job, {"heatmap": points(1)}, START, END + timedelta(hours=5))
    jobs.enqueue_locations(
        job, {"heatmap": points(1)}, START, END - timedelta(hours=5)
    )  # a shorter need is fine


# --- running a job ------------------------------------------------------------------------------


def test_stages_run_in_order_and_every_location_is_fetched_once():
    provider = FakeProvider()
    job = queued_job(
        {
            "heatmap": points(4, 10),
            "checkpoints_10": points(2, 5) + points(2, 0),  # the last two are already in the 25 mile stage
            "checkpoints_25": points(3),
            "checkpoints_50": points(2, 1),  # both already covered by the 25 mile stage
        }
    )

    run(job, provider)

    assert provider.calls == [keys(points(3)), keys(points(2, 5)), keys(points(4, 10))]
    assert len(provider.locations) == len(set(provider.locations)) == 9


def test_locations_are_fetched_in_batches_of_50():
    provider = FakeProvider()
    job = queued_job({"heatmap": points(120)})

    run(job, provider)

    assert [len(call) for call in provider.calls] == [50, 50, 20]


def test_progress_is_written_after_every_batch():
    seen = []
    job = queued_job({"heatmap": points(120)})
    provider = FakeProvider(on_fetch=lambda n: seen.append(WeatherJob.objects.get(pk=job.pk).done_locations))

    finished = run(job, provider)

    assert seen == [0, 50, 100]  # what the database showed as each batch started
    assert (finished.done_locations, finished.total_locations, finished.percent) == (120, 120, 100)


def test_a_finished_job_is_done_with_its_forecasts_saved():
    job = queued_job({"checkpoints_25": points(3), "heatmap": points(2, 3)})

    finished = run(job, FakeProvider())

    refreshed = WeatherJob.objects.get(pk=job.pk)
    assert (refreshed.status, refreshed.stage, refreshed.error) == ("done", "done", "")
    assert refreshed.finished_at is not None
    assert refreshed.heartbeat_at is not None
    assert len(storage.read_json(finished.data_path)["series"]) == 5


def test_the_stage_shows_which_part_is_being_fetched():
    stages_seen = []
    job = queued_job({"checkpoints_25": points(2), "heatmap": points(2, 2)})
    provider = FakeProvider(on_fetch=lambda n: stages_seen.append(WeatherJob.objects.get(pk=job.pk).stage))

    run(job, provider)

    assert stages_seen == ["checkpoints_25", "heatmap"]


# --- failures and resuming ----------------------------------------------------------------------


def test_a_failed_job_keeps_what_it_fetched_and_a_retry_resumes_from_there():
    stages = {"heatmap": points(120)}
    job = queued_job(stages)
    failing = FakeProvider(fail_on=(2, RateLimited("busy", retry_after=120)))

    failed = run(job, failing)

    assert (failed.status, failed.done_locations) == ("failed", 50)
    assert "about 2 minute(s)" in failed.error
    assert len(storage.read_json(failed.data_path)["series"]) == 50

    requeued = jobs.enqueue_locations(job, stages, START, END)
    assert (requeued.status, requeued.error) == ("queued", "")
    resumed = FakeProvider()
    run(job, resumed)

    assert len(resumed.locations) == 70  # only what was still missing
    assert WeatherJob.objects.get(pk=job.pk).status == "done"


@pytest.mark.parametrize(
    ("error", "wording"),
    [
        (requests.Timeout("https://api.example/?key=SECRET"), "timed out"),
        (requests.ConnectionError("https://api.example/?key=SECRET"), "failed"),
        (RuntimeError("Open-Meteo HTTP 500: key=SECRET"), "failed"),
        (RateLimited("hourly budget reached"), "busy"),
    ],
)
def test_failures_are_stored_as_safe_public_messages(error, wording):
    job = queued_job({"heatmap": points(3)})

    failed = run(job, FakeProvider(fail_on=(1, error)))

    assert failed.status == "failed"
    assert wording in failed.error
    assert "SECRET" not in failed.error
    assert "http" not in failed.error


def test_missing_data_for_some_locations_fails_instead_of_looping_forever():
    job = queued_job({"heatmap": points(3)})

    failed = run(job, FakeProvider(empty=True))

    assert failed.status == "failed"


def test_a_job_without_a_work_file_fails_cleanly():
    job = make_job()
    WeatherJob.objects.filter(pk=job.pk).update(status="running")

    failed = jobs.process_job(WeatherJob.objects.get(pk=job.pk), FakeProvider())

    assert failed.status == "failed"


# --- sharing a job between plans ----------------------------------------------------------------


def test_a_later_plan_only_fetches_the_locations_the_pool_lacks():
    job = queued_job({"checkpoints_25": points(5)})
    run(job, FakeProvider())

    extended = jobs.enqueue_locations(job, {"checkpoints_25": points(5), "heatmap": points(3, 5)}, START, END)

    assert (extended.status, extended.total_locations, extended.done_locations) == ("queued", 8, 5)
    second = FakeProvider()
    run(job, second)
    assert second.locations == keys(points(3, 5))
    assert WeatherJob.objects.get(pk=job.pk).status == "done"


def test_a_plan_that_needs_nothing_new_leaves_a_finished_job_alone():
    stages = {"checkpoints_25": points(5)}
    job = queued_job(stages)
    run(job, FakeProvider())

    again = jobs.enqueue_locations(job, stages, START, END)

    assert (again.status, again.done_locations, again.total_locations) == ("done", 5, 5)
    assert jobs.claim_next() is None


def test_locations_added_while_the_job_runs_are_fetched_in_the_same_run():
    job = queued_job({"checkpoints_25": points(5)})
    provider = FakeProvider()

    def add_more(call_number):
        if call_number == 1:
            jobs.enqueue_locations(job, {"heatmap": points(4, 5)}, START, END)

    provider.on_fetch = add_more
    run(job, provider)

    refreshed = WeatherJob.objects.get(pk=job.pk)
    assert (refreshed.status, refreshed.total_locations, refreshed.done_locations) == ("done", 9, 9)
    assert len(provider.locations) == 9


def test_job_pool_scores_exactly_like_fetching_inside_the_pipeline():
    prepared = prepared_plan()
    job = jobs.enqueue_locations(make_job(), jobs.stages_for(prepared), prepared.start, prepared.end)
    run(job, ForecastProvider())
    store = jobs.weather_store(WeatherJob.objects.get(pk=job.pk))

    light = score_plan(prepared, store, LIGHT)
    heavy = score_plan(prepared, store, HEAVY)  # a second load from the same job: no more fetching

    assert without_timestamp(light) == without_timestamp(full_plan(LIGHT))
    assert without_timestamp(heavy) == without_timestamp(full_plan(HEAVY))


def test_stages_for_lists_each_interval_and_the_heatmap_cells():
    prepared = prepared_plan()

    stages = jobs.stages_for(prepared)

    assert set(stages) == {"checkpoints_10", "checkpoints_25", "checkpoints_50", "heatmap"}
    assert stages["heatmap"] == prepared.cells
    assert stages["checkpoints_25"] == prepared.checkpoint_points((25,))


def test_the_weather_store_is_read_only():
    store = jobs.weather_store(make_job())

    with pytest.raises(RuntimeError, match="read-only"):
        store.prefetch([(30.0, -100.0)], START, END)


# --- the queue ----------------------------------------------------------------------------------


def test_claims_are_oldest_first_and_a_job_is_never_claimed_twice():
    created = [queued_job({"heatmap": points(1)}, name=f"trip-{i}") for i in range(3)]
    for age, job in enumerate(created):
        WeatherJob.objects.filter(pk=job.pk).update(created_at=START + timedelta(minutes=age))

    claimed = [jobs.claim_next() for _ in range(4)]

    assert [c.pk for c in claimed[:3]] == [job.pk for job in created]
    assert claimed[3] is None
    assert {c.status for c in claimed[:3]} == {"running"}


def test_a_job_another_worker_already_took_is_not_claimed():
    job = queued_job({"heatmap": points(1)})
    WeatherJob.objects.filter(pk=job.pk).update(status="running")

    assert jobs.claim_next() is None


def test_stale_running_jobs_are_requeued_and_live_ones_are_not(settings):
    settings.JOB_STALE_S = 300
    now = dj_timezone.now()
    for name in ("stale", "never", "alive", "waiting"):
        make_job(name)
    WeatherJob.objects.filter(job_key="stale").update(
        status="running", heartbeat_at=now - timedelta(minutes=10)
    )
    WeatherJob.objects.filter(job_key="never").update(status="running", heartbeat_at=None)
    WeatherJob.objects.filter(job_key="alive").update(
        status="running", heartbeat_at=now - timedelta(seconds=30)
    )

    assert jobs.recover_stale_jobs(now) == 2

    status = {j.job_key: j.status for j in WeatherJob.objects.all()}
    assert status == {"stale": "queued", "never": "queued", "alive": "running", "waiting": "queued"}


def test_run_pending_runs_every_queued_job_but_not_failed_ones():
    queued_job({"heatmap": points(2)}, name="one")
    queued_job({"heatmap": points(2, 2)}, name="two")
    queued_job({"heatmap": points(1)}, name="failed")
    WeatherJob.objects.filter(job_key="failed").update(status="failed")

    ran = jobs.run_pending(FakeProvider())

    assert ran == 2
    assert {j.job_key: j.status for j in WeatherJob.objects.all()} == {
        "one": "done",
        "two": "done",
        "failed": "failed",
    }


# --- the worker thread --------------------------------------------------------------------------


def test_enqueuing_wakes_the_running_worker(monkeypatch, django_capture_on_commit_callbacks):
    runner = jobs.JobRunner(FakeProvider())
    monkeypatch.setattr(jobs, "_active_runner", runner)

    with django_capture_on_commit_callbacks(execute=True):
        queued_job({"heatmap": points(1)})

    assert runner._wake.is_set()


@pytest.mark.django_db(transaction=True)
def test_the_worker_thread_runs_a_queued_job_and_stops():
    runner = jobs.JobRunner(FakeProvider(), poll_s=0.05)
    runner.start()
    try:
        job = queued_job({"checkpoints_25": points(3), "heatmap": points(2, 3)})
        assert wait_until_done(job) == "done"
    finally:
        runner.stop()

    assert not runner.alive
    assert jobs._active_runner is None


@pytest.mark.django_db(transaction=True)
def test_the_worker_thread_requeues_stale_jobs_when_it_starts(settings):
    settings.JOB_STALE_S = 1
    job = queued_job({"heatmap": points(2)})
    stale_since = dj_timezone.now() - timedelta(minutes=5)
    WeatherJob.objects.filter(pk=job.pk).update(status="running", heartbeat_at=stale_since)
    runner = jobs.JobRunner(FakeProvider(), poll_s=0.05)
    runner.start()
    try:
        assert wait_until_done(job) == "done"
    finally:
        runner.stop()


def test_run_jobs_command_processes_the_queue_and_exits():
    job = queued_job({"heatmap": points(2)})
    out = StringIO()

    with mock.patch("planner.management.commands.run_jobs.OpenMeteoProvider", FakeProvider):
        call_command("run_jobs", "--once", stdout=out)

    assert out.getvalue().strip() == "Processed 1 job(s)."
    assert WeatherJob.objects.get(pk=job.pk).status == "done"


# --- configuration ------------------------------------------------------------------------------


def test_sqlite_transactions_take_the_write_lock_up_front(settings):
    assert settings.DATABASES["default"]["OPTIONS"]["transaction_mode"] == "IMMEDIATE"
    assert settings.JOB_STALE_S == 300
