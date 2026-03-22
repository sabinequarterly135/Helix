"""IslandEvolver: multi-island evolution orchestrator.

Wraps N EvolutionLoop instances with cyclic migration and periodic
island reset per the Mind Evolution algorithm (arXiv:2501.09891).

Cross-island coordination:
- Cyclic migration: top n_emigrate candidates from island i -> island (i+1) % n
- Island reset: lowest-performing islands replaced with top global candidates
- Global best tracking across all islands
- Budget enforcement across all islands via shared CostTracker

All intra-island evolution (RCC, mutation, evaluation, population management)
is delegated to EvolutionLoop.step_generation().
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import uuid
from typing import Any

from api.config.models import GenerationConfig
from api.dataset.models import TestCase
from api.evaluation.evaluator import FitnessEvaluator
from api.evolution.loop import EventCallback, EvolutionLoop
from api.evolution.models import (
    Candidate,
    EvolutionConfig,
    EvolutionResult,
    GenerationRecord,
)
from api.evolution.mutator import StructuralMutator
from api.evolution.rcc import RCCEngine
from api.evolution.selector import BoltzmannSelector
from api.exceptions import GatewayError
from api.gateway.cost import CostTracker
from api.lineage.collector import LineageCollector
from api.lineage.models import LineageEvent

logger = logging.getLogger(__name__)


class IslandEvolver:
    """Multi-island evolution orchestrator.

    Manages N EvolutionLoop instances with cyclic migration
    and periodic island reset per the Mind Evolution algorithm.

    Args:
        config: Evolution hyperparameters including island model fields.
        evaluator: FitnessEvaluator for scoring candidate prompts.
        rcc: RCCEngine for critic-author conversation refinement.
        mutator: StructuralMutator for section-level restructuring.
        selector: BoltzmannSelector for parent selection.
        cost_tracker: Shared CostTracker for budget enforcement across islands.
        original_template: The seed Jinja2 template to evolve.
        anchor_variables: Variables that must be preserved in all candidates.
        cases: Test cases for fitness evaluation.
        target_model: OpenRouter model identifier for inference.
        generation_config: Temperature, max_tokens, etc. for inference.
        prompt_tools: Default tool definitions for evaluation (optional).
        purpose: Description of what the prompt is optimized for.
    """

    def __init__(
        self,
        config: EvolutionConfig,
        evaluator: FitnessEvaluator,
        rcc: RCCEngine,
        mutator: StructuralMutator,
        selector: BoltzmannSelector,
        cost_tracker: CostTracker,
        original_template: str,
        anchor_variables: set[str],
        cases: list[TestCase],
        target_model: str,
        generation_config: GenerationConfig,
        prompt_tools: list[dict] | None = None,
        purpose: str = "",
        collector: LineageCollector | None = None,
        event_callback: EventCallback = None,
    ) -> None:
        self._config = config
        self._evaluator = evaluator
        self._cost_tracker = cost_tracker
        self._original_template = original_template
        self._collector = collector
        self._event_callback = event_callback
        self._current_generation: int = 0  # Tracked for _reset_islands

        # Create per-island EvolutionLoop instances for step_generation() delegation.
        # Each loop is a distinct instance so _seed_results state is isolated,
        # but they share services (evaluator, rcc, mutator, selector, cost_tracker,
        # collector, event_callback) since those are either stateless or concurrency-safe.
        self._loops: list[EvolutionLoop] = [
            EvolutionLoop(
                config=config,
                evaluator=evaluator,
                rcc=rcc,
                mutator=mutator,
                selector=selector,
                cost_tracker=cost_tracker,
                original_template=original_template,
                anchor_variables=anchor_variables,
                cases=cases,
                target_model=target_model,
                generation_config=generation_config,
                prompt_tools=prompt_tools,
                purpose=purpose,
                collector=collector,
                event_callback=event_callback,
            )
            for _ in range(config.n_islands)
        ]

        # Per-island populations (initialized in run())
        self._island_populations: list[list[Candidate]] = [[] for _ in range(config.n_islands)]

        # Store evaluation dependencies for seed evaluation
        self._cases = cases
        self._target_model = target_model
        self._generation_config = generation_config
        self._prompt_tools = prompt_tools
        self._purpose = purpose

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit an event via the callback, if one is registered."""
        if self._event_callback is not None:
            await self._event_callback(event_type, data)

    async def run(self) -> EvolutionResult:
        """Execute multi-island evolution with migration and reset.

        1. Evaluate seed candidate ONCE (Pitfall 6 prevention).
        2. Clone seed into all N island populations.
        3. Generation loop with per-island step_generation(), migration, reset.
        4. Return EvolutionResult with global best and aggregate records.

        Returns:
            EvolutionResult with the best candidate across all islands,
            aggregate generation records, total cost, and termination reason.
        """
        # 1. Evaluate seed candidate once
        seed_candidate = Candidate(
            template=self._original_template,
            generation=0,
            parent_ids=[],
        )
        seed_report = await self._evaluator.evaluate(
            template=seed_candidate.template,
            cases=self._cases,
            target_model=self._target_model,
            generation_config=self._generation_config,
            prompt_tools=self._prompt_tools,
            purpose=self._purpose,
        )
        seed_candidate.fitness_score = seed_report.fitness.score
        seed_candidate.normalized_score = seed_report.fitness.normalized_score
        seed_candidate.rejected = seed_report.fitness.rejected
        seed_candidate.evaluation = seed_report

        # Inject seed results for sampling decisions on ALL per-island loops
        for loop in self._loops:
            loop.set_seed_results(seed_report.case_results)

        # Record seed lineage event (so DiffViewer can trace back to origin)
        if self._collector is not None:
            self._collector.record(
                LineageEvent(
                    candidate_id=seed_candidate.id,
                    parent_ids=[],
                    generation=0,
                    fitness_score=seed_candidate.fitness_score,
                    normalized_score=seed_candidate.normalized_score,
                    rejected=seed_candidate.rejected,
                    mutation_type="seed",
                    template=seed_candidate.template,
                )
            )

        # Emit seed evaluation event so the dashboard updates in real-time
        await self._emit(
            "candidate_evaluated",
            {
                "generation": 0,
                "island": 0,
                "candidate_id": seed_candidate.id,
                "fitness_score": seed_candidate.fitness_score,
                "normalized_score": seed_candidate.normalized_score,
                "rejected": seed_candidate.rejected,
                "mutation_type": "seed",
            },
        )

        # 2. Check early termination on seed (0.0 = perfect, no penalties)
        if seed_candidate.fitness_score == 0.0:
            return EvolutionResult(
                best_candidate=seed_candidate,
                generation_records=[],
                total_cost=self._cost_tracker.summary(),
                termination_reason="perfect_fitness",
                seed_evaluation=seed_report,
            )

        # 3. Generate diverse initial variants via RCC (closer to Mind Evolution paper)
        # Paper: N_convs * N_seq candidates per island. We generate n_seed_variants
        # diverse variants of the seed, evaluate them, and distribute to all islands.
        n_seed_variants = self._config.n_seed_variants
        initial_candidates = [seed_candidate]

        if n_seed_variants > 0:
            logger.info(
                "Generating %d seed variants via RCC for initial diversity",
                n_seed_variants,
            )
            anchor_vars = set(self._loops[0]._anchor_variables)
            for v_idx in range(n_seed_variants):
                if self._budget_exceeded():
                    break
                try:
                    variant = await self._loops[0]._rcc.run_conversation(
                        parents=[seed_candidate],
                        original_template=self._original_template,
                        anchor_variables=anchor_vars,
                        purpose=self._purpose,
                        n_seq=1,  # Single refinement turn per variant
                        generation=0,
                    )
                    # Evaluate the variant
                    variant_report = await self._evaluator.evaluate(
                        template=variant.template,
                        cases=self._cases,
                        target_model=self._target_model,
                        generation_config=self._generation_config,
                        prompt_tools=self._prompt_tools,
                        purpose=self._purpose,
                    )
                    variant.fitness_score = variant_report.fitness.score
                    variant.normalized_score = variant_report.fitness.normalized_score
                    variant.rejected = variant_report.fitness.rejected
                    variant.evaluation = variant_report
                    variant.parent_ids = [seed_candidate.id]

                    # Record lineage and emit event
                    if self._collector is not None:
                        self._collector.record(
                            LineageEvent(
                                candidate_id=variant.id,
                                parent_ids=[seed_candidate.id],
                                generation=0,
                                fitness_score=variant.fitness_score,
                                normalized_score=variant.normalized_score,
                                rejected=variant.rejected,
                                mutation_type="seed_variant",
                                template=variant.template,
                            )
                        )
                    # NOTE: per-island clone events are emitted below during
                    # island population cloning (BUG-03 fix).  No island=0
                    # emission here to avoid unbalanced dot display.
                    initial_candidates.append(variant)

                    # Early termination if variant achieves perfect fitness
                    if variant.fitness_score == 0.0:
                        return EvolutionResult(
                            best_candidate=variant,
                            generation_records=[],
                            total_cost=self._cost_tracker.summary(),
                            termination_reason="perfect_fitness",
                            seed_evaluation=seed_report,
                        )
                except Exception:
                    logger.warning("Seed variant %d generation failed", v_idx, exc_info=True)

        # 4. Clone initial candidates into all island populations
        for i in range(self._config.n_islands):
            self._island_populations[i] = []
            for candidate in initial_candidates:
                clone = candidate.model_copy(deep=True)
                clone.id = str(uuid.uuid4())
                self._island_populations[i].append(clone)
                mutation = "seed" if candidate.parent_ids == [] else "seed_variant"
                if self._collector is not None:
                    self._collector.record(
                        LineageEvent(
                            candidate_id=clone.id,
                            parent_ids=[candidate.id],
                            generation=0,
                            island=i,
                            fitness_score=clone.fitness_score,
                            normalized_score=clone.normalized_score,
                            rejected=clone.rejected,
                            mutation_type=mutation,
                            template=clone.template,
                        )
                    )
                # Emit per-island clone event for balanced dashboard display (BUG-03)
                await self._emit(
                    "candidate_evaluated",
                    {
                        "generation": 0,
                        "island": i,
                        "candidate_id": clone.id,
                        "fitness_score": clone.fitness_score,
                        "normalized_score": clone.normalized_score,
                        "rejected": clone.rejected,
                        "mutation_type": mutation,
                    },
                )

        # 4. Generation loop
        best_global = seed_candidate
        generation_records: list[GenerationRecord] = []
        termination_reason = "generations_complete"

        for gen in range(self._config.generations):
            # Budget check at generation boundary
            if self._budget_exceeded():
                termination_reason = "budget_exhausted"
                logger.info("Budget exhausted before generation %d", gen)
                break

            # Track current generation for _reset_islands
            self._current_generation = gen

            # Emit generation_started event (1-indexed for frontend)
            await self._emit(
                "generation_started",
                {
                    "generation": gen + 1,
                    "island_count": self._config.n_islands,
                },
            )

            island_records: list[GenerationRecord] = []
            gen_terminated = False

            # Process all islands in parallel via asyncio.gather.
            # Each island's step_generation is I/O-bound (LLM API calls),
            # so concurrent execution reduces wall-clock time by ~N.
            tasks = [
                self._loops[island_idx].step_generation(
                    population=self._island_populations[island_idx],
                    generation=gen,
                    island=island_idx,
                )
                for island_idx in range(self._config.n_islands)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results sequentially to update populations and detect termination
            for island_idx, result in enumerate(results):
                if isinstance(result, GatewayError):
                    logger.error(
                        "Island %d gen %d: %s -- terminating",
                        island_idx,
                        gen,
                        result,
                    )
                    termination_reason = "error"
                    gen_terminated = True
                    break
                if isinstance(result, Exception):
                    logger.error(
                        "Island %d gen %d unexpected error: %s",
                        island_idx,
                        gen,
                        result,
                    )
                    termination_reason = "error"
                    gen_terminated = True
                    break

                population, record, step_reason = result
                self._island_populations[island_idx] = population
                island_records.append(record)

                if step_reason == "perfect_fitness":
                    if population:
                        island_best = population[0]
                        if island_best.fitness_score > best_global.fitness_score:
                            best_global = island_best
                    termination_reason = "perfect_fitness"
                    gen_terminated = True
                    # Don't break -- process remaining results to update populations

                if step_reason == "budget_exhausted":
                    termination_reason = "budget_exhausted"
                    gen_terminated = True
                    # Don't break -- process remaining results to update populations

            # Cyclic migration (after all islands complete this generation)
            if not gen_terminated:
                self._migrate()
                await self._emit(
                    "migration",
                    {
                        "generation": gen + 1,
                        "emigrants_per_island": self._config.n_emigrate,
                    },
                )
                # Cap populations after migration
                self._select_survivors_all()

            # Island reset (at configured intervals, skipping generation 0)
            if (
                not gen_terminated
                and gen > 0
                and self._config.reset_interval > 0
                and gen % self._config.reset_interval == 0
            ):
                await self._reset_islands()

            # Track global best across all islands (higher = less penalized = better)
            for pop in self._island_populations:
                if pop:
                    island_best = pop[0]  # sorted by fitness desc
                    if island_best.fitness_score > best_global.fitness_score:
                        best_global = island_best

            # Aggregate generation record
            if island_records:
                agg = self._aggregate_records(gen + 1, island_records)
                generation_records.append(agg)

                # Emit generation_complete event (1-indexed for frontend)
                await self._emit(
                    "generation_complete",
                    {
                        "generation": gen + 1,
                        "best_fitness": agg.best_fitness,
                        "avg_fitness": agg.avg_fitness,
                        "best_normalized": agg.best_normalized,
                        "avg_normalized": agg.avg_normalized,
                        "candidates_evaluated": agg.candidates_evaluated,
                        "cost_usd": agg.cost_summary.get("total_cost_usd", 0.0),
                    },
                )

            if gen_terminated:
                break

        # Emit evolution_complete event
        await self._emit(
            "evolution_complete",
            {
                "termination_reason": termination_reason,
                "best_fitness": best_global.fitness_score,
                "best_normalized": best_global.normalized_score,
                "total_cost_usd": self._cost_tracker.summary().get("total_cost_usd", 0.0),
                "generations_completed": len(generation_records),
            },
        )

        return EvolutionResult(
            best_candidate=best_global,
            generation_records=generation_records,
            total_cost=self._cost_tracker.summary(),
            termination_reason=termination_reason,
            seed_evaluation=seed_report,
        )

    def _migrate(self) -> None:
        """Perform cyclic migration: top n_emigrate from island i -> island (i+1) % n.

        Skips if n_emigrate <= 0 or n_islands <= 1.
        Collects emigrants from all islands BEFORE modifying any (prevents order-dependence).
        Uses model_copy(deep=True) to prevent shared state between islands.
        """
        if self._config.n_emigrate <= 0 or self._config.n_islands <= 1:
            return

        n = self._config.n_islands

        # Collect emigrants from each island BEFORE modifying any
        # All candidates participate -- sort by fitness, take top
        emigrants: list[list[Candidate]] = []
        for pop in self._island_populations:
            sorted_pop = sorted(pop, key=lambda c: c.fitness_score, reverse=True)
            top = sorted_pop[: self._config.n_emigrate]
            emigrants.append([c.model_copy(deep=True) for c in top])

        # Inject emigrants into next island cyclically
        for i in range(n):
            target = (i + 1) % n
            for emigrant in emigrants[i]:
                original_id = emigrant.id
                emigrant.id = str(uuid.uuid4())
                self._island_populations[target].append(emigrant)
                if self._collector is not None:
                    self._collector.record(
                        LineageEvent(
                            candidate_id=emigrant.id,
                            parent_ids=[original_id],
                            generation=emigrant.generation,
                            island=target,
                            fitness_score=emigrant.fitness_score,
                            normalized_score=emigrant.normalized_score,
                            rejected=emigrant.rejected,
                            mutation_type="migrated",
                            template=emigrant.template,
                        )
                    )

        logger.info(
            "Migration complete: up to %d candidates moved per island",
            self._config.n_emigrate,
        )

    def _select_survivors_all(self) -> None:
        """Apply population cap to all islands after migration.

        Delegates to EvolutionLoop._select_survivors() for each island,
        preventing unbounded population growth from migration.
        """
        for i in range(len(self._island_populations)):
            self._island_populations[i] = self._loops[0]._select_survivors(
                self._island_populations[i]
            )

    async def _reset_islands(self) -> None:
        """Replace lowest-performing islands with top global candidates.

        - n_reset capped at n_islands - 1 (never reset all islands)
        - Mean fitness per island computed from all candidates
        - Skips if no global candidates exist (Pitfall 4)
        - Uses model_copy(deep=True) for replacement candidates
        """
        n_reset = min(self._config.n_reset, self._config.n_islands - 1)
        if n_reset <= 0:
            return

        # Compute mean fitness per island (all candidates participate)
        island_means: list[tuple[int, float]] = []
        for i, pop in enumerate(self._island_populations):
            mean_f = statistics.mean(c.fitness_score for c in pop) if pop else 0.0
            island_means.append((i, mean_f))

        # Sort ascending by mean fitness (worst/most negative first)
        island_means.sort(key=lambda x: x[1])

        # Collect top global candidates across all islands
        all_candidates: list[Candidate] = []
        for pop in self._island_populations:
            all_candidates.extend(pop)
        all_candidates.sort(key=lambda c: c.fitness_score, reverse=True)
        top_global = all_candidates[: self._config.n_top]

        if not top_global:
            logger.warning("No global candidates for island reset; skipping")
            return

        # Replace worst islands
        for i in range(n_reset):
            island_idx = island_means[i][0]
            new_pop = []
            for c in top_global:
                clone = c.model_copy(deep=True)
                source_id = clone.id
                clone.id = str(uuid.uuid4())
                new_pop.append(clone)
                if self._collector is not None:
                    self._collector.record(
                        LineageEvent(
                            candidate_id=clone.id,
                            parent_ids=[source_id],
                            generation=clone.generation,
                            island=island_idx,
                            fitness_score=clone.fitness_score,
                            normalized_score=clone.normalized_score,
                            rejected=clone.rejected,
                            mutation_type="reset",
                            template=clone.template,
                        )
                    )
            self._island_populations[island_idx] = new_pop
            logger.info(
                "Reset island %d (mean fitness %.3f) with %d top global candidates",
                island_idx,
                island_means[i][1],
                len(top_global),
            )

        # Emit island_reset event with list of reset island indices
        await self._emit(
            "island_reset",
            {
                "generation": self._current_generation,
                "islands_reset": [island_means[i][0] for i in range(n_reset)],
            },
        )

    def _aggregate_records(
        self, generation: int, island_records: list[GenerationRecord]
    ) -> GenerationRecord:
        """Create an aggregate GenerationRecord from per-island records.

        - best_fitness: max across all islands
        - avg_fitness: mean of island avg_fitnesses
        - candidates_evaluated: sum across all islands
        - cost_summary: summed deltas across island records
        """
        best_fitness = max(r.best_fitness for r in island_records)
        avg_fitness = statistics.mean(r.avg_fitness for r in island_records)
        best_normalized = max(r.best_normalized for r in island_records)
        avg_normalized = statistics.mean(r.avg_normalized for r in island_records)
        candidates_evaluated = sum(r.candidates_evaluated for r in island_records)

        # Aggregate cost summaries
        cost_summary: dict[str, float] = {}
        for record in island_records:
            for key, value in record.cost_summary.items():
                cost_summary[key] = cost_summary.get(key, 0) + value

        return GenerationRecord(
            generation=generation,
            best_fitness=best_fitness,
            avg_fitness=avg_fitness,
            best_normalized=best_normalized,
            avg_normalized=avg_normalized,
            cost_summary=cost_summary,
            candidates_evaluated=candidates_evaluated,
        )

    def _budget_exceeded(self) -> bool:
        """Check if the cost tracker total exceeds the configured budget cap.

        Returns False if no budget cap is configured.
        """
        if self._config.budget_cap_usd is None:
            return False
        return self._cost_tracker.summary()["total_cost_usd"] >= self._config.budget_cap_usd
