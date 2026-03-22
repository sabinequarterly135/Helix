"""Tests for SamplingStrategy integration in the evolution loop.

Verifies that:
- step_generation with sample_size calls evaluator.evaluate with a subset of cases
- step_generation with no sampling config calls evaluator.evaluate with all cases
- Seed evaluation in run() always uses ALL cases even when sampling is configured
- set_seed_results() allows external injection of seed results
"""

from __future__ import annotations

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
from api.evaluation.sampling import SamplingStrategy
from api.evolution.loop import EvolutionLoop
from api.evolution.models import Candidate, EvolutionConfig
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


def _make_report_with_results(score: float, case_results: list[CaseResult]) -> EvaluationReport:
    """Create an EvaluationReport with specific case results."""
    return EvaluationReport(
        fitness=FitnessScore(score=score),
        case_results=case_results,
        total_cases=len(case_results),
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


def _make_cases(n: int) -> list[TestCase]:
    """Create n test cases with unique IDs."""
    cases = []
    for i in range(n):
        cases.append(
            TestCase(
                id=f"case-{i}",
                chat_history=[{"role": "user", "content": f"test {i}"}],
            )
        )
    return cases


def _build_loop_with_cases(
    config: EvolutionConfig,
    evaluator: FitnessEvaluator | None = None,
    cases: list[TestCase] | None = None,
) -> EvolutionLoop:
    """Build an EvolutionLoop with configurable cases for sampling tests."""
    if evaluator is None:
        evaluator = AsyncMock(spec=FitnessEvaluator)
        evaluator.evaluate = AsyncMock(return_value=_make_report(0.5))
    if cases is None:
        cases = _make_cases(5)

    rcc = AsyncMock(spec=RCCEngine)
    rcc.run_conversation = AsyncMock(return_value=_make_candidate())

    mutator = AsyncMock(spec=StructuralMutator)
    mutator.mutate = AsyncMock(return_value=_make_candidate())

    return EvolutionLoop(
        config=config,
        evaluator=evaluator,
        rcc=rcc,
        mutator=mutator,
        selector=BoltzmannSelector(),
        cost_tracker=CostTracker(),
        original_template="Hello {{ x }}",
        anchor_variables={"x"},
        cases=cases,
        target_model="test/model",
        generation_config=GenerationConfig(),
        purpose="test",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_generation_with_sampling_uses_subset():
    """step_generation with sample_size=2 calls evaluator.evaluate with fewer cases than total."""
    cases = _make_cases(10)
    config = EvolutionConfig(
        generations=1,
        conversations_per_island=1,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
        sample_size=2,
    )

    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(return_value=_make_report(0.5))

    loop = _build_loop_with_cases(config=config, evaluator=evaluator, cases=cases)

    # Inject seed results so sampling is active
    seed_results = [CaseResult(case_id=f"case-{i}", score=0.8, passed=True) for i in range(10)]
    loop.set_seed_results(seed_results)

    seed = _make_candidate(template="Hello {{ x }}", generation=0)
    seed.fitness_score = 0.5

    await loop.step_generation(population=[seed], generation=1)

    # The evaluate call should use fewer cases than total
    call_kwargs = evaluator.evaluate.call_args.kwargs
    eval_cases = call_kwargs["cases"]
    assert len(eval_cases) < len(cases), (
        f"Expected subset but got {len(eval_cases)} cases (total={len(cases)})"
    )


@pytest.mark.asyncio
async def test_step_generation_without_sampling_uses_all_cases():
    """step_generation with no sampling config calls evaluator.evaluate with all cases."""
    cases = _make_cases(5)
    config = EvolutionConfig(
        generations=1,
        conversations_per_island=1,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )

    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(return_value=_make_report(0.5))

    loop = _build_loop_with_cases(config=config, evaluator=evaluator, cases=cases)

    seed = _make_candidate(template="Hello {{ x }}", generation=0)
    seed.fitness_score = 0.5

    await loop.step_generation(population=[seed], generation=0)

    # The evaluate call should use all cases
    call_kwargs = evaluator.evaluate.call_args.kwargs
    eval_cases = call_kwargs["cases"]
    assert len(eval_cases) == len(cases)


@pytest.mark.asyncio
async def test_seed_evaluation_uses_all_cases_even_with_sampling():
    """run() always evaluates ALL cases for the seed candidate even when sampling is configured."""
    cases = _make_cases(10)
    config = EvolutionConfig(
        generations=1,
        conversations_per_island=1,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
        sample_size=2,
    )

    evaluator = AsyncMock(spec=FitnessEvaluator)
    seed_report = _make_report_with_results(
        0.5,
        [CaseResult(case_id=f"case-{i}", score=0.5, passed=True) for i in range(10)],
    )
    evaluator.evaluate = AsyncMock(return_value=seed_report)

    loop = _build_loop_with_cases(config=config, evaluator=evaluator, cases=cases)
    await loop.run()

    # First call (seed evaluation) should use ALL cases
    first_call_kwargs = evaluator.evaluate.call_args_list[0].kwargs
    seed_cases = first_call_kwargs["cases"]
    assert len(seed_cases) == 10, f"Seed should evaluate all 10 cases but got {len(seed_cases)}"

    # Second call (step_generation) should use a subset since sampling is configured
    if evaluator.evaluate.call_count >= 2:
        second_call_kwargs = evaluator.evaluate.call_args_list[1].kwargs
        step_cases = second_call_kwargs["cases"]
        assert len(step_cases) < 10, (
            f"step_generation should use subset but got {len(step_cases)} cases"
        )


@pytest.mark.asyncio
async def test_set_seed_results_enables_sampling():
    """set_seed_results() allows external injection of seed results for sampling."""
    cases = _make_cases(10)
    config = EvolutionConfig(
        generations=1,
        conversations_per_island=1,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
        sample_size=2,
    )

    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(return_value=_make_report(0.5))

    loop = _build_loop_with_cases(config=config, evaluator=evaluator, cases=cases)

    # Before setting seed results, sampling should not be active
    # (seed_results is None, so all cases are used)
    seed = _make_candidate(template="Hello {{ x }}", generation=0)
    seed.fitness_score = 0.5
    await loop.step_generation(population=[seed], generation=0)

    first_call_cases = evaluator.evaluate.call_args.kwargs["cases"]
    assert len(first_call_cases) == 10  # all cases, no sampling

    evaluator.evaluate.reset_mock()

    # After setting seed results, sampling should be active
    seed_results = [CaseResult(case_id=f"case-{i}", score=0.8, passed=True) for i in range(10)]
    loop.set_seed_results(seed_results)

    await loop.step_generation(population=[seed], generation=1)

    second_call_cases = evaluator.evaluate.call_args.kwargs["cases"]
    assert len(second_call_cases) < 10  # subset


# ---------------------------------------------------------------------------
# Adaptive sampling integration tests (Plan 30-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_full_evaluation():
    """Checkpoint generation (gen % interval == 0) evaluates ALL cases."""
    cases = _make_cases(10)
    config = EvolutionConfig(
        generations=3,
        conversations_per_island=1,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
        sample_size=2,
        adaptive_sampling=True,
        checkpoint_interval=2,
    )

    # Track which cases were passed to evaluate
    eval_case_counts: list[int] = []

    report_with_results = _make_report_with_results(
        -1.0,
        [CaseResult(case_id=f"case-{i}", score=0.8, passed=True) for i in range(10)],
    )

    async def tracking_evaluate(**kwargs):
        eval_case_counts.append(len(kwargs["cases"]))
        return report_with_results

    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(side_effect=tracking_evaluate)

    loop = _build_loop_with_cases(config=config, evaluator=evaluator, cases=cases)

    # Inject seed results so sampling is active
    seed_results = [CaseResult(case_id=f"case-{i}", score=0.8, passed=True) for i in range(10)]
    loop.set_seed_results(seed_results)

    seed = _make_candidate(template="Hello {{ x }}", generation=0)
    seed.fitness_score = -1.0

    # gen=0: not a checkpoint (0 > 0 is false), uses smart_subset
    await loop.step_generation(population=[seed], generation=0)
    gen0_cases = eval_case_counts[-1]

    eval_case_counts.clear()

    # gen=2: checkpoint (2 > 0 and 2 % 2 == 0), evaluates ALL cases
    await loop.step_generation(population=[seed], generation=2)
    gen2_cases = eval_case_counts[-1]

    assert gen0_cases < 10, f"Gen 0 should use subset but got {gen0_cases}"
    assert gen2_cases == 10, f"Gen 2 (checkpoint) should use all 10 cases but got {gen2_cases}"


@pytest.mark.asyncio
async def test_adaptive_sampling_config_false_unchanged():
    """adaptive_sampling=False (default) creates no AdaptiveSampler."""
    config = EvolutionConfig(
        generations=1,
        conversations_per_island=1,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
    )

    loop = _build_loop_with_cases(config=config)
    assert loop._adaptive_sampler is None


@pytest.mark.asyncio
async def test_adaptive_sampler_streak_reset_on_checkpoint_failure():
    """On checkpoint, failing cases have their streaks reset to 0."""
    cases = _make_cases(3)
    config = EvolutionConfig(
        generations=3,
        conversations_per_island=1,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
        sample_size=1,
        adaptive_sampling=True,
        checkpoint_interval=2,
    )

    # First gen: all pass
    all_pass_report = _make_report_with_results(
        -1.0,
        [CaseResult(case_id=f"case-{i}", score=0.8, passed=True) for i in range(3)],
    )
    # Checkpoint gen: case-1 fails
    checkpoint_report = _make_report_with_results(
        -2.0,
        [
            CaseResult(case_id="case-0", score=0.8, passed=True),
            CaseResult(case_id="case-1", score=0.0, passed=False),
            CaseResult(case_id="case-2", score=0.8, passed=True),
        ],
    )

    evaluator = AsyncMock(spec=FitnessEvaluator)
    # Gens 0, 1 return all pass; gen 2 (checkpoint) returns case-1 failure
    evaluator.evaluate = AsyncMock(
        side_effect=[all_pass_report, all_pass_report, checkpoint_report]
    )

    loop = _build_loop_with_cases(config=config, evaluator=evaluator, cases=cases)
    seed_results = [CaseResult(case_id=f"case-{i}", score=0.8, passed=True) for i in range(3)]
    loop.set_seed_results(seed_results)

    seed = _make_candidate(template="Hello {{ x }}", generation=0)
    seed.fitness_score = -1.0

    # Run gen 0 and 1 to build streaks
    await loop.step_generation(population=[seed], generation=0)
    await loop.step_generation(population=[seed], generation=1)

    # Before checkpoint, case-1 should have a streak > 0
    assert loop._adaptive_sampler is not None
    assert loop._adaptive_sampler.pass_streaks.get("case-1", 0) > 0

    # Run gen 2 (checkpoint) where case-1 fails
    await loop.step_generation(population=[seed], generation=2)

    # case-1 should be reset to 0
    assert loop._adaptive_sampler.pass_streaks.get("case-1", -1) == 0
    # case-0 and case-2 should still have streaks (they passed)
    assert loop._adaptive_sampler.pass_streaks.get("case-0", 0) > 0


@pytest.mark.asyncio
async def test_adaptive_weights_passed_to_smart_subset():
    """When adaptive_sampling=True, adaptive_weights kwarg is passed to smart_subset."""
    cases = _make_cases(5)
    config = EvolutionConfig(
        generations=1,
        conversations_per_island=1,
        n_seq=1,
        structural_mutation_probability=0.0,
        pr_no_parents=0.0,
        sample_size=2,
        adaptive_sampling=True,
        checkpoint_interval=0,  # disabled so it uses smart_subset
    )

    report = _make_report_with_results(
        -1.0,
        [CaseResult(case_id=f"case-{i}", score=0.8, passed=True) for i in range(5)],
    )
    evaluator = AsyncMock(spec=FitnessEvaluator)
    evaluator.evaluate = AsyncMock(return_value=report)

    loop = _build_loop_with_cases(config=config, evaluator=evaluator, cases=cases)
    seed_results = [CaseResult(case_id=f"case-{i}", score=0.8, passed=True) for i in range(5)]
    loop.set_seed_results(seed_results)

    seed = _make_candidate(template="Hello {{ x }}", generation=0)
    seed.fitness_score = -1.0

    with patch(
        "api.evolution.loop.SamplingStrategy.smart_subset",
        wraps=SamplingStrategy.smart_subset,
    ) as mock_smart:
        await loop.step_generation(population=[seed], generation=1)

        # smart_subset should have been called with adaptive_weights
        assert mock_smart.called
        call_kwargs = mock_smart.call_args.kwargs
        assert "adaptive_weights" in call_kwargs
        aw = call_kwargs["adaptive_weights"]
        assert isinstance(aw, dict)
        # All weights should be floats
        assert all(isinstance(v, float) for v in aw.values())
