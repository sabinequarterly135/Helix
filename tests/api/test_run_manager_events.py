"""Tests for RunManager + EventBus integration.

Tests verify:
- RunManager.start_run with event_bus creates event_callback and passes to coro_factory
- evolution_complete event published on successful completion (from engine, not RunManager)
- evolution_complete event published on error (from RunManager)
- evolution_complete event published on cancellation (from RunManager)
- EventBus is created in app lifespan and available at app.state.event_bus
- Existing RunManager tests still pass (backward compatible)
"""

from __future__ import annotations

import asyncio


from api.web.event_bus import EventBus
from api.web.run_manager import RunManager


# ---------------------------------------------------------------------------
# Tests: RunManager + EventBus integration
# ---------------------------------------------------------------------------


async def test_start_run_with_event_bus_creates_callback():
    """RunManager.start_run with event_bus creates an event_callback and passes it to coro_factory."""
    rm = RunManager()
    bus = EventBus()

    received_callback = None

    async def coro_factory(event_callback=None):
        nonlocal received_callback
        received_callback = event_callback
        if event_callback is not None:
            await event_callback("test_event", {"key": "value"})

    run_id = await rm.start_run("test-prompt", coro_factory, event_bus=bus)
    # Wait for the task to complete
    await asyncio.sleep(0.1)

    # The factory should have received a non-None callback
    assert received_callback is not None

    # The event should have been published to the bus
    queue, missed = bus.subscribe(run_id)
    assert len(missed) >= 1
    assert missed[0].type == "test_event"


async def test_start_run_without_event_bus_passes_none_callback():
    """RunManager.start_run without event_bus passes event_callback=None to coro_factory."""
    rm = RunManager()

    received_callback = "not_set"

    async def coro_factory(event_callback=None):
        nonlocal received_callback
        received_callback = event_callback

    await rm.start_run("test-prompt", coro_factory)
    await asyncio.sleep(0.1)

    assert received_callback is None


async def test_evolution_complete_emitted_on_error():
    """When evolution task fails, RunManager emits evolution_complete with error info."""
    rm = RunManager()
    bus = EventBus()

    async def coro_factory(event_callback=None):
        raise RuntimeError("test error")

    run_id = await rm.start_run("test-prompt", coro_factory, event_bus=bus)
    # Wait for the task to complete and callbacks to fire
    await asyncio.sleep(0.2)

    queue, missed = bus.subscribe(run_id)
    # Should have an evolution_complete event
    evo_complete = [e for e in missed if e.type == "evolution_complete"]
    assert len(evo_complete) >= 1
    assert evo_complete[0].data.get("termination_reason") == "error"
    assert "test error" in evo_complete[0].data.get("error", "")


async def test_evolution_complete_emitted_on_cancel():
    """When evolution task is cancelled, RunManager emits evolution_complete with cancelled status."""
    rm = RunManager()
    bus = EventBus()

    async def coro_factory(event_callback=None):
        await asyncio.sleep(60)  # Long running to allow cancellation

    run_id = await rm.start_run("test-prompt", coro_factory, event_bus=bus)
    await asyncio.sleep(0.05)

    await rm.stop_run(run_id)
    # Wait for cancellation callback to fire
    await asyncio.sleep(0.2)

    queue, missed = bus.subscribe(run_id)
    evo_complete = [e for e in missed if e.type == "evolution_complete"]
    assert len(evo_complete) >= 1
    assert evo_complete[0].data.get("termination_reason") == "cancelled"


async def test_no_duplicate_evolution_complete_on_success():
    """On success, RunManager does NOT emit evolution_complete (engine already did)."""
    rm = RunManager()
    bus = EventBus()

    async def coro_factory(event_callback=None):
        # Simulate what the engine does: emit evolution_complete itself
        if event_callback is not None:
            await event_callback(
                "evolution_complete",
                {
                    "termination_reason": "generations_complete",
                    "best_fitness": 0.9,
                },
            )

    run_id = await rm.start_run("test-prompt", coro_factory, event_bus=bus)
    await asyncio.sleep(0.2)

    queue, missed = bus.subscribe(run_id)
    evo_complete = [e for e in missed if e.type == "evolution_complete"]
    # Should have exactly 1 evolution_complete (from engine, not from RunManager)
    assert len(evo_complete) == 1
    assert evo_complete[0].data.get("termination_reason") == "generations_complete"


# ---------------------------------------------------------------------------
# Tests: EventBus on app.state
# ---------------------------------------------------------------------------


async def test_event_bus_on_app_state():
    """EventBus is created in app lifespan and available at app.state.event_bus."""
    from api.web.app import create_app

    app = create_app()

    # Simulate lifespan by using the async context manager directly
    async with app.router.lifespan_context(app):
        assert hasattr(app.state, "event_bus")
        assert isinstance(app.state.event_bus, EventBus)


# ---------------------------------------------------------------------------
# Tests: Error-terminated runs still persist via success path (BUG-05)
# ---------------------------------------------------------------------------


async def test_error_terminated_run_uses_success_path():
    """When IslandEvolver catches GatewayError and returns EvolutionResult(termination_reason='error'),
    RunManager._on_complete sees a successful task (no exception) and sets info.result.

    This proves that catching GatewayError inside IslandEvolver means the success
    branch of _on_complete runs, which triggers _persist_result.
    """
    rm = RunManager()
    bus = EventBus()

    # Simulate what IslandEvolver now does: catch GatewayError and return
    # an EvolutionResult with termination_reason="error" (instead of raising)
    class FakeResult:
        termination_reason = "error"

    async def coro_factory(event_callback=None):
        # Emit evolution_complete like the engine does
        if event_callback is not None:
            await event_callback(
                "evolution_complete",
                {
                    "termination_reason": "error",
                    "best_fitness": 0.5,
                },
            )
        return FakeResult()

    run_id = await rm.start_run("test-prompt", coro_factory, event_bus=bus)
    await asyncio.sleep(0.2)

    info = rm._runs[run_id]
    # Success path: result is set, error is None
    assert info.result is not None
    assert info.error is None
    assert info.result.termination_reason == "error"

    # Task completed normally (no exception)
    assert info.task.exception() is None


async def test_error_terminated_run_status_shows_completed():
    """Error-terminated runs show 'completed' status (not 'failed') since the task
    succeeded -- the error was gracefully handled by IslandEvolver."""
    rm = RunManager()

    class FakeResult:
        termination_reason = "error"

    async def coro_factory(event_callback=None):
        return FakeResult()

    run_id = await rm.start_run("test-prompt", coro_factory)
    await asyncio.sleep(0.2)

    status = rm.get_status(run_id)
    assert status["status"] == "completed"


# ---------------------------------------------------------------------------
# Tests: Backward compatibility
# ---------------------------------------------------------------------------


async def test_run_manager_basic_operations_still_work():
    """Existing RunManager operations (status, list, stop, shutdown) work with coro_factory pattern."""
    rm = RunManager()

    async def coro_factory(event_callback=None):
        await asyncio.sleep(0.5)
        return "result"

    run_id = await rm.start_run("test-prompt", coro_factory)
    await asyncio.sleep(0.05)

    # Check status
    status = rm.get_status(run_id)
    assert status is not None
    assert status["status"] == "running"
    assert status["prompt_id"] == "test-prompt"

    # List runs
    runs = rm.list_runs()
    assert len(runs) == 1

    # Stop run
    stopped = await rm.stop_run(run_id)
    assert stopped is True

    await asyncio.sleep(0.1)
    status = rm.get_status(run_id)
    assert status["status"] == "cancelled"

    # Shutdown
    await rm.shutdown()
