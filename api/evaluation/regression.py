"""Regression analysis for detecting cases that regressed between evaluation runs.

Compares current evaluation results against a baseline to identify cases that were
previously passing but are now failing. Reports both the count and details of
regressions, with a flag for critical-tier regressions.
"""

from pydantic import BaseModel

from api.evaluation.models import CaseResult


class Regression(BaseModel):
    """A single regression: a case that was passing but is now failing.

    Attributes:
        case_id: The ID of the regressed case.
        tier: Priority tier of the case ("critical", "normal", "low").
        baseline_score: Score in the baseline evaluation.
        current_score: Score in the current evaluation.
        delta: Change in score (current - baseline, negative means regression).
    """

    case_id: str
    tier: str
    baseline_score: float
    current_score: float
    delta: float


class RegressionReport(BaseModel):
    """Summary of regression analysis between baseline and current results.

    Attributes:
        total_cases: Total number of cases in the current evaluation.
        regressions: List of individual regression entries.
        regression_count: Number of regressions detected.
        has_critical_regressions: Whether any critical-tier case regressed.
    """

    total_cases: int
    regressions: list[Regression]
    regression_count: int
    has_critical_regressions: bool


class RegressionAnalyzer:
    """Analyzes evaluation results for regressions against a baseline.

    A regression is defined as a case that was passing in the baseline
    but is now failing in the current results. New cases (not present
    in the baseline) and improved cases are not flagged.
    """

    def analyze(
        self,
        current: list[CaseResult],
        baseline: list[CaseResult],
    ) -> RegressionReport:
        """Compare current results against baseline to detect regressions.

        Args:
            current: Current evaluation results.
            baseline: Previous (baseline) evaluation results.

        Returns:
            RegressionReport with details of any detected regressions.
        """
        # Build lookup from baseline: case_id -> CaseResult
        baseline_map: dict[str, CaseResult] = {r.case_id: r for r in baseline}

        regressions: list[Regression] = []

        for result in current:
            baseline_result = baseline_map.get(result.case_id)
            if baseline_result is None:
                # New case -- not a regression
                continue
            if baseline_result.passed and not result.passed:
                # Was passing, now failing -- this is a regression
                regressions.append(
                    Regression(
                        case_id=result.case_id,
                        tier=result.tier,
                        baseline_score=baseline_result.score,
                        current_score=result.score,
                        delta=result.score - baseline_result.score,
                    )
                )

        has_critical = any(r.tier.lower() == "critical" for r in regressions)

        return RegressionReport(
            total_cases=len(current),
            regressions=regressions,
            regression_count=len(regressions),
            has_critical_regressions=has_critical,
        )
