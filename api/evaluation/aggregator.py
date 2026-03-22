"""Penalty-based fitness aggregator with tier multipliers.

Implements the penalty-based scoring model per the MindEvolution paper:
- Perfect fitness = 0.0 (no penalties, ceiling)
- Every violation adds a negative penalty
- Critical cases multiply their penalty by critical_multiplier (default 5.0)
- Normal cases keep their penalty as-is (multiplier 1.0)
- Low cases multiply their penalty by low_multiplier (default 0.25)

Total fitness = sum of all tier-weighted penalties. 0.0 = perfect.
"""

from api.evaluation.models import CaseResult, FitnessScore


class FitnessAggregator:
    """Aggregates per-case penalty scores into an overall fitness score.

    Uses tier multipliers where critical cases amplify penalties and
    low-priority cases dampen them, giving a smooth fitness landscape.

    Attributes:
        critical_multiplier: Multiplier for critical-tier penalties (default 5.0).
        normal_multiplier: Multiplier for normal-tier penalties (default 1.0).
        low_multiplier: Multiplier for low-tier penalties (default 0.25).
    """

    def __init__(
        self,
        critical_multiplier: float = 5.0,
        normal_multiplier: float = 1.0,
        low_multiplier: float = 0.25,
    ) -> None:
        self.critical_multiplier = critical_multiplier
        self.normal_multiplier = normal_multiplier
        self.low_multiplier = low_multiplier

    def aggregate(self, results: list[CaseResult]) -> FitnessScore:
        """Compute aggregate fitness from individual case penalty scores.

        Args:
            results: List of per-case evaluation results (scores <= 0).

        Returns:
            FitnessScore with summed tier-weighted penalties and backward-compat
            rejected flag (set when score < -10).
        """
        if not results:
            return FitnessScore(score=0.0, normalized_score=0.0, rejected=False, case_results=[])

        # Sum all case penalties with tier multipliers, and compute max possible penalty
        total = 0.0
        max_possible = 0.0
        for result in results:
            tier = result.tier.lower()
            if tier == "critical":
                multiplier = self.critical_multiplier
            elif tier == "low":
                multiplier = self.low_multiplier
            else:
                # "normal" and any unrecognized tier use normal_multiplier
                multiplier = self.normal_multiplier

            # Phase 33: halve multiplier for synthetic test cases (SYNTH-07)
            if result.synthetic:
                multiplier *= 0.5

            total += result.score * multiplier
            # Max penalty per case is -2 * multiplier (standard ExactMatch max penalty)
            max_possible += -2 * multiplier

        # Normalize: total / abs(max_possible), clamped to [-1.0, 0.0] range
        normalized = total / abs(max_possible) if max_possible != 0 else 0.0

        # Backward compat: set rejected from score threshold (uses raw total, NOT normalized)
        rejected = total < -10

        return FitnessScore(
            score=total,
            normalized_score=normalized,
            rejected=rejected,
            rejection_reason=f"Score {total:.1f} below rejection threshold" if rejected else None,
            case_results=results,
        )
