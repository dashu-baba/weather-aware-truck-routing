"""Environment helpers: .env loading and typed readers for settings."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

# Used only when DJANGO_DEBUG is on and no key is given. Never reaches production.
DEV_SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"


def load_env_files() -> None:
    """Load backend/.env, then the repo-root .env. Variables that are already set win."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    here = Path(__file__).resolve()
    for candidate in (here.parents[1] / ".env", here.parents[2] / ".env"):
        if candidate.exists():
            load_dotenv(candidate)


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ImproperlyConfigured(f"{name} must be one of 1/0, true/false, yes/no, on/off (got {raw!r})")


def env_list(name: str, default: list[str]) -> list[str]:
    """Comma-separated list. Unset -> default. Set but empty -> []."""
    raw = os.getenv(name)
    if raw is None:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def resolve_secret_key(debug: bool, value: str | None) -> str:
    if value:
        return value
    if debug:
        return DEV_SECRET_KEY
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")
