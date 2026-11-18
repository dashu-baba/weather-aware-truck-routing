"""Logging configuration, kept out of settings.py so it stays easy to find and change.

Application loggers (``planner``, ``routing``) share one console handler. Output goes to
stderr, which is where Gunicorn and Render collect logs.

Never log full request URLs from the ``requests`` library: TomTom's API key is in the query string.
"""
from __future__ import annotations

APP_LOGGERS = ("planner", "routing")


def build_logging(level: str) -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "standard"},
        },
        "loggers": {
            **{name: {"handlers": ["console"], "level": level, "propagate": False} for name in APP_LOGGERS},
            "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
            # urllib3 logs full URLs (including the API key) at DEBUG.
            "urllib3": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        },
    }
