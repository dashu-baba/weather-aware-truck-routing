"""Route scoring and the brief's lexicographic recommendation.

Brief order:            1 fewest Severe miles, 2 fewest High miles, 3 lowest average risk, 4 shortest time
Our extra rule 0:       fewest No Travel miles first (No Travel is worse than Severe; the brief omits it).
Average risk is compared in AVG_RISK_TIE_EPS steps: a plain average spreads the same bad stretch over more
miles on a longer route, so tiny gaps say more about length than weather. Inside a step, travel time decides.
"""

from __future__ import annotations

import math

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


def _step(avg: float) -> float:
    """Average risk as a step number (floor of avg / eps), or the exact value when eps is 0.

    Steps keep the order consistent with three routes; a pairwise tolerance does not (0.00 ~ 0.04 ~ 0.08).
    """
    eps = config.AVG_RISK_TIE_EPS
    return math.floor(avg / eps + 1e-9) if eps > 0 else avg


def _key(score: dict) -> tuple:
    return tuple(_step(score[key]) if key == "avg_risk" else score[key] for key, _ in CRITERIA)


def rank(scores: dict[str, dict]) -> list[str]:
    """Route ids, best first. Sorting is stable, so full ties keep their input order."""
    return sorted(scores, key=lambda route_id: _key(scores[route_id]))


def explain(best: dict, runner_up: dict | None) -> str:
    """Which criterion decided the recommendation - show this in the UI."""
    if runner_up is None:
        return "only route available"
    for (key, label), a, b in zip(CRITERIA, _key(best), _key(runner_up), strict=True):
        if a != b:
            if key == "avg_risk":
                return f"{label} ({best[key]:.3f} vs {runner_up[key]:.3f})"
            return label
    return "tie on all criteria"
