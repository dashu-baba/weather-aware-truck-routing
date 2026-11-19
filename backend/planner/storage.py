"""Plan data files and expiry cleanup.

Rows in the database stay small; routes, weather and scored plans are JSON files under settings.PLAN_DATA_DIR
and a row stores the path. Every path is checked to be inside that directory before it is read or deleted.
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import PlanRequest, WeatherJob

logger = logging.getLogger(__name__)


def data_dir() -> Path:
    path = Path(settings.PLAN_DATA_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _inside_data_dir(path: str | Path) -> Path | None:
    resolved = Path(path).resolve()
    return resolved if resolved.is_relative_to(data_dir().resolve()) else None


def write_json(name: str, payload) -> str:
    """Write `payload` as <data dir>/<name> atomically (temp file, then rename) and return the path."""
    if Path(name).name != name:
        raise ValueError("file name must not contain directories")
    target = data_dir() / name
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return str(target)


def read_json(path: str):
    inside = _inside_data_dir(path)
    if inside is None:
        raise ValueError("path is outside the plan data directory")
    return json.loads(inside.read_text())


def remove_file(path: str) -> bool:
    """Delete a data file. Returns whether a file was removed. Paths outside the data dir are refused."""
    if not path:
        return False
    inside = _inside_data_dir(path)
    if inside is None:
        logger.warning("refusing to delete a file outside the plan data directory")
        return False
    try:
        inside.unlink()
    except FileNotFoundError:
        return False
    return True


def cleanup_expired(now: datetime | None = None) -> dict[str, int]:
    """Delete expired plans and weather jobs together with their files. Safe to run at any time."""
    now = now or timezone.now()
    with transaction.atomic():
        plans = list(PlanRequest.objects.filter(expires_at__lte=now))
        jobs = list(WeatherJob.objects.filter(expires_at__lte=now))
        paths = [p for plan in plans for p in (plan.routes_path, plan.result_path)]
        paths += [job.data_path for job in jobs]
        PlanRequest.objects.filter(pk__in=[plan.pk for plan in plans]).delete()
        WeatherJob.objects.filter(pk__in=[job.pk for job in jobs]).delete()
    files = sum(remove_file(path) for path in paths)
    counts = {"plans": len(plans), "jobs": len(jobs), "files": files}
    if any(counts.values()):
        logger.info("cleanup: removed %(plans)d plan(s), %(jobs)d weather job(s), %(files)d file(s)", counts)
    return counts
