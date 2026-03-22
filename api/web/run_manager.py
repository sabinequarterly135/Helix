"""Background evolution run manager.

Manages asyncio tasks for evolution runs, tracking their status
and supporting cancellation. Provides start/stop/status/list operations
for the evolution API endpoints.

Exports:
    RunManager: Manages background evolution tasks
    RunInfo: Dataclass holding run metadata and task reference
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RunInfo:
    """Metadata for a single evolution run.

    Attributes:
        run_id: Unique identifier for the run.
        prompt_id: The prompt being evolved.
        task: The asyncio.Task executing the evolution.
        started_at: UTC timestamp when the run started.
        result: The evolution result, if completed successfully.
        error: Error message, if the run failed.
        event_bus: Optional EventBus reference for event emission on error/cancel.
        config: GeneConfig snapshot for DB persistence on completion.
        evolution_config: EvolutionConfig for DB persistence on completion.
    """

    run_id: str
    prompt_id: str
    task: asyncio.Task
    started_at: datetime
    result: Any = None
    error: str | None = None
    event_bus: Any = None
    config: Any = None
    evolution_config: Any = None
    effective_models: dict | None = None
    generation_config: Any = None
    thinking_config: dict | None = None


class RunManager:
    """Manages background evolution tasks.

    Tracks running tasks by run_id, provides status queries,
    supports cancellation, and cleans up on shutdown.
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunInfo] = {}

    async def start_run(
        self,
        prompt_id: str,
        coro_factory,
        event_bus=None,
        config=None,
        evolution_config=None,
        effective_models: dict | None = None,
        generation_config=None,
        thinking_config: dict | None = None,
    ) -> str:
        """Start a new evolution run as a background task.

        Args:
            prompt_id: The prompt being evolved.
            coro_factory: A callable that accepts an event_callback keyword
                argument and returns a coroutine. When event_bus is provided,
                an event_callback bound to the bus is created and passed to
                the factory. When event_bus is None, event_callback=None
                is passed.
            event_bus: Optional EventBus for event distribution. When
                provided, create_run is called and an event_callback
                closure is created that publishes events to the bus.
            config: GeneConfig for persisting results to DB on completion.
            evolution_config: EvolutionConfig for persisting results to DB.
            effective_models: Dict of effective model/provider names for DB persistence.
            generation_config: Optional GenerationConfig override for inference params.
            thinking_config: Optional per-role thinking config dict for Gemini models.

        Returns:
            The generated run_id string.
        """
        run_id = str(uuid.uuid4())

        if event_bus is not None:
            event_bus.create_run(run_id)

            async def event_callback(event_type: str, data: dict) -> None:
                await event_bus.publish(run_id, event_type, data)

            coro = coro_factory(event_callback=event_callback)
        else:
            coro = coro_factory(event_callback=None)

        task = asyncio.create_task(coro)
        info = RunInfo(
            run_id=run_id,
            prompt_id=prompt_id,
            task=task,
            started_at=datetime.now(UTC),
            event_bus=event_bus,
            config=config,
            evolution_config=evolution_config,
            effective_models=effective_models,
            generation_config=generation_config,
            thinking_config=thinking_config,
        )
        self._runs[run_id] = info
        task.add_done_callback(lambda t: self._on_complete(run_id, t))
        return run_id

    async def stop_run(self, run_id: str) -> bool:
        """Cancel a running evolution task.

        Args:
            run_id: The run to cancel.

        Returns:
            True if the task was cancelled, False if not found or already done.
        """
        info = self._runs.get(run_id)
        if info and not info.task.done():
            info.task.cancel()
            return True
        return False

    def get_status(self, run_id: str) -> dict | None:
        """Get the current status of a run.

        Args:
            run_id: The run to query.

        Returns:
            Dict with run_id, prompt_id, status, started_at,
            model/provider info, and hyperparameters, or None if not found.
        """
        info = self._runs.get(run_id)
        if not info:
            return None
        if not info.task.done():
            status = "running"
        elif info.task.cancelled():
            status = "cancelled"
        elif info.error:
            status = "failed"
        else:
            status = "completed"

        models = info.effective_models or {}
        result = {
            "run_id": run_id,
            "prompt_id": info.prompt_id,
            "status": status,
            "started_at": info.started_at.isoformat(),
            "meta_model": models.get("meta_model"),
            "meta_provider": models.get("meta_provider"),
            "target_model": models.get("target_model"),
            "target_provider": models.get("target_provider"),
            "judge_model": models.get("judge_model"),
            "judge_provider": models.get("judge_provider"),
        }

        if info.evolution_config is not None:
            result["hyperparameters"] = self._build_hyperparameters(info.evolution_config, info)

        return result

    def list_runs(self) -> list[dict]:
        """List all tracked runs with their current status."""
        return [self.get_status(rid) for rid in self._runs]

    async def shutdown(self) -> None:
        """Cancel all running tasks and wait for cleanup."""
        for info in self._runs.values():
            if not info.task.done():
                info.task.cancel()
        # Wait briefly for tasks to handle cancellation
        tasks = [info.task for info in self._runs.values() if not info.task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _on_complete(self, run_id: str, task: asyncio.Task) -> None:
        """Callback when a task finishes -- record result or error.

        On error or cancellation, emits an evolution_complete event
        via the EventBus (the engine itself emits this on success,
        so we only handle failure/cancel paths here).

        On success, persists results to the database (best-effort).
        """
        info = self._runs.get(run_id)
        if not info:
            return

        if task.cancelled():
            info.error = "cancelled"
            # Engine didn't get to emit evolution_complete, so we do it
            if info.event_bus is not None:
                asyncio.ensure_future(
                    info.event_bus.publish(
                        run_id,
                        "evolution_complete",
                        {
                            "termination_reason": "cancelled",
                            "error": None,
                        },
                    )
                )
        elif task.exception():
            info.error = str(task.exception())
            # Engine didn't get to emit evolution_complete, so we do it
            if info.event_bus is not None:
                asyncio.ensure_future(
                    info.event_bus.publish(
                        run_id,
                        "evolution_complete",
                        {
                            "termination_reason": "error",
                            "error": info.error,
                        },
                    )
                )
        else:
            info.result = task.result()
            # On success, the evolution engine itself already emitted
            # evolution_complete -- no duplicate emission needed.
            # Persist results to database (best-effort)
            if info.config and info.evolution_config:
                asyncio.ensure_future(self._persist_result(info))

    @staticmethod
    def _build_hyperparameters(evo_config, info: RunInfo) -> dict:
        """Build hyperparameters dict, merging inference and thinking overrides if present."""
        hyper_dict = evo_config.model_dump()
        if info.generation_config is not None:
            hyper_dict["inference"] = info.generation_config.model_dump()
        if info.thinking_config:
            hyper_dict["thinking"] = info.thinking_config
        return hyper_dict

    async def _persist_result(self, info: RunInfo) -> None:
        """Persist evolution results to the database (best-effort).

        Extracts lineage events, case results, generation records, and
        termination reason from the EvolutionResult and stores them in
        the EvolutionRun.extra_metadata JSON column.
        """
        try:
            from api.storage.database import Database
            from api.storage.models import EvolutionRun

            result = info.result
            config = info.config
            evo_config = info.evolution_config

            # Build extra_metadata with all visualization data
            extra_metadata: dict = {}
            if result.lineage_events:
                extra_metadata["lineage_events"] = result.lineage_events
            if result.best_candidate and result.best_candidate.evaluation:
                extra_metadata["case_results"] = [
                    cr.model_dump(exclude={"otel"})
                    for cr in result.best_candidate.evaluation.case_results
                ]
                extra_metadata["best_candidate_id"] = result.best_candidate.id
            if result.seed_evaluation:
                extra_metadata["seed_case_results"] = [
                    cr.model_dump(exclude={"otel"}) for cr in result.seed_evaluation.case_results
                ]
            if result.generation_records:
                extra_metadata["generation_records"] = [
                    gr.model_dump() for gr in result.generation_records
                ]
            extra_metadata["termination_reason"] = result.termination_reason
            extra_metadata["best_normalized_score"] = result.best_candidate.normalized_score

            db = Database(config.database_url)
            session = await db.get_session()
            try:
                # Use effective_models for model/provider columns if available
                models = info.effective_models or {}
                status_map = {
                    "budget_exhausted": "budget_exhausted",
                    "error": "error",
                }
                status = status_map.get(result.termination_reason, "completed")
                run = EvolutionRun(
                    prompt_id=info.prompt_id,
                    status=status,
                    run_uuid=info.run_id,
                    meta_model=models.get("meta_model", config.meta_model),
                    target_model=models.get("target_model", config.target_model),
                    judge_model=models.get("judge_model", config.judge_model),
                    meta_provider=models.get("meta_provider"),
                    target_provider=models.get("target_provider"),
                    judge_provider=models.get("judge_provider"),
                    hyperparameters=self._build_hyperparameters(evo_config, info),
                    total_input_tokens=result.total_cost.get("total_input_tokens", 0),
                    total_output_tokens=result.total_cost.get("total_output_tokens", 0),
                    total_cost_usd=result.total_cost.get("total_cost_usd", 0.0),
                    total_api_calls=result.total_cost.get("total_calls", 0),
                    best_fitness_score=result.best_candidate.fitness_score,
                    generations_completed=len(result.generation_records),
                    extra_metadata=extra_metadata or None,
                )
                session.add(run)
                await session.commit()
                # Ensure run_uuid is persisted (workaround for SQLAlchemy mapping issue)
                if run.id and info.run_id:
                    from sqlalchemy import update

                    await session.execute(
                        update(EvolutionRun)
                        .where(EvolutionRun.id == run.id)
                        .values(run_uuid=info.run_id)
                    )
                    await session.commit()
                logger.info(
                    "Persisted evolution run for %s (uuid=%s) to database",
                    info.prompt_id,
                    info.run_id,
                )
            finally:
                await session.close()
                await db.close()
        except Exception:
            logger.exception("Failed to persist evolution result to database")
