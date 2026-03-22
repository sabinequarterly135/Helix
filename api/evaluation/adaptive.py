"""Adaptive test case sampler for evolution cost reduction.

Tracks consecutive pass streaks per test case and computes exponential
decay weights.  Cases that keep passing get sampled less frequently,
reducing redundant API calls by 2-5x while periodic checkpoint generations
maintain full regression coverage.

The weights integrate into SamplingStrategy.smart_subset() via its
adaptive_weights parameter -- a single code path, not stacked filters.
"""

from __future__ import annotations

from api.dataset.models import TestCase
from api.evaluation.models import CaseResult


class AdaptiveSampler:
    """Tracks per-case pass streaks and computes decay-based sampling weights.

    Weight formula: max(min_rate, 1.0 / (1.0 + streak / decay_constant))
    - streak=0 -> weight=1.0 (always sample)
    - streak=3 (dc=3.0) -> weight=0.5
    - streak=9 (dc=3.0) -> weight=0.25
    - Very high streak -> clamped to min_rate

    Args:
        decay_constant: Controls how quickly weights decay with streak length.
            Higher values mean slower decay. Must be > 0.
        min_rate: Floor for sampling weight. Even high-streak cases are
            sampled at least this often. Must be in [0.0, 1.0].
    """

    def __init__(self, decay_constant: float = 3.0, min_rate: float = 0.1) -> None:
        self._decay_constant = decay_constant
        self._min_rate = min_rate
        self._pass_streaks: dict[str, int] = {}

    def update(self, results: list[CaseResult]) -> None:
        """Update pass streaks from evaluation results.

        Increments streak for passing cases, resets to 0 for failing ones.

        Args:
            results: Case results from the latest evaluation.
        """
        for r in results:
            if r.passed:
                self._pass_streaks[r.case_id] = self._pass_streaks.get(r.case_id, 0) + 1
            else:
                self._pass_streaks[r.case_id] = 0

    def get_weights(self, cases: list[TestCase]) -> dict[str, float]:
        """Compute sampling weights for the given cases.

        Cases not in the streak tracker get weight 1.0 (always sample).

        Args:
            cases: Test cases to compute weights for.

        Returns:
            Mapping of case_id -> sampling weight in [min_rate, 1.0].
        """
        weights: dict[str, float] = {}
        for case in cases:
            streak = self._pass_streaks.get(case.id, 0)
            raw_weight = 1.0 / (1.0 + streak / self._decay_constant)
            weights[case.id] = max(self._min_rate, raw_weight)
        return weights

    def reset_case(self, case_id: str) -> None:
        """Reset a case's streak to 0 (e.g., on checkpoint failure).

        Args:
            case_id: The case whose streak should be reset.
        """
        self._pass_streaks[case_id] = 0

    @property
    def pass_streaks(self) -> dict[str, int]:
        """Read-only copy of the internal pass streaks."""
        return dict(self._pass_streaks)
