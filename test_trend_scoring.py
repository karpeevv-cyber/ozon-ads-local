from trend_scoring import (
    acceleration_score,
    confidence_score,
    demand_score,
    pct_change,
    stability_score,
    trend_score,
)


def test_pct_change_handles_zero_baseline():
    assert pct_change(0, 0) == 0.0
    assert pct_change(0, 10) == 100.0


def test_stability_score_rewards_consistent_series():
    stable = stability_score([10, 11, 10, 12, 11])
    volatile = stability_score([1, 30, 2, 25, 1])
    assert stable > volatile


def test_acceleration_score_detects_recent_growth():
    assert acceleration_score([1, 1, 2, 4, 8, 16]) > 0


def test_confidence_score_rewards_coverage_and_queries():
    low = confidence_score(2, 30, False)
    high = confidence_score(25, 30, True)
    assert high > low


def test_trend_score_stays_in_expected_range():
    demand = demand_score(40, 20, 10, 70, "1-3 months")
    score = trend_score(demand, 50, 65, 80)
    assert 0.0 <= score <= 100.0
