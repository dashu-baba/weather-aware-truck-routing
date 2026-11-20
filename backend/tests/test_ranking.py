"""Lexicographic ranking and distance-weighted scores."""

import pytest

from routing import config
from routing.ranking import explain, rank, score_route
from routing.risk import HIGH, LOW, NO_TRAVEL, SEVERE


def s(nt=0, sev=0, high=0, avg=0.0, dur=3600):
    return dict(no_travel_mi=nt, severe_mi=sev, high_mi=high, avg_risk=avg, duration_s=dur)


@pytest.fixture(autouse=True)
def exact_average(monkeypatch):
    monkeypatch.setattr(config, "AVG_RISK_TIE_EPS", 0)


DECISIONS = [
    (s(sev=100, high=200, avg=3, dur=9000), s(nt=10), "fewer No Travel miles"),
    (s(high=200, avg=3, dur=9000), s(sev=10), "fewer Severe miles"),
    (s(avg=2, dur=9000), s(high=10, avg=0.5), "fewer High miles"),
    (s(avg=0.5, dur=9000), s(avg=0.6), "lower average risk (0.500 vs 0.600)"),
    (s(dur=3600), s(dur=4000), "shorter travel time"),
]


@pytest.mark.parametrize(
    ("winner", "loser", "reason"), DECISIONS, ids=["no-travel", "severe", "high", "average", "duration"]
)
def test_first_difference_decides(winner, loser, reason):
    assert rank({"B": loser, "A": winner}) == ["A", "B"]
    assert explain(winner, loser) == reason


def test_three_routes_in_order():
    assert rank({"C": s(nt=1), "A": s(), "B": s(sev=1)}) == ["A", "B", "C"]


def test_full_tie_is_stable():
    assert rank({"C": s(), "A": s(), "B": s()}) == ["C", "A", "B"]
    assert explain(s(), s()) == "tie on all criteria"


@pytest.mark.parametrize(
    ("epsilon", "order", "reason"),
    [
        (0.05, ["faster", "safer"], "shorter travel time"),
        (0, ["safer", "faster"], "lower average risk (1.000 vs 1.030)"),
    ],
    ids=["average-step", "exact-average"],
)
def test_average_tie_step(monkeypatch, epsilon, order, reason):
    monkeypatch.setattr(config, "AVG_RISK_TIE_EPS", epsilon)
    scores = {"faster": s(avg=1.03, dur=3600), "safer": s(avg=1, dur=9000)}
    assert rank(scores) == order
    assert explain(scores[order[0]], scores[order[1]]) == reason


def test_longer_detour_does_not_win_on_dilution(monkeypatch):
    # Same 25 Moderate miles on both: 25/719.6 vs 25/790.4. The longer detour only looks safer.
    monkeypatch.setattr(config, "AVG_RISK_TIE_EPS", 0.05)
    scores = {"detour": s(avg=0.0316, dur=42240), "direct": s(avg=0.0347, dur=39180)}
    assert rank(scores) == ["direct", "detour"]
    assert explain(scores["direct"], scores["detour"]) == "shorter travel time"


def test_clear_average_difference_still_decides(monkeypatch):
    monkeypatch.setattr(config, "AVG_RISK_TIE_EPS", 0.05)
    scores = {"stormy": s(avg=0.2, dur=3600), "clear": s(avg=0.0, dur=9000)}
    assert rank(scores) == ["clear", "stormy"]
    assert explain(scores["clear"], scores["stormy"]) == "lower average risk (0.000 vs 0.200)"


def test_steps_give_a_consistent_order_for_three_routes(monkeypatch):
    # A pairwise tolerance calls 0.00~0.04 and 0.04~0.08 ties but 0.00<0.08: no consistent order.
    monkeypatch.setattr(config, "AVG_RISK_TIE_EPS", 0.05)
    scores = {"high": s(avg=0.08, dur=1000), "mid": s(avg=0.04, dur=2000), "low": s(avg=0.0, dur=3000)}
    for _ in range(3):
        assert rank(scores) == ["mid", "low", "high"]
        scores = dict(reversed(list(scores.items())))


def test_default_step_is_005(monkeypatch):
    import importlib

    monkeypatch.delenv("AVG_RISK_TIE_EPS", raising=False)
    assert importlib.reload(config).AVG_RISK_TIE_EPS == 0.05


def test_only_route_explanation():
    assert explain(s(), None) == "only route available"


def test_distance_weighted_score():
    cps = [
        dict(segment_mi=mi, risk=risk)
        for mi, risk in [(0, SEVERE), (25, LOW), (25, HIGH), (25, SEVERE), (10, NO_TRAVEL)]
    ]
    assert score_route(cps, 3600) == dict(
        no_travel_mi=10,
        severe_mi=25,
        high_mi=25,
        avg_risk=round((0 * 25 + 2 * 25 + 3 * 25 + 4 * 10) / 85, 4),
        duration_s=3600,
        max_risk=NO_TRAVEL,
        drivable=False,
    )


def test_without_no_travel_is_drivable():
    assert score_route([dict(segment_mi=25, risk=SEVERE)], 3600)["drivable"] is True


def test_origin_only_has_zero_average():
    score = score_route([dict(segment_mi=0, risk=SEVERE)], 0)
    assert score["avg_risk"] == 0.0
    assert score["severe_mi"] == 0
    assert score["drivable"] is True
