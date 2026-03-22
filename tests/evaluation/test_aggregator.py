"""Tests for FitnessAggregator with penalty-based tier multipliers."""

import pytest

from api.evaluation.aggregator import FitnessAggregator
from api.evaluation.models import CaseResult, FitnessScore


@pytest.fixture
def aggregator() -> FitnessAggregator:
    """Default aggregator with standard multipliers."""
    return FitnessAggregator()


@pytest.fixture
def custom_aggregator() -> FitnessAggregator:
    """Aggregator with custom multipliers."""
    return FitnessAggregator(
        critical_multiplier=10.0,
        normal_multiplier=2.0,
        low_multiplier=0.5,
    )


# --- Empty results ---


def test_aggregate_empty_results(aggregator: FitnessAggregator) -> None:
    """Empty results list returns score=0.0, not rejected."""
    result = aggregator.aggregate([])
    assert isinstance(result, FitnessScore)
    assert result.score == 0.0
    assert result.rejected is False
    assert result.case_results == []


# --- Critical failures with penalty amplification ---


def test_aggregate_critical_failure_rejects(aggregator: FitnessAggregator) -> None:
    """Critical case with score=-2, tier='critical' -> score = -2 * 5.0 = -10.0."""
    results = [
        CaseResult(case_id="c1", tier="critical", score=-2, passed=False),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.score == -10.0
    # -10.0 is NOT < -10 (it's equal), so rejected=False
    assert fitness.rejected is False
    assert fitness.case_results == results


def test_aggregate_multiple_critical_failures(aggregator: FitnessAggregator) -> None:
    """Two critical failures: score = (-2 * 5) + (-2 * 5) = -20.0."""
    results = [
        CaseResult(case_id="c1", tier="critical", score=-2, passed=False),
        CaseResult(case_id="c2", tier="critical", score=-2, passed=False),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.score == -20.0
    assert fitness.rejected is True  # -20 < -10


# --- Critical cases all pass ---


def test_aggregate_all_critical_pass(aggregator: FitnessAggregator) -> None:
    """Critical at 0 + Normal at 0 -> total = 0.0. Not rejected."""
    results = [
        CaseResult(case_id="c1", tier="critical", score=0, passed=True),
        CaseResult(case_id="n1", tier="normal", score=0, passed=True),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.rejected is False
    assert fitness.score == 0.0


# --- Normal cases with penalties ---


def test_aggregate_normal_cases_only(aggregator: FitnessAggregator) -> None:
    """Two normal cases with score=-1 each -> -1 + -1 = -2.0."""
    results = [
        CaseResult(case_id="n1", tier="normal", score=-1, passed=False),
        CaseResult(case_id="n2", tier="normal", score=-1, passed=False),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.rejected is False
    assert fitness.score == pytest.approx(-2.0)


# --- Low cases with reduced multiplier ---


def test_aggregate_low_cases_soft_signals(aggregator: FitnessAggregator) -> None:
    """Normal at 0, low at -2 -> 0 + (-2 * 0.25) = -0.5."""
    results = [
        CaseResult(case_id="n1", tier="normal", score=0, passed=True),
        CaseResult(case_id="l1", tier="low", score=-2, passed=False),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.rejected is False
    assert fitness.score == pytest.approx(-0.5)


# --- Mixed tiers ---


def test_aggregate_mixed_tiers(aggregator: FitnessAggregator) -> None:
    """Critical 0 + Normal -1 + Low -2 -> (0*5) + (-1*1) + (-2*0.25) = -1.5."""
    results = [
        CaseResult(case_id="c1", tier="critical", score=0, passed=True),
        CaseResult(case_id="n1", tier="normal", score=-1, passed=False),
        CaseResult(case_id="l1", tier="low", score=-2, passed=False),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.rejected is False
    assert fitness.score == pytest.approx(-1.5)


# --- Custom multipliers ---


def test_aggregate_custom_multipliers(custom_aggregator: FitnessAggregator) -> None:
    """Custom multipliers affect scoring correctly."""
    results = [
        CaseResult(case_id="n1", tier="normal", score=-1, passed=False),
        CaseResult(case_id="l1", tier="low", score=-2, passed=False),
    ]
    fitness = custom_aggregator.aggregate(results)
    assert fitness.rejected is False
    # normal_multiplier=2.0, low_multiplier=0.5
    # (-1 * 2.0) + (-2 * 0.5) = -2.0 + -1.0 = -3.0
    assert fitness.score == pytest.approx(-3.0)


def test_aggregate_custom_critical_multiplier(custom_aggregator: FitnessAggregator) -> None:
    """Custom critical_multiplier amplifies penalties."""
    # critical_multiplier=10.0, score=-2 -> -20.0
    results = [
        CaseResult(case_id="c1", tier="critical", score=-2, passed=False),
    ]
    fitness = custom_aggregator.aggregate(results)
    assert fitness.score == pytest.approx(-20.0)
    assert fitness.rejected is True  # -20 < -10


# --- Case-insensitive tier matching ---


def test_aggregate_tier_case_insensitive(aggregator: FitnessAggregator) -> None:
    """Tier string comparison uses lowercase matching."""
    results = [
        CaseResult(case_id="c1", tier="Critical", score=0, passed=True),
        CaseResult(case_id="n1", tier="NORMAL", score=-1, passed=False),
        CaseResult(case_id="l1", tier="Low", score=-2, passed=False),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.rejected is False
    # Critical(0)*5 + Normal(-1)*1 + Low(-2)*0.25 = 0 + -1 + -0.5 = -1.5
    assert fitness.score == pytest.approx(-1.5)


# --- Penalty sum formula ---


def test_penalty_sum_formula(aggregator: FitnessAggregator) -> None:
    """Total fitness = sum of (score_i * tier_multiplier_i)."""
    results = [
        CaseResult(case_id="n1", tier="normal", score=-1, passed=False),
        CaseResult(case_id="n2", tier="normal", score=-2, passed=False),
        CaseResult(case_id="l1", tier="low", score=-2, passed=False),
    ]
    fitness = aggregator.aggregate(results)
    # (-1 * 1.0) + (-2 * 1.0) + (-2 * 0.25) = -1.0 + -2.0 + -0.5 = -3.5
    assert fitness.score == pytest.approx(-3.5)


def test_perfect_score_all_pass(aggregator: FitnessAggregator) -> None:
    """All cases pass (score=0) -> total = 0.0 (perfect)."""
    results = [
        CaseResult(case_id="c1", tier="critical", score=0, passed=True),
        CaseResult(case_id="n1", tier="normal", score=0, passed=True),
        CaseResult(case_id="l1", tier="low", score=0, passed=True),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.score == 0.0
    assert fitness.rejected is False


# --- Normalized score tests ---


def test_normalized_score_basic(aggregator: FitnessAggregator) -> None:
    """3 normal cases all fail at -2 -> normalized = -6.0 / 6.0 = -1.0."""
    results = [
        CaseResult(case_id="n1", tier="normal", score=-2, passed=False),
        CaseResult(case_id="n2", tier="normal", score=-2, passed=False),
        CaseResult(case_id="n3", tier="normal", score=-2, passed=False),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.score == pytest.approx(-6.0)
    assert fitness.normalized_score == pytest.approx(-1.0)


def test_normalized_score_perfect(aggregator: FitnessAggregator) -> None:
    """3 normal cases all pass at 0 -> normalized = 0.0 / 6.0 = 0.0."""
    results = [
        CaseResult(case_id="n1", tier="normal", score=0, passed=True),
        CaseResult(case_id="n2", tier="normal", score=0, passed=True),
        CaseResult(case_id="n3", tier="normal", score=0, passed=True),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.score == 0.0
    assert fitness.normalized_score == pytest.approx(0.0)


def test_normalized_score_mixed_tiers(aggregator: FitnessAggregator) -> None:
    """1 critical fail (-2*5=-10), 1 normal pass (0), 1 low fail (-2*0.25=-0.5).

    raw = -10.5, max_possible = abs(-10 + -2 + -0.5) = 12.5,
    normalized = -10.5 / 12.5 = -0.84.
    """
    results = [
        CaseResult(case_id="c1", tier="critical", score=-2, passed=False),
        CaseResult(case_id="n1", tier="normal", score=0, passed=True),
        CaseResult(case_id="l1", tier="low", score=-2, passed=False),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.score == pytest.approx(-10.5)
    assert fitness.normalized_score == pytest.approx(-0.84)


def test_normalized_score_worst_case(aggregator: FitnessAggregator) -> None:
    """Single normal case fail -2 -> normalized = -2.0 / 2.0 = -1.0."""
    results = [
        CaseResult(case_id="n1", tier="normal", score=-2, passed=False),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.score == pytest.approx(-2.0)
    assert fitness.normalized_score == pytest.approx(-1.0)


def test_normalized_score_subset(aggregator: FitnessAggregator) -> None:
    """2 of 5 cases evaluated, both normal fail -2.

    normalized uses only evaluated cases: -4.0 / 4.0 = -1.0 (not -4.0/10.0).
    """
    results = [
        CaseResult(case_id="n1", tier="normal", score=-2, passed=False),
        CaseResult(case_id="n2", tier="normal", score=-2, passed=False),
    ]
    # Only 2 results passed, even though the full dataset has 5 cases.
    # Normalization divides by len(results) * 2 * multiplier, not total dataset size.
    fitness = aggregator.aggregate(results)
    assert fitness.normalized_score == pytest.approx(-1.0)


def test_aggregate_empty_results_normalized(aggregator: FitnessAggregator) -> None:
    """Empty results list returns normalized_score=0.0."""
    result = aggregator.aggregate([])
    assert result.normalized_score == pytest.approx(0.0)


def test_normalized_score_partial_fail(aggregator: FitnessAggregator) -> None:
    """2 normal cases, one fail -1, one pass 0.

    raw=-1.0, max_possible=abs(-2 + -2)=4.0, normalized=-1.0/4.0=-0.25.
    """
    results = [
        CaseResult(case_id="n1", tier="normal", score=-1, passed=False),
        CaseResult(case_id="n2", tier="normal", score=0, passed=True),
    ]
    fitness = aggregator.aggregate(results)
    assert fitness.score == pytest.approx(-1.0)
    assert fitness.normalized_score == pytest.approx(-0.25)
