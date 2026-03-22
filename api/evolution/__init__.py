"""Evolution sub-package for prompt optimization via evolutionary search.

This package implements the core evolution loop based on the Mind Evolution paper
(arXiv:2501.09891): Boltzmann tournament selection, RCC (Refinement through
Critical Conversation), structural mutation, and budget-bounded generation iteration.

Public API re-exports:
    - Candidate: evolved prompt template with fitness evaluation
    - EvolutionConfig: hyperparameters with Mind Evolution paper defaults
    - GenerationRecord: per-generation metrics
    - EvolutionResult: final evolution output with termination reason
    - BoltzmannSelector: parent selection via numerically stable softmax
    - RCCEngine: critic-author conversation for prompt refinement
    - StructuralMutator: section-level prompt restructuring via meta-model
    - EvolutionLoop: single-island evolution orchestrator
    - IslandEvolver: multi-island evolution orchestrator with migration and reset
"""

from api.evolution.islands import IslandEvolver
from api.evolution.loop import EvolutionLoop
from api.evolution.models import (
    Candidate,
    EvolutionConfig,
    EvolutionResult,
    GenerationRecord,
)
from api.evolution.mutator import StructuralMutator
from api.evolution.rcc import RCCEngine
from api.evolution.selector import BoltzmannSelector

__all__ = [
    "BoltzmannSelector",
    "Candidate",
    "EvolutionConfig",
    "EvolutionLoop",
    "EvolutionResult",
    "GenerationRecord",
    "IslandEvolver",
    "RCCEngine",
    "StructuralMutator",
]
