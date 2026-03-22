"""Tests for EventCallback integration in IslandEvolver and EvolutionLoop.

Tests verify:
- IslandEvolver with event_callback=None runs exactly as before (no errors)
- IslandEvolver with event_callback emits generation_started at loop start
- EvolutionLoop with event_callback emits candidate_evaluated after each eval
- IslandEvolver emits migration event after _migrate()
- IslandEvolver emits generation_complete at end of each generation
- IslandEvolver emits evolution_complete at the very end
- island_reset event emitted when _reset_islands() fires
- candidate_evaluated includes island index in data
"""

from __future__ import annotations

from unittest.mock import AsyncMock


from api.config.models import GenerationConfig
from api.dataset.models import TestCase
from api.evaluation.evaluator import FitnessEvaluator
from api.evaluation.models import (
    CaseResult,
    EvaluationReport,
    FitnessScore,
)
from api.evolution.islands import IslandEvolver
from api.evolution.loop import EvolutionLoop
from api.evolution.models import (
    Candidate,
    EvolutionConfig,
)
from api.evolution.mutator import StructuralMutator
from api.evolution.rcc import RCCEngine
from api.evolution.selector import BoltzmannSelector
from api.gateway.cost import CostTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report(score: float, rejected: bool = False) -> EvaluationReport:
    """Create an EvaluationReport with a controlled fitness score."""
    return EvaluationReport(
        fitness=FitnessScore(score=score, rejected=rejected),
        case_results=[
            CaseResult(case_id="c1", score=score, passed=score >= 0.5),
        ],
        total_cases=1,
        cost_summary={
            "total_calls": 1,
            "total_input_tokens": 10,
            "total_output_tokens": 10,
            "total_cost_usd": 0.001,
        },
    )


def _make_candidate(
    template: str = "evolved {{ x }}", generation: int = 0, fitness: float = 0.5
) -> Candidate:
    """Create a Candidate with a test template and fitness."""
    c = Candidate(template=template, generation=generation, parent_ids=[])
    c.fitness_score = fitness
    return c


def _build_island_evolver(
    config: EvolutionConfig | None = None,
    evaluator: FitnessEvaluator | None = None,
    rcc: RCCEngine | None = None,
    mutator: StructuralMutator | None = None,
    cost_tracker: CostTracker | None = None,
    event_callback=None,
) -> IslandEvolver:
    """Build an IslandEvolver with sensible defaults and optional event_callback."""
    if config is None:
        config = EvolutionConfig(
            generations=1,
            conversations_per_island=1,
            n_seq=1,
            n_parents=3,
            n_islands=2,
            n_emigrate=1,
            reset_interval=0,
            n_reset=1,
            n_top=2,
            structural_mutation_probability=0.0,
            pr_no_parents=0.0,
            population_cap=10,
        )
    if evaluator is None:
        evaluator = AsyncMock(spec=FitnessEvaluator)
        evaluator.evaluate = AsyncMock(return_value=_make_report(0.5))
    if rcc is None:
        rcc = AsyncMock(spec=RCCEngine)
        rcc_count_holder = [0]

        async def unique_rcc(*args, **kwargs):
            rcc_count_holder[0] += 1
            return _make_candidate(template=f"evolved_{rcc_count_holder[0]} {{{{ x }}}}")

        rcc.run_conversation = AsyncMock(side_effect=unique_rcc)
    if mutator is None:
        mutator = AsyncMock(spec=StructuralMutator)
        mutator.mutate = AsyncMock(return_value=_make_candidate())
    if cost_tracker is None:
        cost_tracker = CostTracker()

    return IslandEvolver(
        config=config,
        evaluator=evaluator,
        rcc=rcc,
        mutator=mutator,
        selector=BoltzmannSelector(),
        cost_tracker=cost_tracker,
        original_template="Hello {{ x }}",
        anchor_variables={"x"},
        cases=[TestCase(chat_history=[{"role": "user", "content": "hi"}])],
        target_model="test/model",
        generation_config=GenerationConfig(),
        purpose="test",
        event_callback=event_callback,
    )


def _build_evolution_loop(
    config: EvolutionConfig | None = None,
    evaluator: FitnessEvaluator | None = None,
    rcc: RCCEngine | None = None,
    mutator: StructuralMutator | None = None,
    cost_tracker: CostTracker | None = None,
    event_callback=None,
) -> EvolutionLoop:
    """Build an EvolutionLoop with sensible defaults and optional event_callback."""
    if config is None:
        config = EvolutionConfig(
            generations=1,
            conversations_per_island=1,
            n_seq=1,
            n_parents=3,
            n_islands=2,
            n_emigrate=1,
            reset_interval=0,
            n_reset=1,
            n_top=2,
            structural_mutation_probability=0.0,
            pr_no_parents=0.0,
            population_cap=10,
        )
    if evaluator is None:
        evaluator = AsyncMock(spec=FitnessEvaluator)
        evaluator.evaluate = AsyncMock(return_value=_make_report(0.5))
    if rcc is None:
        rcc = AsyncMock(spec=RCCEngine)
        rcc_count_holder = [0]

        async def unique_rcc(*args, **kwargs):
            rcc_count_holder[0] += 1
            return _make_candidate(template=f"evolved_{rcc_count_holder[0]} {{{{ x }}}}")

        rcc.run_conversation = AsyncMock(side_effect=unique_rcc)
    if mutator is None:
        mutator = AsyncMock(spec=StructuralMutator)
        mutator.mutate = AsyncMock(return_value=_make_candidate())
    if cost_tracker is None:
        cost_tracker = CostTracker()

    return EvolutionLoop(
        config=config,
        evaluator=evaluator,
        rcc=rcc,
        mutator=mutator,
        selector=BoltzmannSelector(),
        cost_tracker=cost_tracker,
        original_template="Hello {{ x }}",
        anchor_variables={"x"},
        cases=[TestCase(chat_history=[{"role": "user", "content": "hi"}])],
        target_model="test/model",
        generation_config=GenerationConfig(),
        purpose="test",
        event_callback=event_callback,
    )


# ---------------------------------------------------------------------------
# Tests: event_callback=None is backward compatible
# ---------------------------------------------------------------------------


async def test_island_evolver_no_callback_runs_normally():
    """IslandEvolver with event_callback=None runs exactly as before."""
    evolver = _build_island_evolver(event_callback=None)
    result = await evolver.run()

    assert result.termination_reason == "generations_complete"
    assert result.best_candidate is not None
    assert len(result.generation_records) == 1


# ---------------------------------------------------------------------------
# Tests: generation_started event
# ---------------------------------------------------------------------------


async def test_island_evolver_emits_generation_started():
    """IslandEvolver with event_callback emits generation_started at beginning of generation loop."""
    events: list[tuple[str, dict]] = []

    async def callback(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    evolver = _build_island_evolver(event_callback=callback)
    await evolver.run()

    gen_started = [e for e in events if e[0] == "generation_started"]
    assert len(gen_started) >= 1
    # Should contain generation number and island count
    assert "generation" in gen_started[0][1]
    assert "island_count" in gen_started[0][1]
    assert gen_started[0][1]["generation"] == 1  # 1-indexed for frontend
    assert gen_started[0][1]["island_count"] == 2


# ---------------------------------------------------------------------------
# Tests: candidate_evaluated event from EvolutionLoop
# ---------------------------------------------------------------------------


async def test_evolution_loop_emits_candidate_evaluated():
    """EvolutionLoop with event_callback emits candidate_evaluated after each eval."""
    events: list[tuple[str, dict]] = []

    async def callback(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    loop = _build_evolution_loop(event_callback=callback)

    # Use step_generation to test candidate_evaluated events
    seed = _make_candidate(template="Hello {{ x }}", fitness=0.5)
    population = [seed]
    loop.set_seed_results([CaseResult(case_id="c1", score=0.5, passed=True)])

    await loop.step_generation(population=population, generation=0)

    candidate_evals = [e for e in events if e[0] == "candidate_evaluated"]
    assert len(candidate_evals) >= 1
    data = candidate_evals[0][1]
    assert "generation" in data
    assert "candidate_id" in data
    assert "fitness_score" in data
    assert "rejected" in data
    assert "mutation_type" in data


async def test_candidate_evaluated_includes_island_index():
    """candidate_evaluated includes island index in data when passed to step_generation."""
    events: list[tuple[str, dict]] = []

    async def callback(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    loop = _build_evolution_loop(event_callback=callback)

    seed = _make_candidate(template="Hello {{ x }}", fitness=0.5)
    population = [seed]
    loop.set_seed_results([CaseResult(case_id="c1", score=0.5, passed=True)])

    await loop.step_generation(population=population, generation=0, island=3)

    candidate_evals = [e for e in events if e[0] == "candidate_evaluated"]
    assert len(candidate_evals) >= 1
    assert candidate_evals[0][1]["island"] == 3


# ---------------------------------------------------------------------------
# Tests: migration event
# ---------------------------------------------------------------------------


async def test_island_evolver_emits_migration():
    """IslandEvolver emits migration event after _migrate() completes."""
    events: list[tuple[str, dict]] = []

    async def callback(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    evolver = _build_island_evolver(event_callback=callback)
    await evolver.run()

    migration_events = [e for e in events if e[0] == "migration"]
    assert len(migration_events) >= 1
    data = migration_events[0][1]
    assert "generation" in data
    assert "emigrants_per_island" in data


# ---------------------------------------------------------------------------
# Tests: generation_complete event
# ---------------------------------------------------------------------------


async def test_island_evolver_emits_generation_complete():
    """IslandEvolver emits generation_complete at end of each generation."""
    events: list[tuple[str, dict]] = []

    async def callback(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    evolver = _build_island_evolver(event_callback=callback)
    await evolver.run()

    gen_complete = [e for e in events if e[0] == "generation_complete"]
    assert len(gen_complete) >= 1
    data = gen_complete[0][1]
    assert "generation" in data
    assert "best_fitness" in data
    assert "avg_fitness" in data
    assert "candidates_evaluated" in data
    assert "cost_usd" in data


# ---------------------------------------------------------------------------
# Tests: evolution_complete event
# ---------------------------------------------------------------------------


async def test_island_evolver_emits_evolution_complete():
    """IslandEvolver emits evolution_complete at the very end."""
    events: list[tuple[str, dict]] = []

    async def callback(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    evolver = _build_island_evolver(event_callback=callback)
    await evolver.run()

    evo_complete = [e for e in events if e[0] == "evolution_complete"]
    assert len(evo_complete) == 1
    data = evo_complete[0][1]
    assert "termination_reason" in data
    assert "best_fitness" in data
    assert "total_cost_usd" in data
    assert "generations_completed" in data


# ---------------------------------------------------------------------------
# Tests: island_reset event
# ---------------------------------------------------------------------------


async def test_island_evolver_emits_island_reset():
    """island_reset event is emitted when _reset_islands() fires."""
    events: list[tuple[str, dict]] = []

    async def callback(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    config = EvolutionConfig(
        generations=4,
        conversations_per_island=1,
        n_seq=1,
        n_parents=3,
        n_islands=3,
        n_emigrate=0,
        reset_interval=3,
        n_reset=1,
        n_top=2,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
        population_cap=10,
    )
    evolver = _build_island_evolver(config=config, event_callback=callback)
    await evolver.run()

    reset_events = [e for e in events if e[0] == "island_reset"]
    # Reset fires at generation 3 (gen > 0 and gen % 3 == 0)
    assert len(reset_events) >= 1
    data = reset_events[0][1]
    assert "generation" in data
    assert "islands_reset" in data
