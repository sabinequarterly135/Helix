"""Evolution data models for the prompt optimization pipeline.

Defines the core value objects used throughout the evolution sub-package:
- Candidate: an evolved prompt template with its fitness evaluation
- EvolutionConfig: all hyperparameters with Mind Evolution paper defaults
- GenerationRecord: per-generation metrics
- EvolutionResult: final evolution output with termination reason
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from api.evaluation.models import EvaluationReport
from api.types import OTelAttributes


class Candidate(BaseModel):
    """An evolved prompt candidate with its fitness evaluation.

    Candidates are immutable value objects -- create new instances
    rather than mutating in place to preserve lineage tracking.

    Attributes:
        id: Unique identifier (auto-generated UUID string).
        template: The Jinja2 prompt template text.
        fitness_score: Aggregate fitness score (<= 0.0). 0.0 = perfect, negative = penalized.
        rejected: Deprecated: use score magnitude instead. Kept for backward compat
            with frontend/lineage serialization.
        evaluation: Full evaluation report, if evaluated.
        generation: Which generation this candidate was created in.
        parent_ids: IDs of parent candidates used to produce this one.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    template: str
    fitness_score: float = 0.0
    normalized_score: float = 0.0
    rejected: bool = False
    evaluation: EvaluationReport | None = None
    generation: int = 0
    parent_ids: list[str] = Field(default_factory=list)
    otel: OTelAttributes | None = None


class EvolutionConfig(BaseModel):
    """Hyperparameters for the evolution loop.

    Defaults are derived from the Mind Evolution paper
    (arXiv:2501.09891) adapted for prompt optimization.

    Attributes:
        generations: Number of evolution generations to run (>= 1).
        conversations_per_island: Number of RCC conversations per generation (>= 1).
        n_seq: Number of sequential refinement turns per conversation (>= 1).
        n_parents: Number of parents selected per conversation (>= 0).
        temperature: Boltzmann selection temperature (> 0). Higher = more random.
        structural_mutation_probability: Probability of structural mutation per conversation [0, 1].
        pr_no_parents: Probability of generating from scratch (no parents) [0, 1].
        budget_cap_usd: Hard budget cap in USD. None means no limit.
        population_cap: Maximum population size per island.
        n_islands: Number of islands for island model evolution (>= 1).
        n_emigrate: Number of top candidates to emigrate between islands per migration (>= 0).
        reset_interval: Generations between island resets (>= 0, where 0 means no resets).
        n_reset: Number of worst islands to reset per reset event (>= 0).
        n_top: Number of top candidates to preserve during island reset (>= 1).
    """

    generations: int = 10
    conversations_per_island: int = 5
    n_seq: int = 3
    n_parents: int = 5
    temperature: float = 1.0
    structural_mutation_probability: float = 0.2
    pr_no_parents: float = Field(default=1 / 6)
    budget_cap_usd: float | None = None
    population_cap: int = 10

    # Island model fields (Mind Evolution paper defaults)
    n_islands: int = 4
    n_emigrate: int = 5
    reset_interval: int = 3
    n_reset: int = 2
    n_top: int = 5

    # Initial diversity: number of RCC seed variants per island (0 = paper default: clone only)
    n_seed_variants: int = 3

    # Subset sampling fields
    sample_size: int | None = None
    sample_ratio: float | None = None

    # Adaptive sampling fields (EVO-04/05/06)
    adaptive_sampling: bool = False
    adaptive_decay_constant: float = 3.0
    adaptive_min_rate: float = 0.1
    checkpoint_interval: int = 3  # Full eval every N generations (0 = disabled)

    @field_validator("generations")
    @classmethod
    def generations_at_least_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("generations must be >= 1")
        return v

    @field_validator("conversations_per_island")
    @classmethod
    def conversations_at_least_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("conversations_per_island must be >= 1")
        return v

    @field_validator("n_seq")
    @classmethod
    def n_seq_at_least_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("n_seq must be >= 1")
        return v

    @field_validator("n_parents")
    @classmethod
    def n_parents_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("n_parents must be >= 0")
        return v

    @field_validator("temperature")
    @classmethod
    def temperature_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("temperature must be > 0")
        return v

    @field_validator("structural_mutation_probability")
    @classmethod
    def structural_mutation_in_range(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("structural_mutation_probability must be in [0.0, 1.0]")
        return v

    @field_validator("pr_no_parents")
    @classmethod
    def pr_no_parents_in_range(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("pr_no_parents must be in [0.0, 1.0]")
        return v

    @field_validator("n_islands")
    @classmethod
    def n_islands_at_least_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("n_islands must be >= 1")
        return v

    @field_validator("n_emigrate")
    @classmethod
    def n_emigrate_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("n_emigrate must be >= 0")
        return v

    @field_validator("reset_interval")
    @classmethod
    def reset_interval_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("reset_interval must be >= 0")
        return v

    @field_validator("n_reset")
    @classmethod
    def n_reset_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("n_reset must be >= 0")
        return v

    @field_validator("n_top")
    @classmethod
    def n_top_at_least_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("n_top must be >= 1")
        return v

    @field_validator("sample_ratio")
    @classmethod
    def sample_ratio_in_range(cls, v: float | None) -> float | None:
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError("sample_ratio must be in [0.0, 1.0]")
        return v

    @field_validator("sample_size")
    @classmethod
    def sample_size_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("sample_size must be >= 0")
        return v

    @field_validator("adaptive_decay_constant")
    @classmethod
    def adaptive_decay_constant_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("adaptive_decay_constant must be > 0")
        return v

    @field_validator("adaptive_min_rate")
    @classmethod
    def adaptive_min_rate_in_range(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("adaptive_min_rate must be in [0.0, 1.0]")
        return v

    @field_validator("checkpoint_interval")
    @classmethod
    def checkpoint_interval_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("checkpoint_interval must be >= 0")
        return v


class GenerationRecord(BaseModel):
    """Metrics for a single generation of evolution.

    Attributes:
        generation: Generation number (0-indexed).
        best_fitness: Best fitness score in this generation.
        avg_fitness: Average fitness score across the population.
        cost_summary: Cost breakdown for this generation.
        candidates_evaluated: Number of candidates evaluated.
    """

    generation: int
    best_fitness: float
    avg_fitness: float
    best_normalized: float = 0.0
    avg_normalized: float = 0.0
    cost_summary: dict[str, Any] = Field(default_factory=dict)
    candidates_evaluated: int


class EvolutionResult(BaseModel):
    """Final output of an evolution run.

    Attributes:
        best_candidate: The highest-fitness candidate found.
        generation_records: Per-generation metrics.
        total_cost: Aggregate cost for the entire run.
        termination_reason: Why evolution stopped -- one of
            "perfect_fitness", "budget_exhausted", "generations_complete".
        seed_evaluation: Baseline evaluation of the seed prompt for regression analysis.
        lineage_events: Serialized lineage events (replaces monkey-patched attribute).
    """

    best_candidate: Candidate
    generation_records: list[GenerationRecord] = Field(default_factory=list)
    total_cost: dict[str, Any] = Field(default_factory=dict)
    termination_reason: str
    seed_evaluation: EvaluationReport | None = None
    lineage_events: list[dict[str, Any]] | None = None
    effective_models: dict[str, str] | None = None
