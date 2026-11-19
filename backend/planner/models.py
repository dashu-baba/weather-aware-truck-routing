import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def job_expiry():
    return timezone.now() + timedelta(seconds=settings.WEATHER_JOB_TTL_S)


def plan_expiry():
    return timezone.now() + timedelta(seconds=settings.PLAN_TTL_S)


class WeatherJob(models.Model):
    """One weather download for a trip and departure hour, shared by every load (see planner.trips)."""

    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        DONE = "done"
        FAILED = "failed"

    class Stage(models.TextChoices):
        ROUTES = "routes"
        CHECKPOINTS_25 = "checkpoints_25"
        CHECKPOINTS_50 = "checkpoints_50"
        CHECKPOINTS_10 = "checkpoints_10"
        HEATMAP = "heatmap"
        DONE = "done"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_key = models.CharField(max_length=80, unique=True)
    departure_hour = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status, default=Status.QUEUED, db_index=True)
    stage = models.CharField(max_length=16, choices=Stage, default=Stage.ROUTES)
    done_locations = models.PositiveIntegerField(default=0)
    total_locations = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)  # public message only: never a URL or API key
    data_path = models.CharField(max_length=300, blank=True)  # JSON file with the weather pool
    heartbeat_at = models.DateTimeField(null=True, blank=True)  # a running job that stops updating is stale
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(default=job_expiry, db_index=True)

    @property
    def percent(self) -> int:
        if not self.total_locations:
            return 100 if self.status == self.Status.DONE else 0
        return min(100, self.done_locations * 100 // self.total_locations)

    def __str__(self):
        return f"{self.job_key} [{self.status}/{self.stage}]"


class PlanRequest(models.Model):
    """One plan: a trip, departure hour and load. Its routes and scores are per load; weather is the job's."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan_key = models.CharField(max_length=100, unique=True)
    payload = models.JSONField()  # the validated request
    job = models.ForeignKey(
        WeatherJob, null=True, blank=True, on_delete=models.SET_NULL, related_name="plans"
    )
    routes_path = models.CharField(max_length=300, blank=True)  # JSON file with this load's TomTom routes
    result_path = models.CharField(max_length=300, blank=True)  # JSON file with the scored plan
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=plan_expiry, db_index=True)

    def __str__(self):
        return self.plan_key
