"""Tests for SamplingStrategy -- full and smart_subset sampling modes."""

from api.dataset.models import PriorityTier, TestCase
from api.evaluation.models import CaseResult
from api.evaluation.sampling import SamplingStrategy


def _make_case(case_id: str, tier: PriorityTier = PriorityTier.NORMAL) -> TestCase:
    """Helper to create a TestCase with a specific ID and tier."""
    return TestCase(id=case_id, tier=tier)


def _make_result(case_id: str, passed: bool, score: float = 1.0) -> CaseResult:
    """Helper to create a CaseResult with a specific ID and pass/fail status."""
    return CaseResult(case_id=case_id, score=score, passed=passed)


# --- SamplingStrategy.full ---


def test_full_returns_all_cases() -> None:
    """full() returns all cases unchanged."""
    cases = [_make_case("c1"), _make_case("c2"), _make_case("c3")]
    result = SamplingStrategy.full(cases)
    assert len(result) == 3
    assert result == cases


def test_full_empty_list() -> None:
    """full() with empty list returns empty list."""
    result = SamplingStrategy.full([])
    assert result == []


# --- SamplingStrategy.smart_subset: no previous results ---


def test_smart_subset_no_previous_results() -> None:
    """smart_subset with no previous_results returns all cases."""
    cases = [_make_case("c1"), _make_case("c2")]
    result = SamplingStrategy.smart_subset(cases)
    assert len(result) == 2


# --- SamplingStrategy.smart_subset: critical always included ---


def test_smart_subset_includes_all_critical() -> None:
    """smart_subset always includes all critical-tier cases."""
    cases = [
        _make_case("crit1", PriorityTier.CRITICAL),
        _make_case("crit2", PriorityTier.CRITICAL),
        _make_case("n1", PriorityTier.NORMAL),
        _make_case("n2", PriorityTier.NORMAL),
        _make_case("n3", PriorityTier.NORMAL),
        _make_case("n4", PriorityTier.NORMAL),
    ]
    previous_results = [
        _make_result("crit1", passed=True),
        _make_result("crit2", passed=True),
        _make_result("n1", passed=True),
        _make_result("n2", passed=True),
        _make_result("n3", passed=True),
        _make_result("n4", passed=True),
    ]
    result = SamplingStrategy.smart_subset(cases, previous_results, sample_size=0)
    result_ids = {c.id for c in result}
    assert "crit1" in result_ids
    assert "crit2" in result_ids


# --- SamplingStrategy.smart_subset: failing always included ---


def test_smart_subset_includes_all_failing() -> None:
    """smart_subset always includes all previously-failing cases."""
    cases = [
        _make_case("n1"),
        _make_case("n2"),
        _make_case("n3"),
        _make_case("n4"),
    ]
    previous_results = [
        _make_result("n1", passed=False),
        _make_result("n2", passed=False),
        _make_result("n3", passed=True),
        _make_result("n4", passed=True),
    ]
    result = SamplingStrategy.smart_subset(cases, previous_results, sample_size=0)
    result_ids = {c.id for c in result}
    assert "n1" in result_ids
    assert "n2" in result_ids


# --- SamplingStrategy.smart_subset: sample_size ---


def test_smart_subset_with_sample_size() -> None:
    """smart_subset with sample_size=N samples N passing cases."""
    cases = [
        _make_case("crit1", PriorityTier.CRITICAL),
        _make_case("n1"),
        _make_case("n2"),
        _make_case("n3"),
        _make_case("n4"),
        _make_case("n5"),
    ]
    previous_results = [
        _make_result("crit1", passed=True),
        _make_result("n1", passed=True),
        _make_result("n2", passed=True),
        _make_result("n3", passed=True),
        _make_result("n4", passed=True),
        _make_result("n5", passed=True),
    ]
    result = SamplingStrategy.smart_subset(cases, previous_results, sample_size=2)
    # Should include: 1 critical + 2 sampled passing = 3
    assert len(result) == 3
    result_ids = {c.id for c in result}
    assert "crit1" in result_ids


# --- SamplingStrategy.smart_subset: sample_ratio ---


def test_smart_subset_with_sample_ratio() -> None:
    """smart_subset with sample_ratio=R samples R proportion of passing cases."""
    cases = [
        _make_case("n1"),
        _make_case("n2"),
        _make_case("n3"),
        _make_case("n4"),
    ]
    previous_results = [
        _make_result("n1", passed=True),
        _make_result("n2", passed=True),
        _make_result("n3", passed=True),
        _make_result("n4", passed=True),
    ]
    # 50% of 4 passing = 2 sampled
    result = SamplingStrategy.smart_subset(cases, previous_results, sample_ratio=0.5)
    assert len(result) == 2


# --- SamplingStrategy.smart_subset: default sampling ---


def test_smart_subset_default_25_percent() -> None:
    """smart_subset default sampling is 25% of passing non-critical cases."""
    # 20 passing normal cases -> 25% = 5 sampled
    cases = [_make_case(f"n{i}") for i in range(20)]
    previous_results = [_make_result(f"n{i}", passed=True) for i in range(20)]
    result = SamplingStrategy.smart_subset(cases, previous_results)
    assert len(result) == 5


# --- SamplingStrategy.smart_subset: deduplication ---


def test_smart_subset_deduplicates() -> None:
    """A critical case that also failed is only included once."""
    cases = [
        _make_case("crit1", PriorityTier.CRITICAL),
        _make_case("n1"),
    ]
    previous_results = [
        _make_result("crit1", passed=False),  # both critical AND failing
        _make_result("n1", passed=True),
    ]
    result = SamplingStrategy.smart_subset(cases, previous_results, sample_size=0)
    result_ids = [c.id for c in result]
    # crit1 should appear exactly once (not twice)
    assert result_ids.count("crit1") == 1
    assert len(result) == 1  # Only crit1 (n1 is passing and sample_size=0)


# --- SamplingStrategy.smart_subset: combined scenario ---


def test_smart_subset_combined_scenario() -> None:
    """Full scenario: critical + failing + sampled passing."""
    cases = [
        _make_case("crit1", PriorityTier.CRITICAL),
        _make_case("fail1"),
        _make_case("fail2"),
        _make_case("pass1"),
        _make_case("pass2"),
        _make_case("pass3"),
        _make_case("pass4"),
        _make_case("pass5"),
        _make_case("pass6"),
        _make_case("pass7"),
        _make_case("pass8"),
    ]
    previous_results = [
        _make_result("crit1", passed=True),
        _make_result("fail1", passed=False),
        _make_result("fail2", passed=False),
        _make_result("pass1", passed=True),
        _make_result("pass2", passed=True),
        _make_result("pass3", passed=True),
        _make_result("pass4", passed=True),
        _make_result("pass5", passed=True),
        _make_result("pass6", passed=True),
        _make_result("pass7", passed=True),
        _make_result("pass8", passed=True),
    ]
    # 8 passing non-critical, default 25% -> 2 sampled
    # total = 1 critical + 2 failing + 2 sampled = 5
    result = SamplingStrategy.smart_subset(cases, previous_results)
    assert len(result) == 5
    result_ids = {c.id for c in result}
    assert "crit1" in result_ids
    assert "fail1" in result_ids
    assert "fail2" in result_ids


# --- SamplingStrategy.smart_subset: adaptive_weights ---


def test_smart_subset_with_adaptive_weights() -> None:
    """smart_subset with adaptive_weights uses weighted sampling.

    Low-weight cases should appear less frequently than high-weight cases
    over many iterations.
    """
    cases = [
        _make_case("crit1", PriorityTier.CRITICAL),
        _make_case("p1"),
        _make_case("p2"),
        _make_case("p3"),
        _make_case("p4"),
    ]
    previous_results = [
        _make_result("crit1", passed=True),
        _make_result("p1", passed=True),
        _make_result("p2", passed=True),
        _make_result("p3", passed=True),
        _make_result("p4", passed=True),
    ]

    # p1 has very low weight (rarely sampled), p2/p3/p4 have normal weight
    adaptive_weights = {"p1": 0.01, "p2": 1.0, "p3": 1.0, "p4": 1.0}

    # Run 200 iterations and count how often p1 appears
    p1_count = 0
    p2_count = 0
    for _ in range(200):
        result = SamplingStrategy.smart_subset(
            cases,
            previous_results,
            sample_size=2,
            adaptive_weights=adaptive_weights,
        )
        result_ids = {c.id for c in result}
        if "p1" in result_ids:
            p1_count += 1
        if "p2" in result_ids:
            p2_count += 1

    # p1 (weight=0.01) should appear much less than p2 (weight=1.0)
    assert p1_count < p2_count, (
        f"Low-weight p1 appeared {p1_count} times, normal-weight p2 appeared {p2_count} times"
    )


def test_smart_subset_without_adaptive_weights_unchanged() -> None:
    """smart_subset without adaptive_weights behaves identically to before."""
    cases = [
        _make_case("n1"),
        _make_case("n2"),
        _make_case("n3"),
        _make_case("n4"),
    ]
    previous_results = [
        _make_result("n1", passed=True),
        _make_result("n2", passed=True),
        _make_result("n3", passed=True),
        _make_result("n4", passed=True),
    ]
    # Without adaptive_weights, uses random.sample (uniform)
    result = SamplingStrategy.smart_subset(cases, previous_results, sample_size=2)
    assert len(result) == 2
    # All returned cases should be from the original set
    result_ids = {c.id for c in result}
    assert result_ids.issubset({"n1", "n2", "n3", "n4"})
