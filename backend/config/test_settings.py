"""Settings for the test suite: production-safe defaults plus a throwaway secret key."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-secret")
os.environ.setdefault("LOG_LEVEL", "DEBUG")  # tests assert on debug-level log lines

from .settings import *  # noqa: E402,F401,F403

# Django's default SQLite test database is in memory with a shared cache. There, a second connection
# that touches a locked table fails at once with "database table is locked" (the busy timeout does not
# apply), and the worker thread tests hit that on slow machines. A real file, like production, uses WAL
# and waits for the lock instead. The pid keeps parallel test runs from sharing a file; Django deletes
# it when the run ends.
DATABASES["default"]["TEST"] = {  # noqa: F405
    "NAME": str(Path(tempfile.gettempdir()) / f"truckroute-test-{os.getpid()}.sqlite3"),
}
