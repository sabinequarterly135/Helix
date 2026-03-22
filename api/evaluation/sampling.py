"""Sampling strategies for dataset evaluation cost control.

Provides two modes:
- full: Evaluate all cases (no filtering)
- smart_subset: Always include critical + failing, random sample of passing

The smart_subset strategy optimizes evaluation cost during iterative evolution
by focusing on the most informative cases.
"""

import math
import random

from api.dataset.models import TestCase
from api.evaluation.models import CaseResult


class SamplingStrategy:
    """Static methods for selecting which test cases to evaluate.

    Supports full evaluation (all cases) and smart_subset mode that
    prioritizes critical and failing cases while sampling passing ones.
    """

    @staticmethod
    def full(cases: list[TestCase]) -> list[TestCase]:
        """Return all cases for full evaluation.

        Args:
            cases: All available test cases.

        Returns:
            All cases unchanged.
        """
        return list(cases)

    @staticmethod
    def smart_subset(
        cases: list[TestCase],
        previous_results: list[CaseResult] | None = None,
        sample_size: int | None = None,
        sample_ratio: float | None = None,
        adaptive_weights: dict[str, float] | None = None,
    ) -> list[TestCase]:
        """Select a smart subset of cases for cost-efficient evaluation.

        Always includes:
        - All critical-tier cases
        - All previously-failing cases

        Randomly samples from passing non-critical cases using either
        sample_size (fixed count), sample_ratio (proportion), or
        default 25%.

        When adaptive_weights is provided, uses weighted random.choices
        instead of uniform random.sample for passing non-critical cases.
        This makes well-solved cases (high streak = low weight) less
        likely to be sampled, reducing redundant evaluations.

        Args:
            cases: All available test cases.
            previous_results: Results from the previous evaluation run.
            sample_size: Fixed number of passing cases to sample.
            sample_ratio: Fraction of passing cases to sample (0.0-1.0).
            adaptive_weights: Optional per-case sampling weights from
                AdaptiveSampler.get_weights(). Keys are case IDs,
                values are floats in [min_rate, 1.0].

        Returns:
            Subset of cases to evaluate.
        """
        if previous_results is None:
            return list(cases)

        # Build set of failing case IDs from previous results
        failing_ids: set[str] = {r.case_id for r in previous_results if not r.passed}

        # Partition cases into categories
        critical_ids: set[str] = set()
        failing_noncritical_ids: set[str] = set()
        passing_noncritical_ids: list[str] = []

        for case in cases:
            if case.tier.value == "critical":
                critical_ids.add(case.id)
            elif case.id in failing_ids:
                failing_noncritical_ids.add(case.id)
            else:
                passing_noncritical_ids.append(case.id)

        # Determine sample count for passing non-critical cases
        n_passing = len(passing_noncritical_ids)
        if sample_size is not None:
            n_sample = min(sample_size, n_passing)
        elif sample_ratio is not None:
            n_sample = min(math.ceil(sample_ratio * n_passing), n_passing)
        else:
            # Default: 25% of passing non-critical
            n_sample = min(math.ceil(0.25 * n_passing), n_passing)

        # Random sample from passing non-critical
        sampled_ids: set[str]
        if n_sample >= n_passing:
            sampled_ids = set(passing_noncritical_ids)
        elif adaptive_weights and n_sample > 0:
            # Weighted sampling: cases with lower adaptive weight are
            # less likely to be picked.  random.choices samples with
            # replacement so we deduplicate in a loop.
            weights = [adaptive_weights.get(cid, 1.0) for cid in passing_noncritical_ids]
            collected: set[str] = set()
            while len(collected) < n_sample and len(collected) < n_passing:
                picks = random.choices(passing_noncritical_ids, weights=weights, k=n_sample)
                collected.update(picks)
            # Trim if we oversampled due to dedup loop
            sampled_ids = set(list(collected)[:n_sample])
        else:
            sampled_ids = set(random.sample(passing_noncritical_ids, n_sample))

        # Combine with deduplication (set union)
        selected_ids = critical_ids | failing_noncritical_ids | sampled_ids

        # Preserve original order
        result = [case for case in cases if case.id in selected_ids]
        return result
