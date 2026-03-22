"""Tests for AdaptiveSampler -- streak tracking and exponential decay weights."""

import pytest

from api.dataset.models import TestCase
from api.evaluation.adaptive import AdaptiveSampler
from api.evaluation.models import CaseResult


def _make_result(case_id: str, passed: bool, score: float = 1.0) -> CaseResult:
    """Helper to create a CaseResult."""
    return CaseResult(case_id=case_id, score=score, passed=passed)


def _make_case(case_id: str) -> TestCase:
    """Helper to create a TestCase."""
    return TestCase(id=case_id)


# --- Streak tracking ---


def test_streak_tracking_increment() -> None:
    """update() with all-passing results increments pass streaks."""
    sampler = AdaptiveSampler()
    results = [
        _make_result("c1", passed=True),
        _make_result("c2", passed=True),
    ]

    sampler.update(results)
    assert sampler.pass_streaks["c1"] == 1
    assert sampler.pass_streaks["c2"] == 1

    sampler.update(results)
    assert sampler.pass_streaks["c1"] == 2
    assert sampler.pass_streaks["c2"] == 2


def test_streak_tracking_reset_on_fail() -> None:
    """update() resets streak to 0 for failing cases."""
    sampler = AdaptiveSampler()

    # Build up streaks
    passing = [_make_result("c1", passed=True), _make_result("c2", passed=True)]
    sampler.update(passing)
    sampler.update(passing)
    assert sampler.pass_streaks["c1"] == 2

    # c1 fails, c2 still passes
    mixed = [_make_result("c1", passed=False), _make_result("c2", passed=True)]
    sampler.update(mixed)
    assert sampler.pass_streaks["c1"] == 0
    assert sampler.pass_streaks["c2"] == 3


# --- Weight decay formula ---


def test_weight_decay_formula() -> None:
    """Weight formula: max(min_rate, 1.0 / (1.0 + streak / decay_constant))."""
    sampler = AdaptiveSampler(decay_constant=3.0, min_rate=0.1)
    cases = [_make_case("c0"), _make_case("c3"), _make_case("c9")]

    # Manually set streaks
    sampler._pass_streaks["c0"] = 0
    sampler._pass_streaks["c3"] = 3
    sampler._pass_streaks["c9"] = 9

    weights = sampler.get_weights(cases)

    # streak=0 -> 1.0 / (1.0 + 0/3.0) = 1.0
    assert weights["c0"] == pytest.approx(1.0)
    # streak=3 -> 1.0 / (1.0 + 3/3.0) = 0.5
    assert weights["c3"] == pytest.approx(0.5)
    # streak=9 -> 1.0 / (1.0 + 9/3.0) = 0.25
    assert weights["c9"] == pytest.approx(0.25)


def test_min_rate_floor() -> None:
    """Very high streak still returns min_rate, not 0."""
    sampler = AdaptiveSampler(decay_constant=3.0, min_rate=0.1)
    cases = [_make_case("c1")]

    # streak=1000 -> 1.0 / (1.0 + 1000/3.0) ~ 0.003 -> clamped to 0.1
    sampler._pass_streaks["c1"] = 1000

    weights = sampler.get_weights(cases)
    assert weights["c1"] == pytest.approx(0.1)


def test_reset_case() -> None:
    """reset_case() sets streak to 0."""
    sampler = AdaptiveSampler()
    sampler._pass_streaks["c1"] = 10

    sampler.reset_case("c1")
    assert sampler.pass_streaks["c1"] == 0


def test_get_weights_unknown_case() -> None:
    """Case not in streaks gets weight 1.0 (always sample)."""
    sampler = AdaptiveSampler()
    cases = [_make_case("unknown")]

    weights = sampler.get_weights(cases)
    assert weights["unknown"] == pytest.approx(1.0)
