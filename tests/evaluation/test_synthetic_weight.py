"""Tests for synthetic weight support in CaseResult and FitnessAggregator.

Covers:
- CaseResult.synthetic field (defaults to False)
- FitnessAggregator applies 0.5x multiplier when result.synthetic is True
- Non-synthetic results unchanged (regression guard)
- Mixed synthetic + non-synthetic produces correct weighted sum
- Normalized score denominator accounts for synthetic weight adjustment
"""

import pytest

from api.evaluation.aggregator import FitnessAggregator
from api.evaluation.models import CaseResult


@pytest.fixture
def aggregator() -> FitnessAggregator:
    """Default aggregator with standard multipliers."""
    return FitnessAggregator()


# --- CaseResult.synthetic field ---


class TestCaseResultSyntheticField:
    """Tests for the CaseResult.synthetic field."""

    def test_synthetic_defaults_false(self) -> None:
        """CaseResult.synthetic defaults to False."""
        result = CaseResult(case_id="c1", score=-1.0)
        assert result.synthetic is False

    def test_synthetic_set_true(self) -> None:
        """CaseResult.synthetic can be set to True."""
        result = CaseResult(case_id="c1", score=-1.0, synthetic=True)
        assert result.synthetic is True


# --- Non-synthetic regression guard ---


class TestNonSyntheticRegression:
    """Ensure non-synthetic results behave exactly as before."""

    def test_all_non_synthetic_same_as_before(self, aggregator: FitnessAggregator) -> None:
        """All non-synthetic results produce same fitness as before (regression guard)."""
        results = [
            CaseResult(case_id="c1", tier="critical", score=-2.0, synthetic=False),
            CaseResult(case_id="c2", tier="normal", score=-1.0, synthetic=False),
            CaseResult(case_id="c3", tier="low", score=-0.5, synthetic=False),
        ]
        fitness = aggregator.aggregate(results)
        # critical: -2.0 * 5.0 = -10.0
        # normal:   -1.0 * 1.0 = -1.0
        # low:      -0.5 * 0.25 = -0.125
        # total = -11.125
        expected_total = -2.0 * 5.0 + -1.0 * 1.0 + -0.5 * 0.25
        assert fitness.score == pytest.approx(expected_total)

    def test_non_synthetic_without_field(self, aggregator: FitnessAggregator) -> None:
        """Results without explicit synthetic field (defaults to False) work correctly."""
        results = [
            CaseResult(case_id="c1", tier="normal", score=-1.5),
        ]
        fitness = aggregator.aggregate(results)
        assert fitness.score == pytest.approx(-1.5 * 1.0)


# --- Synthetic weight application ---


class TestSyntheticWeight:
    """Tests for the 0.5x synthetic multiplier in aggregator."""

    def test_synthetic_critical_gets_half_weight(self, aggregator: FitnessAggregator) -> None:
        """Synthetic critical case gets 5.0 * 0.5 = 2.5x multiplier."""
        results = [
            CaseResult(case_id="c1", tier="critical", score=-2.0, synthetic=True),
        ]
        fitness = aggregator.aggregate(results)
        # critical multiplier 5.0 * synthetic 0.5 = 2.5
        # -2.0 * 2.5 = -5.0
        assert fitness.score == pytest.approx(-5.0)

    def test_synthetic_normal_gets_half_weight(self, aggregator: FitnessAggregator) -> None:
        """Synthetic normal case gets 1.0 * 0.5 = 0.5x multiplier."""
        results = [
            CaseResult(case_id="c1", tier="normal", score=-2.0, synthetic=True),
        ]
        fitness = aggregator.aggregate(results)
        # normal multiplier 1.0 * synthetic 0.5 = 0.5
        # -2.0 * 0.5 = -1.0
        assert fitness.score == pytest.approx(-1.0)

    def test_synthetic_low_gets_half_weight(self, aggregator: FitnessAggregator) -> None:
        """Synthetic low case gets 0.25 * 0.5 = 0.125x multiplier."""
        results = [
            CaseResult(case_id="c1", tier="low", score=-2.0, synthetic=True),
        ]
        fitness = aggregator.aggregate(results)
        # low multiplier 0.25 * synthetic 0.5 = 0.125
        # -2.0 * 0.125 = -0.25
        assert fitness.score == pytest.approx(-0.25)


# --- Mixed synthetic + non-synthetic ---


class TestMixedSyntheticWeight:
    """Tests for mixed synthetic and non-synthetic results."""

    def test_mixed_results_correct_weighted_sum(self, aggregator: FitnessAggregator) -> None:
        """Mix of synthetic and non-synthetic results produces correct weighted sum."""
        results = [
            # Non-synthetic critical: -2.0 * 5.0 = -10.0
            CaseResult(case_id="c1", tier="critical", score=-2.0, synthetic=False),
            # Synthetic normal: -1.0 * 1.0 * 0.5 = -0.5
            CaseResult(case_id="c2", tier="normal", score=-1.0, synthetic=True),
            # Non-synthetic normal: -1.0 * 1.0 = -1.0
            CaseResult(case_id="c3", tier="normal", score=-1.0, synthetic=False),
        ]
        fitness = aggregator.aggregate(results)
        expected = -10.0 + -0.5 + -1.0
        assert fitness.score == pytest.approx(expected)

    def test_normalized_score_with_synthetic(self, aggregator: FitnessAggregator) -> None:
        """Normalized score denominator includes synthetic weight adjustment."""
        results = [
            # Non-synthetic critical: score=-2, multiplier=5.0
            #   total += -2 * 5.0 = -10.0,  max_possible += -2 * 5.0 = -10.0
            CaseResult(case_id="c1", tier="critical", score=-2.0, synthetic=False),
            # Synthetic normal: score=-2, multiplier=1.0*0.5=0.5
            #   total += -2 * 0.5 = -1.0,  max_possible += -2 * 0.5 = -1.0
            CaseResult(case_id="c2", tier="normal", score=-2.0, synthetic=True),
        ]
        fitness = aggregator.aggregate(results)

        # total = -10.0 + -1.0 = -11.0
        # max_possible = -10.0 + -1.0 = -11.0
        # normalized = -11.0 / abs(-11.0) = -1.0
        assert fitness.score == pytest.approx(-11.0)
        assert fitness.normalized_score == pytest.approx(-1.0)

    def test_partial_failure_normalized_with_synthetic(self, aggregator: FitnessAggregator) -> None:
        """Partial failure normalized score correctly with synthetic weight."""
        results = [
            # Non-synthetic normal: score=-1, multiplier=1.0
            #   total += -1, max_possible += -2
            CaseResult(case_id="c1", tier="normal", score=-1.0, synthetic=False),
            # Synthetic normal: score=0 (passed), multiplier=0.5
            #   total += 0, max_possible += -1
            CaseResult(case_id="c2", tier="normal", score=0.0, synthetic=True),
        ]
        fitness = aggregator.aggregate(results)

        # total = -1.0 + 0.0 = -1.0
        # max_possible = -2.0 + -1.0 = -3.0
        # normalized = -1.0 / abs(-3.0) = -0.333...
        assert fitness.score == pytest.approx(-1.0)
        assert fitness.normalized_score == pytest.approx(-1.0 / 3.0)
