"""Route scoring and the brief's lexicographic recommendation.

Brief order:            1 fewest Severe miles, 2 fewest High miles, 3 lowest average risk, 4 shortest time
Our extra rule 0:       fewest No Travel miles first (No Travel is worse than Severe; the brief omits it).
"""

from __future__ import annotations

from functools import cmp_to_key

from . import config
from .risk import HIGH, NO_TRAVEL, SEVERE

CRITERIA = (
    ("no_travel_mi", "fewer No Travel miles"),
    ("severe_mi", "fewer Severe miles"),
    ("high_mi", "fewer High miles"),
    ("avg_risk", "lower average risk"),
    ("duration_s", "shorter travel time"),
)


def score_route(checkpoints: list[dict], duration_s: float) -> dict:
    """Distance-weighted totals. Each checkpoint's risk covers its segment_mi (the stretch before it)."""
    total = sum(c["segment_mi"] for c in checkpoints)

    def by_level(level: int) -> float:
        return sum(c["segment_mi"] for c in checkpoints if c["risk"] == level)

    avg = sum(c["risk"] * c["segment_mi"] for c in checkpoints) / total if total > 0 else 0.0
    return {
        "no_travel_mi": round(by_level(NO_TRAVEL), 2),
        "severe_mi": round(by_level(SEVERE), 2),
        "high_mi": round(by_level(HIGH), 2),
        "avg_risk": round(avg, 4),
        "duration_s": round(duration_s),
        "max_risk": max((c["risk"] for c in checkpoints), default=0),
        "drivable": by_level(NO_TRAVEL) == 0,
    }


def _tolerance(key: str) -> float:
    return config.AVG_RISK_TIE_EPS if key == "avg_risk" else 1e-9


def _cmp(a: dict, b: dict) -> int:
    for key, _ in CRITERIA:
        if abs(a[key] - b[key]) > _tolerance(key):
            return -1 if a[key] < b[key] else 1
    return 0


def rank(scores: dict[str, dict]) -> list[str]:
    """Route ids, best first."""
    return sorted(scores, key=cmp_to_key(lambda i, j: _cmp(scores[i], scores[j])))


def explain(best: dict, runner_up: dict | None) -> str:
    """Which criterion decided the recommendation - show this in the UI."""
    if runner_up is None:
        return "only route available"
    for key, label in CRITERIA:
        if abs(best[key] - runner_up[key]) > _tolerance(key):
            return label
    return "tie on all criteria"
