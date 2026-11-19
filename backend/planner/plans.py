"""The plan flow: routes now, weather in the background, scoring once the forecasts are in.

start_plan()     validated request -> a PlanRequest. Reuses an identical plan, otherwise gets the routes
                 from TomTom (seconds), attaches the plan to the weather job of its trip and queues the
                 locations that job still lacks. Another load on the same trip shares the job.
plan_status()    what the API returns: routes always, progress and partial results while the job runs,
                 the scored result when it is done.
plan_heatmap()   the heatmap, which is stored apart because it is large and affects no ranking.
"""

import dataclasses
import logging
import threading
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone as dj_timezone

from routing import pipeline
from routing.openmeteo import OpenMeteoProvider, weather_key
from routing.tomtom import ParsedRoute

from . import jobs, services, storage
from .models import PlanRequest, WeatherJob
from .trips import departure_hour, job_key, plan_key

logger = logging.getLogger(__name__)

POLL_MS = 2000
PREPARED_CACHE_SIZE = 8

# One provider for every job, so the Open-Meteo pacing sees all the traffic of this process.
weather_provider = OpenMeteoProvider()

_runner: jobs.JobRunner | None = None
_runner_lock = threading.Lock()
_prepared: OrderedDict[str, pipeline.PreparedPlan] = OrderedDict()
_prepared_lock = threading.Lock()


def ensure_worker() -> None:
    """Start the in-process job worker the first time it is needed (JOB_WORKER=thread, the default).

    Set JOB_WORKER=external to run `manage.py run_jobs` as a separate process instead.
    """
    global _runner
    if settings.JOB_WORKER != "thread":
        return
    with _runner_lock:
        if _runner is None:
            _runner = jobs.JobRunner(weather_provider)
        if not _runner.alive:
            _runner.start()


# --- routes on disk -----------------------------------------------------------------------------------


def _routes_to_json(routes: list[ParsedRoute], warnings: list[str]) -> dict:
    return {"warnings": warnings, "routes": [dataclasses.asdict(r) for r in routes]}


def _routes_from_json(data: dict) -> tuple[list[ParsedRoute], list[str]]:
    routes = [
        ParsedRoute(
            **{**r, "points": [tuple(p) for p in r["points"]], "progress": [tuple(p) for p in r["progress"]]}
        )
        for r in data["routes"]
    ]
    return routes, data["warnings"]


def _prepare(payload: dict, routes: list[ParsedRoute], warnings: list[str]) -> pipeline.PreparedPlan:
    return pipeline.prepare(
        payload["origin"],
        payload["destination"],
        datetime.fromisoformat(payload["departure"]),
        payload["load_lb"],
        lambda *_: (routes, warnings),
    )


def _remember(plan_id, prepared: pipeline.PreparedPlan) -> None:
    with _prepared_lock:
        _prepared[str(plan_id)] = prepared
        _prepared.move_to_end(str(plan_id))
        while len(_prepared) > PREPARED_CACHE_SIZE:
            _prepared.popitem(last=False)


def prepared_for(plan: PlanRequest) -> pipeline.PreparedPlan:
    """The plan's checkpoints and grid, rebuilt from its saved routes (and remembered for the next poll)."""
    with _prepared_lock:
        found = _prepared.get(str(plan.pk))
    if found is not None:
        return found
    routes, warnings = _routes_from_json(storage.read_json(plan.routes_path))
    prepared = _prepare(plan.payload, routes, warnings)
    _remember(plan.pk, prepared)
    return prepared


# --- starting a plan ----------------------------------------------------------------------------------


def _window_end(prepared: pipeline.PreparedPlan) -> datetime:
    return prepared.start + timedelta(hours=settings.JOB_WINDOW_HOURS)


def _create_plan(key: str, payload: dict) -> PlanRequest:
    departure = datetime.fromisoformat(payload["departure"])
    routes, warnings = services.fetch_routes(
        payload["origin"],
        payload["destination"],
        departure.isoformat().replace("+00:00", "Z"),
        payload["load_lb"],
    )
    prepared = _prepare(payload, routes, warnings)
    if prepared.end > _window_end(prepared):
        raise services.TripTooLong(
            f"This trip is longer than the {settings.JOB_WINDOW_HOURS}-hour forecast window."
        )
    plan, _ = PlanRequest.objects.get_or_create(plan_key=key, defaults={"payload": payload})
    path = storage.write_json(f"plan-{plan.pk}-routes.json", _routes_to_json(routes, warnings))
    PlanRequest.objects.filter(pk=plan.pk).update(routes_path=path)
    plan.routes_path = path
    _remember(plan.pk, prepared)
    return plan


def _stored_file_exists(path: str) -> bool:
    return bool(path) and (storage.data_dir() / Path(path).name).exists()


def _attach_job(plan: PlanRequest) -> None:
    """Join (or create) the trip's weather job and queue the locations this plan needs that it lacks."""
    prepared = prepared_for(plan)
    payload = plan.payload
    key = job_key(payload["origin"], payload["destination"], datetime.fromisoformat(payload["departure"]))
    with transaction.atomic():
        job, _ = WeatherJob.objects.get_or_create(
            job_key=key, defaults={"departure_hour": departure_hour(prepared.departure)}
        )
        if plan.job_id != job.pk:
            PlanRequest.objects.filter(pk=plan.pk).update(job=job)
            plan.job = job
    jobs.enqueue_locations(job, jobs.stages_for(prepared), prepared.start, _window_end(prepared))


def start_plan(data: dict) -> PlanRequest:
    """Find or create the plan for validated request data and make sure its weather is being fetched."""
    storage.cleanup_expired()
    payload = {
        "origin": dict(data["origin"]),
        "destination": dict(data["destination"]),
        "departure": data["departure"].isoformat(),
        "load_lb": data["load_lb"],
    }
    key = plan_key(payload["origin"], payload["destination"], data["departure"], payload["load_lb"])
    plan = PlanRequest.objects.filter(plan_key=key).select_related("job").first()
    if plan is None or not plan.routes_path:
        plan = _create_plan(key, payload)
    if not _stored_file_exists(plan.result_path):
        _attach_job(plan)  # also requeues a failed job, which resumes from the forecasts it already has
        ensure_worker()
    return plan


def find_plan(plan_id) -> PlanRequest | None:
    return (
        PlanRequest.objects.filter(pk=plan_id, expires_at__gt=dj_timezone.now()).select_related("job").first()
    )


# --- reporting a plan ---------------------------------------------------------------------------------


def _progress(job: WeatherJob | None, done: bool = False) -> dict:
    if done:
        total = job.total_locations if job else 0
        return {"stage": "done", "done": total, "total": total, "percent": 100, "queued": False}
    if job is None:
        return {"stage": "routes", "done": 0, "total": 0, "percent": 0, "queued": False}
    return {
        "stage": job.stage,
        "done": job.done_locations,
        "total": job.total_locations,
        "percent": job.percent,
        "queued": job.status == WeatherJob.Status.QUEUED,
    }


def _load_stored(path: str):
    return storage.read_json(path) if _stored_file_exists(path) else None


def _score_and_store(plan: PlanRequest, prepared: pipeline.PreparedPlan, job: WeatherJob) -> dict:
    """Score the finished job's forecasts for this plan's load and keep the result (heatmap apart)."""
    result = pipeline.score_plan(prepared, jobs.weather_store(job), plan.payload["load_lb"])
    heatmap = result.pop("heatmap")
    plan.result_path = storage.write_json(f"plan-{plan.pk}-result.json", result)
    plan.heatmap_path = storage.write_json(f"plan-{plan.pk}-heatmap.json", heatmap)
    PlanRequest.objects.filter(pk=plan.pk).update(
        result_path=plan.result_path, heatmap_path=plan.heatmap_path
    )
    return result


def _partial(plan: PlanRequest, prepared: pipeline.PreparedPlan, job: WeatherJob) -> dict | None:
    """Recommendations for every checkpoint interval whose forecasts have all arrived."""
    store = jobs.weather_store(job)
    ready = tuple(
        iv
        for iv in prepared.intervals
        if all(weather_key(*p) in store.series for p in prepared.checkpoint_points((iv,)))
    )
    if not ready:
        return None
    scored = pipeline.score_plan(
        prepared.restricted(ready), store, plan.payload["load_lb"], include_heatmap=False
    )
    return {
        "intervals": {
            str(iv): {
                "recommendation": scored["recommendation"][str(iv)],
                "scores": {r["id"]: r["by_interval"][str(iv)]["score"] for r in scored["routes"]},
            }
            for iv in ready
        }
    }


def plan_status(plan: PlanRequest) -> dict:
    """The response body for POST /api/plan and GET /api/plan/<id>."""
    prepared = prepared_for(plan)
    job = WeatherJob.objects.filter(pk=plan.job_id).first() if plan.job_id else None
    body = {
        "plan_id": str(plan.pk),
        "status": "weather",
        "routes": [pipeline.route_entry(prepared, pr) for pr in prepared.routes],
        "progress": _progress(job),
        "partial": None,
        "result": None,
        "heatmap_url": None,
        "error": None,
        "poll_after_ms": POLL_MS,
    }
    result = _load_stored(plan.result_path)
    if result is None and job is not None and job.status == WeatherJob.Status.DONE:
        result = _score_and_store(plan, prepared, job)
    if result is not None:
        body.update(
            status="done",
            result=result,
            progress=_progress(job, done=True),
            heatmap_url=f"/api/plan/{plan.pk}/heatmap",
            poll_after_ms=None,
        )
    elif job is None:
        body.update(status="failed", error="The forecast expired. Submit the plan again.", poll_after_ms=None)
    elif job.status == WeatherJob.Status.FAILED:
        body.update(
            status="failed", error=job.error or "Weather service failed. Try again.", poll_after_ms=None
        )
    else:
        body["partial"] = _partial(plan, prepared, job)
    return body


def plan_heatmap(plan: PlanRequest) -> dict | None:
    """The plan's heatmap, or None while the weather is still being fetched."""
    heatmap = _load_stored(plan.heatmap_path)
    if heatmap is not None:
        return heatmap
    job = WeatherJob.objects.filter(pk=plan.job_id).first() if plan.job_id else None
    if job is None or job.status != WeatherJob.Status.DONE:
        return None
    _score_and_store(plan, prepared_for(plan), job)
    return _load_stored(plan.heatmap_path)
