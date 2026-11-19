import logging

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from config.logging_config import APP_LOGGERS
from routing import config as routing_config

TEST_API_KEY = "test-key-123"


@pytest.fixture(autouse=True)
def clean_cache():
    """LocMemCache is process-wide and also stores throttle counters, so reset it around every test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def tomtom_key(monkeypatch):
    monkeypatch.setattr(routing_config, "TOMTOM_API_KEY", TEST_API_KEY)
    return TEST_API_KEY


@pytest.fixture(autouse=True)
def plan_files(settings, tmp_path):
    """Plan files go to a temp dir, and no test starts the background worker thread on its own."""
    settings.PLAN_DATA_DIR = tmp_path / "plan-data"
    settings.JOB_WORKER = "external"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def app_logs(caplog):
    """Capture the app loggers.

    They don't propagate to root (see logging_config), so attach caplog's handler directly.
    """
    caplog.set_level(logging.DEBUG)
    loggers = [logging.getLogger(name) for name in APP_LOGGERS]
    for lg in loggers:
        lg.addHandler(caplog.handler)
    yield caplog
    for lg in loggers:
        lg.removeHandler(caplog.handler)
