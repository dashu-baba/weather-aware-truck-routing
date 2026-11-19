"""Settings for the test suite: production-safe defaults plus a throwaway secret key."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-secret")
os.environ.setdefault("LOG_LEVEL", "DEBUG")  # tests assert on debug-level log lines

from .settings import *  # noqa: E402,F401,F403
