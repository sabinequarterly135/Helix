"""Boltzmann tournament selection for evolutionary prompt optimization.

Uses a numerically stable softmax to compute selection probabilities
from candidate fitness scores, with configurable temperature for
exploration-exploitation balance.
"""

from __future__ import annotations

import math
import random

from api.evolution.models import Candidate


class BoltzmannSelector:
    """Selects parent candidates using Boltzmann tournament selection.

    Higher temperature produces more uniform (exploratory) selection.
    Lower temperature produces more greedy (exploitative) selection.
    Uses numerically stable softmax: subtract max fitness before exp()
    to prevent overflow for any temperature > 0.
    """

    def select(
        self,
        candidates: list[Candidate],
        n_parents: int,
        temperature: float,
    ) -> list[Candidate]:
        """Select n_parents candidates via Boltzmann-weighted sampling.

        Args:
            candidates: Population of evaluated candidates.
            n_parents: Number of parents to select (with replacement).
            temperature: Boltzmann temperature. Higher = more random,
                lower = more greedy toward high fitness.

        Returns:
            List of selected parent candidates. Empty if no viable
            candidates or n_parents <= 0.
        """
        if not candidates or n_parents <= 0:
            return []

        # All candidates participate in selection (no rejected filtering)
        # Numerically stable softmax: subtract max to avoid exp() overflow
        fitnesses = [c.fitness_score for c in candidates]
        max_f = max(fitnesses)
        weights = [math.exp((f - max_f) / temperature) for f in fitnesses]

        # Weighted sampling with replacement
        selected = random.choices(candidates, weights=weights, k=n_parents)
        return selected
