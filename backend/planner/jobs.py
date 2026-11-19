"""Background weather jobs: fetch the forecast for the locations a plan needs, one stage at a time.

A job knows nothing about routes, TomTom or loads. Two JSON files per job (under settings.PLAN_DATA_DIR):

  work file   what to fetch: {"start", "end", "stages": {"checkpoints_25": [[lat, lon], ...], ...}}
              written by enqueue_locations(), read by the runner.
  pool file   what has been fetched: {"start", "end", "series": {"lat,lon": hourly series}}
              written by the runner, read back as a WeatherStore by weather_store().

Stages run in STAGE_ORDER so the first useful result (the 25-mile checkpoints that rank the routes) is
ready early and the heatmap, which does not affect ranking, comes last. Locations are fetched once: a later
plan with another load only adds the locations its routes need that the pool does not hold yet.
"""

import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings
from django.db import connections, transaction
from django.db.models import Q
from django.utils import timezone as dj_timezone

from routing import config
from routing.geo import LatLon
from routing.openmeteo import Provider, RateLimited, WeatherStore, weather_key

from . import storage
from .models import WeatherJob
from .storage import pool_name, work_name

logger = logging.getLogger(__name__)

STAGE_ORDER = ("checkpoints_25", "checkpoints_50", "checkpoints_10", "heatmap")
# Locations fetched between saves of the pool file. One batch, so a crash loses at most the batch in flight.
SAVE_EVERY = 50


def _key_str(key: LatLon) -> str:
    return f"{key[0]!r},{key[1]!r}"


def _parse_key(text: str) -> LatLon:
    lat, lon = text.split(",")
    return float(lat), float(lon)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _unique_keys(points) -> list[LatLon]:
    """Rounded Open-Meteo keys, first-seen order, no repeats."""
    return list(dict.fromkeys(weather_key(lat, lon) for lat, lon in points))


def _read_optional(name: str):
    path = storage.data_dir() / name
    return storage.read_json(str(path)) if path.exists() else None


def _load_series(job: WeatherJob) -> dict[LatLon, dict]:
    pool = _read_optional(pool_name(job))
    return {_parse_key(k): v for k, v in pool["series"].items()} if pool else {}


def _all_keys(work: dict) -> list[LatLon]:
    return _unique_keys(tuple(p) for stage in STAGE_ORDER for p in work["stages"].get(stage, []))


def stages_for(prepared) -> dict[str, list[LatLon]]:
    """The work of a pipeline.PreparedPlan: its checkpoints per interval, then its heatmap cells."""
    stages = {f"checkpoints_{iv}": prepared.checkpoint_points((iv,)) for iv in prepared.intervals}
    stages["heatmap"] = list(prepared.cells)
    return stages


def enqueue_locations(
    job: WeatherJob, stages: dict[str, list[LatLon]], start: datetime, end: datetime
) -> WeatherJob:
    """Add locations to a job's work and queue it if there is something new to fetch.

    Safe to call again for the same job from another plan: locations already in the work list or the pool
    are not fetched twice. The forecast window is fixed per job, so `start` must match and `end` may not
    be later than the first plan's.
    """
    unknown = set(stages) - set(STAGE_ORDER)
    if unknown:
        raise ValueError(f"unknown stage(s): {sorted(unknown)}")
    with transaction.atomic():
        job = WeatherJob.objects.get(pk=job.pk)
        work = _read_optional(work_name(job))
        if work is None:
            work = {"start": _iso(start), "end": _iso(end), "stages": {}}
        else:
            if datetime.fromisoformat(work["start"]) != start.astimezone(timezone.utc):
                raise ValueError("this job's forecast window starts at a different hour")
            if end.astimezone(timezone.utc) > datetime.fromisoformat(work["end"]):
                raise ValueError("this job's forecast window ends earlier than the new plan needs")
        for name, points in stages.items():
            known = [tuple(p) for p in work["stages"].get(name, [])]
            added = [k for k in _unique_keys(points) if k not in set(known)]
            work["stages"][name] = [list(k) for k in known + added]
        storage.write_json(work_name(job), work)

        keys = _all_keys(work)
        have = set(_load_series(job))
        job.total_locations = len(keys)
        job.done_locations = sum(1 for k in keys if k in have)
        finished = job.status in (WeatherJob.Status.DONE, WeatherJob.Status.FAILED)
        if finished and job.done_locations < job.total_locations:
            job.status, job.error, job.finished_at = WeatherJob.Status.QUEUED, "", None
        job.save(update_fields=["total_locations", "done_locations", "status", "error", "finished_at"])
        transaction.on_commit(notify)
    return job


# --- running a job -------------------------------------------------------------------------------------


def _public_error(exc: Exception) -> str:
    """A short message that is safe to show: never a URL, and so never the API key."""
    if isinstance(exc, RateLimited):
        if exc.retry_after:
            return f"Weather service is busy. Try again in about {math.ceil(exc.retry_after / 60)} minute(s)."
        return "Weather service is busy. Try again in a few minutes."
    if isinstance(exc, requests.Timeout):
        return "Weather service timed out. Try again."
    return "Weather service failed. Try again."


def _update(job: WeatherJob, **fields) -> None:
    """Write only these fields, so a concurrent enqueue_locations() is never overwritten."""
    WeatherJob.objects.filter(pk=job.pk).update(**fields)
    for name, value in fields.items():
        setattr(job, name, value)


def _save_pool(job: WeatherJob, series: dict[LatLon, dict], work: dict) -> None:
    path = storage.write_json(
        pool_name(job),
        {"start": work["start"], "end": work["end"], "series": {_key_str(k): v for k, v in series.items()}},
    )
    if job.data_path != path:
        _update(job, data_path=path)


def _fail(job: WeatherJob, exc: Exception) -> WeatherJob:
    if isinstance(exc, requests.RequestException):
        logger.error(
            "weather job %s failed: %s", job.pk, type(exc).__name__
        )  # str(exc) holds the URL and key
    else:
        logger.error("weather job %s failed: %s", job.pk, exc)
    _update(job, status=WeatherJob.Status.FAILED, error=_public_error(exc), finished_at=dj_timezone.now())
    return job


def process_job(job: WeatherJob, provider: Provider) -> WeatherJob:
    """Fetch what a claimed job still needs, stage by stage. Upstream errors fail the job, not the caller."""
    work = _read_optional(work_name(job))
    if work is None:
        return _fail(job, RuntimeError("job has no work file"))
    start, end = datetime.fromisoformat(work["start"]), datetime.fromisoformat(work["end"])
    series = _load_series(job)
    unsaved = 0
    try:
        while True:
            work = _read_optional(work_name(job))  # re-read: another plan may have added locations
            keys = _all_keys(work)
            missing = [k for k in keys if k not in series]
            if not missing:
                break
            for stage in STAGE_ORDER:
                todo = [
                    k
                    for k in _unique_keys(tuple(p) for p in work["stages"].get(stage, []))
                    if k not in series
                ]
                if not todo:
                    continue
                logger.info("weather job %s: %s, %d location(s) to fetch", job.pk, stage, len(todo))
                _update(job, stage=stage, total_locations=len(keys), heartbeat_at=dj_timezone.now())
                for i in range(0, len(todo), config.OPEN_METEO_BATCH):
                    chunk = todo[i : i + config.OPEN_METEO_BATCH]
                    series.update(provider.fetch(chunk, start, end))
                    unsaved += len(chunk)
                    if unsaved >= SAVE_EVERY:
                        _save_pool(job, series, work)
                        unsaved = 0
                    _update(
                        job,
                        done_locations=sum(1 for k in keys if k in series),
                        total_locations=len(keys),
                        heartbeat_at=dj_timezone.now(),
                    )
                _save_pool(job, series, work)
                unsaved = 0
            if len([k for k in keys if k not in series]) >= len(missing):
                raise RuntimeError("Open-Meteo returned no data for some locations")
    except Exception as exc:
        _save_pool(job, series, work)  # keep what was fetched: a retry resumes from here
        return _fail(job, exc)

    with transaction.atomic():  # serialised with enqueue_locations(): either it ran first, or it sees DONE
        work = _read_optional(work_name(job))
        keys = _all_keys(work)
        if any(k not in series for k in keys):
            _update(job, status=WeatherJob.Status.QUEUED)  # locations were added while we finished
        else:
            _update(
                job,
                status=WeatherJob.Status.DONE,
                stage=WeatherJob.Stage.DONE,
                done_locations=len(keys),
                total_locations=len(keys),
                finished_at=dj_timezone.now(),
                error="",
            )
    logger.info("weather job %s: %s with %d location(s)", job.pk, job.status, len(series))
    return job


class _ReadOnly:
    def fetch(self, keys, start, end):
        raise RuntimeError("this weather store is read-only: the job runner fetches forecasts")


def weather_store(job: WeatherJob) -> WeatherStore:
    """The job's fetched forecasts as a WeatherStore, ready for pipeline.score_plan()."""
    store = WeatherStore(_ReadOnly())
    store.series = _load_series(job)
    store.calls = len(store.series)
    return store


# --- the queue -----------------------------------------------------------------------------------------


def claim_next() -> WeatherJob | None:
    """Take the oldest queued job. The conditional update means two workers can never take the same one."""
    queued = WeatherJob.objects.filter(status=WeatherJob.Status.QUEUED).order_by("created_at")
    for pk in list(queued.values_list("pk", flat=True)[:10]):
        claimed = WeatherJob.objects.filter(pk=pk, status=WeatherJob.Status.QUEUED).update(
            status=WeatherJob.Status.RUNNING, heartbeat_at=dj_timezone.now(), error=""
        )
        if claimed:
            return WeatherJob.objects.get(pk=pk)
    return None


def recover_stale_jobs(now: datetime | None = None) -> int:
    """Requeue running jobs whose worker died (no heartbeat for JOB_STALE_S). Fetched data is kept."""
    now = now or dj_timezone.now()
    stale = Q(heartbeat_at__lt=now - timedelta(seconds=settings.JOB_STALE_S)) | Q(heartbeat_at__isnull=True)
    count = WeatherJob.objects.filter(stale, status=WeatherJob.Status.RUNNING).update(
        status=WeatherJob.Status.QUEUED
    )
    if count:
        logger.warning("requeued %d stale weather job(s)", count)
    return count


def run_pending(provider: Provider) -> int:
    """Process every queued job, oldest first, and return how many were run."""
    ran = 0
    while (job := claim_next()) is not None:
        process_job(job, provider)
        ran += 1
    return ran


_active_runner: "JobRunner | None" = None


def notify() -> None:
    """Wake the in-process runner, if any, because a job was queued."""
    if _active_runner is not None:
        _active_runner.wake()


class JobRunner:
    """One daemon thread that runs queued jobs one at a time, so they share a single weather budget."""

    def __init__(self, provider: Provider, poll_s: float = 2.0):
        self.provider, self.poll_s = provider, poll_s
        self._wake, self._stop = threading.Event(), threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        global _active_runner
        if self._thread and self._thread.is_alive():
            return
        recover_stale_jobs()
        self._stop.clear()
        _active_runner = self
        self._thread = threading.Thread(target=self._loop, name="weather-job-runner", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10) -> None:
        global _active_runner
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)
        if _active_runner is self:
            _active_runner = None

    def wake(self) -> None:
        self._wake.set()

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    job = claim_next()
                    if job is None:
                        recover_stale_jobs()  # a crashed process can leave a `running` row behind
                        self._wake.wait(self.poll_s)
                        self._wake.clear()
                        continue
                    process_job(job, self.provider)
                except Exception:
                    logger.exception("weather job runner error")
                    time.sleep(1)
        finally:
            connections.close_all()  # this thread's own database connection
