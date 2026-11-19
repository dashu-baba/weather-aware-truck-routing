"""SQLite models, plan data files and expiry cleanup."""

from datetime import timedelta
from io import StringIO

import pytest
from django.conf import settings as django_settings
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from planner import storage
from planner.models import PlanRequest, WeatherJob

pytestmark = pytest.mark.django_db

JOB_KEY = "32.7767,-96.7970>33.7490,-84.3880@2026-11-20T08"
PLAN_KEY = f"{JOB_KEY}|30000.0"


@pytest.fixture(autouse=True)
def data_dir(settings, tmp_path):
    """Keep every test's files in its own temp dir, never in the real plan data directory."""
    settings.PLAN_DATA_DIR = tmp_path / "plan-data"
    return settings.PLAN_DATA_DIR


def make_job(key=JOB_KEY, **fields):
    return WeatherJob.objects.create(job_key=key, departure_hour=timezone.now(), **fields)


def make_plan(key=PLAN_KEY, **fields):
    return PlanRequest.objects.create(plan_key=key, payload={"load_lb": 30_000}, **fields)


# --- models -------------------------------------------------------------------------------------


def test_a_new_job_starts_queued_with_a_six_hour_expiry():
    job = make_job()

    assert (job.status, job.stage) == ("queued", "routes")
    assert (job.done_locations, job.total_locations, job.percent) == (0, 0, 0)
    assert job.expires_at - timezone.now() == pytest.approx(timedelta(hours=6), abs=timedelta(seconds=5))


def test_a_new_plan_expires_after_a_day_and_the_ttls_are_configurable(settings):
    assert make_plan().expires_at - timezone.now() == pytest.approx(
        timedelta(hours=24), abs=timedelta(seconds=5)
    )

    settings.PLAN_TTL_S = 60
    settings.WEATHER_JOB_TTL_S = 30
    assert make_plan("other|1.0").expires_at - timezone.now() < timedelta(minutes=2)
    assert make_job("other-job").expires_at - timezone.now() < timedelta(minutes=1)


@pytest.mark.parametrize(
    ("done", "total", "status", "expected"),
    [
        (0, 0, "queued", 0),
        (0, 0, "done", 100),
        (50, 200, "running", 25),
        (199, 200, "running", 99),
        (250, 200, "running", 100),
    ],
)
def test_job_percent(done, total, status, expected):
    assert make_job(done_locations=done, total_locations=total, status=status).percent == expected


def test_a_trip_has_one_job_however_many_times_it_is_requested():
    first, created_first = WeatherJob.objects.get_or_create(
        job_key=JOB_KEY, defaults={"departure_hour": timezone.now()}
    )
    second, created_second = WeatherJob.objects.get_or_create(
        job_key=JOB_KEY, defaults={"departure_hour": timezone.now()}
    )

    assert (created_first, created_second) == (True, False)
    assert first.pk == second.pk


def test_duplicate_job_and_plan_keys_are_rejected_by_the_database():
    make_job()
    make_plan()

    with pytest.raises(IntegrityError), transaction.atomic():
        make_job()
    with pytest.raises(IntegrityError), transaction.atomic():
        make_plan()


def test_loads_on_the_same_trip_share_a_job():
    job = make_job()
    light = make_plan(f"{JOB_KEY}|30000.0", job=job)
    heavy = make_plan(f"{JOB_KEY}|60000.0", job=job)

    assert set(job.plans.all()) == {light, heavy}


def test_deleting_a_job_keeps_its_plans():
    job = make_job()
    plan = make_plan(job=job)

    job.delete()
    plan.refresh_from_db()

    assert plan.job is None


# --- files --------------------------------------------------------------------------------------


def test_json_round_trips_through_the_data_directory(data_dir):
    path = storage.write_json("routes.json", {"routes": [1, 2, 3]})

    assert path.startswith(str(data_dir))
    assert storage.read_json(path) == {"routes": [1, 2, 3]}


def test_writing_leaves_no_temp_files_and_replaces_existing_content(data_dir):
    storage.write_json("a.json", {"v": 1})
    path = storage.write_json("a.json", {"v": 2})

    assert storage.read_json(path) == {"v": 2}
    assert [p.name for p in data_dir.iterdir()] == ["a.json"]


def test_a_failed_write_leaves_neither_a_file_nor_a_temp_file(data_dir):
    with pytest.raises(TypeError):
        storage.write_json("bad.json", {"v": object()})

    assert list(data_dir.iterdir()) == []


@pytest.mark.parametrize("name", ["../escape.json", "sub/dir.json", "/etc/passwd"])
def test_file_names_cannot_contain_directories(name):
    with pytest.raises(ValueError, match="directories"):
        storage.write_json(name, {})


def test_reading_outside_the_data_directory_is_refused(tmp_path):
    outside = tmp_path / "secret.json"
    outside.write_text("{}")

    with pytest.raises(ValueError, match="outside"):
        storage.read_json(str(outside))


def test_remove_file(tmp_path):
    inside = storage.write_json("x.json", {})
    outside = tmp_path / "keep.json"
    outside.write_text("{}")

    assert storage.remove_file(inside) is True
    assert storage.remove_file(inside) is False  # already gone
    assert storage.remove_file("") is False
    assert storage.remove_file(str(outside)) is False
    assert outside.exists()  # files outside the data directory are never deleted


# --- cleanup ------------------------------------------------------------------------------------


def expired():
    return timezone.now() - timedelta(minutes=1)


def test_cleanup_removes_only_what_has_expired_together_with_its_files():
    old_job = make_job("old-job", expires_at=expired(), data_path=storage.write_json("old-weather.json", {}))
    old_plan = make_plan(
        "old-plan",
        expires_at=expired(),
        routes_path=storage.write_json("old-routes.json", {}),
        result_path=storage.write_json("old-result.json", {}),
    )
    fresh_job = make_job("fresh-job", data_path=storage.write_json("fresh-weather.json", {}))
    fresh_plan = make_plan("fresh-plan", result_path=storage.write_json("fresh-result.json", {}))

    counts = storage.cleanup_expired()

    assert counts == {"plans": 1, "jobs": 1, "files": 3}
    assert not WeatherJob.objects.filter(pk=old_job.pk).exists()
    assert not PlanRequest.objects.filter(pk=old_plan.pk).exists()
    assert WeatherJob.objects.filter(pk=fresh_job.pk).exists()
    assert PlanRequest.objects.filter(pk=fresh_plan.pk).exists()
    assert sorted(p.name for p in storage.data_dir().iterdir()) == ["fresh-result.json", "fresh-weather.json"]


def test_cleanup_also_removes_a_jobs_work_and_pool_files_and_a_plans_heatmap():
    job = make_job("old-job", expires_at=expired())  # the row never recorded its files
    storage.write_json(storage.work_name(job), {})
    storage.write_json(storage.pool_name(job), {})
    make_plan("old-plan", expires_at=expired(), heatmap_path=storage.write_json("heat.json", {}))

    counts = storage.cleanup_expired()

    assert counts == {"plans": 1, "jobs": 1, "files": 3}
    assert list(storage.data_dir().iterdir()) == []


def test_cleanup_is_idempotent():
    make_job(expires_at=expired())

    assert storage.cleanup_expired()["jobs"] == 1
    assert storage.cleanup_expired() == {"plans": 0, "jobs": 0, "files": 0}


def test_an_expired_job_goes_but_a_fresh_plan_that_used_it_stays():
    job = make_job(expires_at=expired())
    plan = make_plan(job=job)

    storage.cleanup_expired()
    plan.refresh_from_db()

    assert plan.job is None


def test_cleanup_copes_with_files_that_are_already_gone():
    make_plan(expires_at=expired(), result_path=str(storage.data_dir() / "missing.json"))

    assert storage.cleanup_expired() == {"plans": 1, "jobs": 0, "files": 0}


def test_cleanup_never_deletes_files_outside_the_data_directory(tmp_path):
    outside = tmp_path / "precious.json"
    outside.write_text("{}")
    make_plan(expires_at=expired(), result_path=str(outside))

    storage.cleanup_expired()

    assert outside.exists()


def test_cleanup_can_be_run_for_a_given_moment():
    make_job()

    assert storage.cleanup_expired()["jobs"] == 0
    assert storage.cleanup_expired(now=timezone.now() + timedelta(hours=7))["jobs"] == 1


def test_cleanup_command_reports_what_it_removed():
    make_job(expires_at=expired())
    out = StringIO()

    call_command("cleanup_plans", stdout=out)

    assert out.getvalue().strip() == "Removed 0 plan(s), 1 weather job(s), 0 file(s)."


# --- configuration ------------------------------------------------------------------------------


def test_migrations_are_in_sync_with_the_models():
    # Exits non-zero (SystemExit) when a model change has no migration.
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)


def test_sqlite_runs_in_wal_mode_so_polling_does_not_block_writes():
    options = django_settings.DATABASES["default"]["OPTIONS"]

    assert django_settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert "journal_mode=WAL" in options["init_command"]
