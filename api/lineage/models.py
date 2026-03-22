"""Lineage event data model for tracking candidate ancestry.

LineageEvent records a single candidate's parentage, fitness outcome,
and mutation type during evolutionary optimization.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LineageEvent(BaseModel):
    """A single lineage record for one candidate in the evolution process.

    Attributes:
        candidate_id: Unique identifier for this candidate.
        parent_ids: IDs of parent candidates (empty for seed/fresh).
        generation: Generation number when this candidate was created.
        island: Island index where this candidate lives.
        fitness_score: Evaluated fitness (<= 0.0). 0.0 = perfect, negative = penalized.
        rejected: Deprecated: use score magnitude instead. Kept for backward compat
            with renderer visual styling.
        mutation_type: How this candidate was produced. One of:
            "rcc", "structural", "fresh", "seed", "migrated", "reset".
        survived: Whether this candidate survived population management.
    """

    candidate_id: str
    parent_ids: list[str] = Field(default_factory=list)
    generation: int
    island: int = 0
    fitness_score: float = 0.0
    normalized_score: float = 0.0
    rejected: bool = False
    mutation_type: str = "rcc"
    survived: bool = True
    template: str | None = None
