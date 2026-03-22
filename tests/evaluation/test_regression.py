"""Tests for RegressionAnalyzer -- detects regressions between baseline and current results."""

import pytest

from api.evaluation.models import CaseResult
from api.evaluation.regression import (
    Regression,
    RegressionAnalyzer,
    RegressionReport,
)


@pytest.fixture
def analyzer() -> RegressionAnalyzer:
    """Default regression analyzer."""
    return RegressionAnalyzer()


# --- Basic regression detection ---


def test_detects_regression(analyzer: RegressionAnalyzer) -> None:
    """Case passing in baseline but failing in current is a regression."""
    baseline = [
        CaseResult(case_id="c1", tier="normal", score=1.0, passed=True),
    ]
    current = [
        CaseResult(case_id="c1", tier="normal", score=0.0, passed=False),
    ]
    report = analyzer.analyze(current=current, baseline=baseline)
    assert isinstance(report, RegressionReport)
    assert report.regression_count == 1
    assert len(report.regressions) == 1
    reg = report.regressions[0]
    assert isinstance(reg, Regression)
    assert reg.case_id == "c1"
    assert reg.tier == "normal"
    assert reg.baseline_score == 1.0
    assert reg.current_score == 0.0
    assert reg.delta == pytest.approx(-1.0)


def test_detects_multiple_regressions(analyzer: RegressionAnalyzer) -> None:
    """Multiple cases regressing are all reported."""
    baseline = [
        CaseResult(case_id="c1", tier="normal", score=1.0, passed=True),
        CaseResult(case_id="c2", tier="critical", score=1.0, passed=True),
        CaseResult(case_id="c3", tier="low", score=0.8, passed=True),
    ]
    current = [
        CaseResult(case_id="c1", tier="normal", score=0.2, passed=False),
        CaseResult(case_id="c2", tier="critical", score=0.0, passed=False),
        CaseResult(case_id="c3", tier="low", score=0.8, passed=True),  # not regressed
    ]
    report = analyzer.analyze(current=current, baseline=baseline)
    assert report.regression_count == 2
    regressed_ids = {r.case_id for r in report.regressions}
    assert regressed_ids == {"c1", "c2"}


# --- Critical regressions flagged ---


def test_has_critical_regressions(analyzer: RegressionAnalyzer) -> None:
    """Reports has_critical_regressions when a critical-tier case regresses."""
    baseline = [
        CaseResult(case_id="c1", tier="critical", score=1.0, passed=True),
    ]
    current = [
        CaseResult(case_id="c1", tier="critical", score=0.0, passed=False),
    ]
    report = analyzer.analyze(current=current, baseline=baseline)
    assert report.has_critical_regressions is True


def test_no_critical_regressions(analyzer: RegressionAnalyzer) -> None:
    """has_critical_regressions is False when only normal/low cases regress."""
    baseline = [
        CaseResult(case_id="c1", tier="normal", score=1.0, passed=True),
    ]
    current = [
        CaseResult(case_id="c1", tier="normal", score=0.0, passed=False),
    ]
    report = analyzer.analyze(current=current, baseline=baseline)
    assert report.has_critical_regressions is False


# --- Non-regression cases ---


def test_new_case_not_flagged(analyzer: RegressionAnalyzer) -> None:
    """New cases in current (not in baseline) are not flagged as regressions."""
    baseline = [
        CaseResult(case_id="c1", tier="normal", score=1.0, passed=True),
    ]
    current = [
        CaseResult(case_id="c1", tier="normal", score=1.0, passed=True),
        CaseResult(case_id="c2", tier="normal", score=0.0, passed=False),  # new
    ]
    report = analyzer.analyze(current=current, baseline=baseline)
    assert report.regression_count == 0


def test_improved_case_not_flagged(analyzer: RegressionAnalyzer) -> None:
    """Cases that improved (were failing, now passing) are not regressions."""
    baseline = [
        CaseResult(case_id="c1", tier="normal", score=0.0, passed=False),
    ]
    current = [
        CaseResult(case_id="c1", tier="normal", score=1.0, passed=True),
    ]
    report = analyzer.analyze(current=current, baseline=baseline)
    assert report.regression_count == 0


# --- Edge cases ---


def test_empty_baseline(analyzer: RegressionAnalyzer) -> None:
    """Empty baseline returns 0 regressions."""
    current = [
        CaseResult(case_id="c1", tier="normal", score=0.0, passed=False),
    ]
    report = analyzer.analyze(current=current, baseline=[])
    assert report.regression_count == 0
    assert report.regressions == []


def test_empty_current(analyzer: RegressionAnalyzer) -> None:
    """Empty current returns 0 regressions."""
    baseline = [
        CaseResult(case_id="c1", tier="normal", score=1.0, passed=True),
    ]
    report = analyzer.analyze(current=[], baseline=baseline)
    assert report.regression_count == 0


def test_both_empty(analyzer: RegressionAnalyzer) -> None:
    """Both empty returns 0 regressions."""
    report = analyzer.analyze(current=[], baseline=[])
    assert report.regression_count == 0
    assert report.has_critical_regressions is False


def test_total_cases_in_report(analyzer: RegressionAnalyzer) -> None:
    """Report includes total_cases from current results."""
    baseline = [
        CaseResult(case_id="c1", tier="normal", score=1.0, passed=True),
    ]
    current = [
        CaseResult(case_id="c1", tier="normal", score=1.0, passed=True),
        CaseResult(case_id="c2", tier="normal", score=0.5, passed=True),
    ]
    report = analyzer.analyze(current=current, baseline=baseline)
    assert report.total_cases == 2
