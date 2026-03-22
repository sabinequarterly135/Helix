"""Integration tests for EvolutionLoop orchestrator.

Tests cover the full evolution loop with mocked components:
- Single/multi generation completion
- Early termination on perfect fitness (score == 0.0)
- Budget cap and per-conversation budget checks (COST-03)
- Per-generation cost tracking (COST-02)
- Population cap enforcement
- Penalty-based population ranking (all candidates participate)
- Pr_no_parents fresh generation
- Probabilistic structural mutation
- Initial candidate evaluation
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from api.config.models import GenerationConfig
from api.dataset.models import TestCase
from api.evaluation.evaluator import FitnessEvaluator
from api.evaluation.models import (
    CaseResult,
    EvaluationReport,
    FitnessScore,
)
from api.evolution.loop import EvolutionLoop
from api.evolution.models import GenerationRecord
from api.evolution.models import Candidate, EvolutionConfig
from api.evolution.mutator import StructuralMutator
from api.evolution.rcc import RCCEngine
from api.evolution.selector import BoltzmannSelector
from api.gateway.cost import CostTracker
from api.types import LLMResponse, ModelRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report(score: float, rejected: bool = False) -> EvaluationReport:
    """Create an EvaluationReport with a controlled fitness score.

    Penalty model: 0.0 = perfect, negative = penalized.
    """
    return EvaluationReport(
        fitness=FitnessScore(
            score=score,
            rejected=rejected,
        ),
        case_results=[
            CaseResult(case_id="c1", score=score, passed=score == 0),
        ],
        total_cases=1,
        cost_summary={
            "total_calls": 1,
            "total_input_tokens": 10,
            "total_output_tokens": 10,
            "total_cost_usd": 0.001,
        },
    )


def _make_candidate(template: str = "evolved {{ x }}", generation: int = 0) -> Candidate:
    """Create a Candidate with a test template."""
    return Candidate(template=template, generation=generation, parent_ids=[])


def _make_llm_response(cost_usd: float = 0.001) -> LLMResponse:
    """Create a minimal LLMResponse for cost tracking."""
    return LLMResponse(
        content="ok",
        model_used="test/model",
        role=ModelRole.TARGET,
        input_tokens=10,
        output_tokens=10,
        cost_usd=cost_usd,
        timestamp=datetime.now(),
    )


def _build_loop(
    config: EvolutionConfig | None = None,
    evaluator: FitnessEvaluator | None = None,
    rcc: RCCEngine | None = None,
    mutator: StructuralMutator | None = None,
    cost_tracker: CostTracker | None = None,
) -> EvolutionLoop:
    """Build an EvolutionLoop with sensible defaults and optional overrides."""
    if config is None:
        config = EvolutionConfig(
            generations=1,
            conversations_per_island=2,
            n_seq=1,
            n_parents=3,
            structural_mutation_probability=0.0,
            pr_no_parents=0.0,
        )
    if evaluator is None:
        evaluator = AsyncMock(spec=FitnessEvaluator)
        evaluator.evaluate = AsyncMock(return_value=_make_report(-2.0))
    if rcc is None:
        rcc = AsyncMock(spec=RCCEngine)
        rcc.run_conversation = AsyncMock(return_value=_make_candidate())
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
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_generation_completes():
    """1 generation, 2 conversations -> EvolutionResult with generation_records."""
    loop = _build_loop()
    result = await loop.run()

    assert result.termination_reason == "generations_complete"
    assert len(result.generation_records) == 1
    assert result.generation_records[0].generation == 0
    assert result.generation_records[0].candidates_evaluated == 2
    assert result.best_candidate is not None


@pytest.mark.asyncio
async def test_early_termination_perfect_fitness():
    """Candidate with score 0.0 (perfect) terminates immediately."""
    evaluator = AsyncMock(spec=FitnessEvaluator)
    # Seed evaluation returns -2.0, then first conv candidate returns 0.0 (perfect)
    evaluator.evaluate = AsyncMock(side_effect=[_make_report(-2.0), _make_report(0.0)])

    config = EvolutionConfig(
        generations=10,
        conversations_per_island=5,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    loop = _build_loop(config=config, evaluator=evaluator)
    result = await loop.run()

    assert result.termination_reason == "perfect_fitness"
    assert result.best_candidate.fitness_score == 0.0
    # Should have stopped after just 2 evaluations (seed + first conv)
    assert evaluator.evaluate.call_count == 2


@pytest.mark.asyncio
async def test_budget_cap_terminates():
    """Cost exceeds budget_cap_usd -> termination_reason='budget_exhausted' (COST-03)."""
    cost_tracker = CostTracker()
    cost_tracker.record(_make_llm_response(cost_usd=5.0))

    config = EvolutionConfig(
        generations=5,
        conversations_per_island=3,
        n_seq=1,
        budget_cap_usd=1.0,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )

    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(return_value=_make_report(-2.0))

    loop = _build_loop(config=config, evaluator=evaluator, cost_tracker=cost_tracker)
    result = await loop.run()

    assert result.termination_reason == "budget_exhausted"


@pytest.mark.asyncio
async def test_budget_checked_per_conversation():
    """Budget check happens before each conversation, not just per generation."""
    cost_tracker = CostTracker()

    evaluator = AsyncMock(spec=FitnessEvaluator)
    call_count = 0

    async def eval_with_cost(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            cost_tracker.record(_make_llm_response(cost_usd=10.0))
        return _make_report(-2.0)

    evaluator.evaluate = AsyncMock(side_effect=eval_with_cost)

    config = EvolutionConfig(
        generations=1,
        conversations_per_island=5,
        n_seq=1,
        budget_cap_usd=1.0,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    loop = _build_loop(config=config, evaluator=evaluator, cost_tracker=cost_tracker)
    result = await loop.run()

    assert result.termination_reason == "budget_exhausted"
    assert evaluator.evaluate.call_count < 1 + 5


@pytest.mark.asyncio
async def test_generation_cost_tracking():
    """Each GenerationRecord has cost_summary with per-generation costs (COST-02)."""
    cost_tracker = CostTracker()

    evaluator = AsyncMock(spec=FitnessEvaluator)
    call_count = 0

    async def eval_with_cost(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        cost_tracker.record(_make_llm_response(cost_usd=0.01))
        return _make_report(-2.0)

    evaluator.evaluate = AsyncMock(side_effect=eval_with_cost)

    config = EvolutionConfig(
        generations=2,
        conversations_per_island=2,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    loop = _build_loop(config=config, evaluator=evaluator, cost_tracker=cost_tracker)
    result = await loop.run()

    assert len(result.generation_records) == 2
    for record in result.generation_records:
        assert "total_cost_usd" in record.cost_summary
        assert "total_calls" in record.cost_summary
    gen0_cost = result.generation_records[0].cost_summary["total_cost_usd"]
    gen1_cost = result.generation_records[1].cost_summary["total_cost_usd"]
    assert gen0_cost > 0
    assert gen1_cost > 0


@pytest.mark.asyncio
async def test_population_capped():
    """Population never exceeds population_cap."""
    config = EvolutionConfig(
        generations=3,
        conversations_per_island=5,
        n_seq=1,
        population_cap=3,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )

    evaluator = AsyncMock(spec=FitnessEvaluator)
    eval_count = 0

    async def varying_eval(*args, **kwargs):
        nonlocal eval_count
        eval_count += 1
        # Varying negative penalties, never reaching 0 (perfect)
        score = -0.5 - 0.1 * (eval_count % 10)
        return _make_report(score)

    evaluator.evaluate = AsyncMock(side_effect=varying_eval)

    rcc = AsyncMock(spec=RCCEngine)
    rcc_count = 0

    async def unique_rcc(*args, **kwargs):
        nonlocal rcc_count
        rcc_count += 1
        return _make_candidate(template=f"evolved_{rcc_count} {{{{ x }}}}")

    rcc.run_conversation = AsyncMock(side_effect=unique_rcc)

    loop = _build_loop(config=config, evaluator=evaluator, rcc=rcc)
    result = await loop.run()

    total_evaluated = sum(r.candidates_evaluated for r in result.generation_records)
    assert total_evaluated > 3
    assert result.termination_reason == "generations_complete"


@pytest.mark.asyncio
async def test_heavily_penalized_candidates_ranked_lower():
    """All candidates stay in population, but heavily penalized ones rank lower."""
    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(
        side_effect=[
            _make_report(-2.0),  # seed: penalty -2
            _make_report(-10.0),  # conv1: heavy penalty -10
            _make_report(-1.0),  # conv2: light penalty -1
        ]
    )

    config = EvolutionConfig(
        generations=1,
        conversations_per_island=2,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    loop = _build_loop(config=config, evaluator=evaluator)
    result = await loop.run()

    # Best candidate should have the least negative score
    assert result.best_candidate.fitness_score == -1.0


@pytest.mark.asyncio
@patch("api.evolution.loop.random")
async def test_pr_no_parents_fresh_generation(mock_random):
    """With pr_no_parents=1.0, all conversations get 0 parents."""
    config = EvolutionConfig(
        generations=1,
        conversations_per_island=3,
        n_seq=1,
        pr_no_parents=1.0,
        structural_mutation_probability=0.0,
    )

    rcc = AsyncMock(spec=RCCEngine)
    rcc.run_conversation = AsyncMock(return_value=_make_candidate())

    mock_random.random.return_value = 0.5

    loop = _build_loop(config=config, rcc=rcc)
    await loop.run()

    for call_args in rcc.run_conversation.call_args_list:
        parents = call_args.kwargs.get("parents", call_args.args[0] if call_args.args else None)
        assert parents == []


@pytest.mark.asyncio
@patch("api.evolution.loop.random")
async def test_structural_mutation_applied_probabilistically(mock_random):
    """With probability 1.0, mutator is always called; with 0.0, never called."""
    mutator = AsyncMock(spec=StructuralMutator)
    mutator.mutate = AsyncMock(return_value=_make_candidate())

    mock_random.random.return_value = 0.0

    config_always = EvolutionConfig(
        generations=1,
        conversations_per_island=2,
        n_seq=1,
        structural_mutation_probability=1.0,
        pr_no_parents=0.0,
    )
    mock_random.randint.return_value = 1

    loop = _build_loop(config=config_always, mutator=mutator)
    await loop.run()
    assert mutator.mutate.call_count == 2

    mutator.mutate.reset_mock()
    config_never = EvolutionConfig(
        generations=1,
        conversations_per_island=2,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    mock_random.randint.return_value = 1
    loop = _build_loop(config=config_never, mutator=mutator)
    await loop.run()
    assert mutator.mutate.call_count == 0


@pytest.mark.asyncio
async def test_multi_generation_evolution():
    """3+ generations, fitness improves over time (less negative)."""
    evaluator = AsyncMock(spec=FitnessEvaluator)
    call_count = 0

    async def improving_eval(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Start very negative, improve toward 0
        score = max(-10.0 + 1.0 * call_count, -0.5)
        return _make_report(score)

    evaluator.evaluate = AsyncMock(side_effect=improving_eval)

    config = EvolutionConfig(
        generations=3,
        conversations_per_island=2,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    loop = _build_loop(config=config, evaluator=evaluator)
    result = await loop.run()

    assert len(result.generation_records) == 3
    assert result.termination_reason == "generations_complete"
    best_gen0 = result.generation_records[0].best_fitness
    best_gen2 = result.generation_records[2].best_fitness
    assert best_gen2 >= best_gen0


@pytest.mark.asyncio
async def test_termination_reason_generations_complete():
    """All generations exhausted -> reason is 'generations_complete'."""
    config = EvolutionConfig(
        generations=2,
        conversations_per_island=1,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    loop = _build_loop(config=config)
    result = await loop.run()

    assert result.termination_reason == "generations_complete"
    assert len(result.generation_records) == 2


@pytest.mark.asyncio
async def test_initial_candidate_evaluated():
    """The original template is evaluated to establish baseline fitness."""
    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(return_value=_make_report(-3.0))

    config = EvolutionConfig(
        generations=1,
        conversations_per_island=1,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    loop = _build_loop(config=config, evaluator=evaluator)
    await loop.run()

    assert evaluator.evaluate.call_count >= 2
    first_call_kwargs = evaluator.evaluate.call_args_list[0].kwargs
    assert first_call_kwargs["template"] == "Hello {{ x }}"


# ---------------------------------------------------------------------------
# step_generation() Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_generation_returns_tuple():
    """step_generation returns (list[Candidate], GenerationRecord, str|None) tuple."""
    loop = _build_loop()
    seed = _make_candidate(template="Hello {{ x }}", generation=0)
    seed.fitness_score = -2.0

    result = await loop.step_generation(population=[seed], generation=0)

    assert isinstance(result, tuple)
    assert len(result) == 3
    population, record, termination_reason = result
    assert isinstance(population, list)
    assert all(isinstance(c, Candidate) for c in population)
    assert isinstance(record, GenerationRecord)
    assert termination_reason is None


@pytest.mark.asyncio
async def test_step_generation_runs_conversations():
    """step_generation runs conversations_per_island conversations and adds new candidates."""
    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(return_value=_make_report(-1.0))

    rcc = AsyncMock(spec=RCCEngine)
    rcc_count = 0

    async def unique_rcc(*args, **kwargs):
        nonlocal rcc_count
        rcc_count += 1
        return _make_candidate(template=f"evolved_{rcc_count} {{{{ x }}}}")

    rcc.run_conversation = AsyncMock(side_effect=unique_rcc)

    config = EvolutionConfig(
        generations=1,
        conversations_per_island=3,
        n_seq=1,
        n_parents=3,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    loop = _build_loop(config=config, evaluator=evaluator, rcc=rcc)
    seed = _make_candidate(template="Hello {{ x }}", generation=0)
    seed.fitness_score = -2.0

    population, record, reason = await loop.step_generation(population=[seed], generation=0)

    assert rcc.run_conversation.call_count == 3
    assert evaluator.evaluate.call_count == 3
    assert len(population) >= 1
    assert record.candidates_evaluated == 3
    assert reason is None


@pytest.mark.asyncio
async def test_step_generation_perfect_fitness():
    """step_generation returns 'perfect_fitness' when candidate scores 0.0."""
    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(return_value=_make_report(0.0))

    config = EvolutionConfig(
        generations=1,
        conversations_per_island=5,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    loop = _build_loop(config=config, evaluator=evaluator)
    seed = _make_candidate(template="Hello {{ x }}", generation=0)
    seed.fitness_score = -2.0

    population, record, reason = await loop.step_generation(population=[seed], generation=0)

    assert reason == "perfect_fitness"
    assert evaluator.evaluate.call_count == 1


@pytest.mark.asyncio
async def test_step_generation_budget_exhausted():
    """step_generation returns 'budget_exhausted' when budget exceeded."""
    cost_tracker = CostTracker()
    cost_tracker.record(_make_llm_response(cost_usd=5.0))

    config = EvolutionConfig(
        generations=1,
        conversations_per_island=5,
        n_seq=1,
        budget_cap_usd=1.0,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )

    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(return_value=_make_report(-2.0))

    loop = _build_loop(config=config, evaluator=evaluator, cost_tracker=cost_tracker)
    seed = _make_candidate(template="Hello {{ x }}", generation=0)
    seed.fitness_score = -2.0

    population, record, reason = await loop.step_generation(population=[seed], generation=0)

    assert reason == "budget_exhausted"


@pytest.mark.asyncio
async def test_step_generation_population_capped():
    """step_generation caps population at population_cap."""
    evaluator = AsyncMock(spec=FitnessEvaluator)
    eval_count = 0

    async def varying_eval(*args, **kwargs):
        nonlocal eval_count
        eval_count += 1
        # Varying negative penalties, never reaching 0 (perfect)
        score = -0.5 - 0.1 * (eval_count % 10)
        return _make_report(score)

    evaluator.evaluate = AsyncMock(side_effect=varying_eval)

    rcc = AsyncMock(spec=RCCEngine)
    rcc_count = 0

    async def unique_rcc(*args, **kwargs):
        nonlocal rcc_count
        rcc_count += 1
        return _make_candidate(template=f"evolved_{rcc_count} {{{{ x }}}}")

    rcc.run_conversation = AsyncMock(side_effect=unique_rcc)

    config = EvolutionConfig(
        generations=1,
        conversations_per_island=10,
        n_seq=1,
        population_cap=3,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )
    loop = _build_loop(config=config, evaluator=evaluator, rcc=rcc)

    seeds = [_make_candidate(template=f"seed_{i} {{{{ x }}}}", generation=0) for i in range(5)]
    for i, s in enumerate(seeds):
        s.fitness_score = -0.5 * i

    population, record, reason = await loop.step_generation(population=seeds, generation=0)

    assert len(population) <= 3
