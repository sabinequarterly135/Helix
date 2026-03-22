"""Tests for evolution start/stop/status endpoints.

All tests mock run_evolution to avoid real LLM calls.
Uses the shared conftest fixtures (app, client, prompts_dir).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from api.config.models import GenerationConfig
from api.evolution.models import Candidate, EvolutionResult


# -- Helpers --


def _make_evolution_result() -> EvolutionResult:
    """Create a minimal EvolutionResult for mocking."""
    return EvolutionResult(
        best_candidate=Candidate(template="evolved prompt", fitness_score=0.95),
        generation_records=[],
        total_cost={"total_cost_usd": 0.01},
        termination_reason="generations_complete",
    )


async def _setup_prompt_with_cases(
    client: httpx.AsyncClient, prompt_id: str = "test-prompt"
) -> None:
    """Register a prompt and add a test case, both via API."""
    # Register prompt via API (creates DB row)
    await client.post(
        "/api/prompts/",
        json={
            "id": prompt_id,
            "purpose": "Test prompt for evolution",
            "template": "Hello {{ name }}",
        },
    )
    # Add a test case via API (uses DB-backed DatasetService)
    await client.post(
        f"/api/prompts/{prompt_id}/dataset",
        json={
            "name": "test case 1",
            "variables": {"name": "world"},
            "expected_output": {"contains": "Hello"},
        },
    )


async def _setup_prompt_no_cases(
    client: httpx.AsyncClient, prompt_id: str = "empty-prompt"
) -> None:
    """Register a prompt via API with no test cases."""
    await client.post(
        "/api/prompts/",
        json={
            "id": prompt_id,
            "purpose": "Empty prompt for testing",
            "template": "Hello {{ name }}",
        },
    )


# -- POST /api/evolution/start --


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_start_run_returns_run_id(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """POST /api/evolution/start returns run_id and status 'running'."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    resp = await client.post(
        "/api/evolution/start",
        json={"prompt_id": "test-prompt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "running"
    assert data["prompt_id"] == "test-prompt"
    assert "started_at" in data


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_start_run_no_cases_returns_400(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """POST /api/evolution/start with no test cases returns 400."""
    await _setup_prompt_no_cases(client)

    resp = await client.post(
        "/api/evolution/start",
        json={"prompt_id": "empty-prompt"},
    )
    assert resp.status_code == 400
    assert "No test cases" in resp.json()["detail"]


async def test_start_run_nonexistent_prompt_returns_404(
    client: httpx.AsyncClient,
):
    """POST /api/evolution/start with nonexistent prompt returns 404."""
    resp = await client.post(
        "/api/evolution/start",
        json={"prompt_id": "nonexistent-prompt"},
    )
    assert resp.status_code == 404


# -- POST /api/evolution/{run_id}/stop --


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_stop_run_cancels_task(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """POST /api/evolution/{run_id}/stop cancels a running task."""

    # Mock a long-running coroutine so the task is still running when we stop it
    async def _long_running(*args, **kwargs):
        await asyncio.sleep(60)

    mock_run_evolution.side_effect = _long_running

    await _setup_prompt_with_cases(client)

    # Start a run
    start_resp = await client.post(
        "/api/evolution/start",
        json={"prompt_id": "test-prompt"},
    )
    assert start_resp.status_code == 200
    run_id = start_resp.json()["run_id"]
    assert start_resp.json()["status"] == "running"

    # Give the event loop a moment to start the task
    await asyncio.sleep(0.05)

    # Stop the run
    stop_resp = await client.post(f"/api/evolution/{run_id}/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["status"] == "cancelled"

    # Give the event loop a moment to process cancellation
    await asyncio.sleep(0.05)

    # Verify status shows cancelled
    status_resp = await client.get(f"/api/evolution/{run_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "cancelled"


async def test_stop_nonexistent_run_returns_404(
    client: httpx.AsyncClient,
):
    """POST /api/evolution/fake-id/stop returns 404."""
    resp = await client.post("/api/evolution/fake-id/stop")
    assert resp.status_code == 404


# -- GET /api/evolution/{run_id}/status --


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_get_status(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """GET /api/evolution/{run_id}/status returns correct fields."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    start_resp = await client.post(
        "/api/evolution/start",
        json={"prompt_id": "test-prompt"},
    )
    run_id = start_resp.json()["run_id"]

    status_resp = await client.get(f"/api/evolution/{run_id}/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["run_id"] == run_id
    assert data["prompt_id"] == "test-prompt"
    assert data["status"] in ("running", "completed")
    assert "started_at" in data


async def test_get_status_nonexistent_returns_404(
    client: httpx.AsyncClient,
):
    """GET /api/evolution/fake-id/status returns 404."""
    resp = await client.get("/api/evolution/fake-id/status")
    assert resp.status_code == 404


# -- Model/provider override threading --


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_start_run_accepts_model_overrides(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """POST /api/evolution/start accepts model/provider override fields in request body."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    resp = await client.post(
        "/api/evolution/start",
        json={
            "prompt_id": "test-prompt",
            "meta_model": "custom-meta",
            "meta_provider": "gemini",
            "target_model": "custom-target",
            "target_provider": "openrouter",
            "judge_model": "custom-judge",
            "judge_provider": "gemini",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_start_run_threads_overrides_to_run_evolution(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """Override fields from request body are passed through to run_evolution kwargs."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    await client.post(
        "/api/evolution/start",
        json={
            "prompt_id": "test-prompt",
            "meta_model": "custom-meta",
            "target_provider": "gemini",
        },
    )

    # Wait briefly for the task to invoke run_evolution
    await asyncio.sleep(0.1)

    # Verify run_evolution was called with override kwargs
    mock_run_evolution.assert_called_once()
    call_kwargs = mock_run_evolution.call_args
    # The overrides should be passed as keyword arguments
    assert call_kwargs.kwargs.get("meta_model") == "custom-meta"
    assert call_kwargs.kwargs.get("target_provider") == "gemini"
    # Non-specified overrides should be None
    assert call_kwargs.kwargs.get("meta_provider") is None
    assert call_kwargs.kwargs.get("target_model") is None
    assert call_kwargs.kwargs.get("judge_model") is None
    assert call_kwargs.kwargs.get("judge_provider") is None


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_start_run_empty_overrides_passed_as_none(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """Empty string overrides are converted to None before passing to run_evolution."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    await client.post(
        "/api/evolution/start",
        json={
            "prompt_id": "test-prompt",
            "meta_model": "",
            "target_provider": "",
        },
    )

    # Wait briefly for the task to invoke run_evolution
    await asyncio.sleep(0.1)

    mock_run_evolution.assert_called_once()
    call_kwargs = mock_run_evolution.call_args
    # Empty strings should be converted to None
    assert call_kwargs.kwargs.get("meta_model") is None
    assert call_kwargs.kwargs.get("target_provider") is None


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_start_run_no_overrides_passes_none(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """When no override fields are provided, all override kwargs are None."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    await client.post(
        "/api/evolution/start",
        json={"prompt_id": "test-prompt"},
    )

    # Wait briefly for the task to invoke run_evolution
    await asyncio.sleep(0.1)

    mock_run_evolution.assert_called_once()
    call_kwargs = mock_run_evolution.call_args
    assert call_kwargs.kwargs.get("meta_model") is None
    assert call_kwargs.kwargs.get("meta_provider") is None
    assert call_kwargs.kwargs.get("target_model") is None
    assert call_kwargs.kwargs.get("target_provider") is None
    assert call_kwargs.kwargs.get("judge_model") is None
    assert call_kwargs.kwargs.get("judge_provider") is None


# -- Advanced evolution params + inference params threading --


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_start_run_accepts_advanced_params(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """POST /api/evolution/start threads advanced evolution params to EvolutionConfig."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    resp = await client.post(
        "/api/evolution/start",
        json={
            "prompt_id": "test-prompt",
            "n_seq": 5,
            "population_cap": 20,
            "n_emigrate": 3,
            "reset_interval": 5,
            "n_reset": 3,
            "n_top": 8,
        },
    )
    assert resp.status_code == 200

    # Wait briefly for the task to invoke run_evolution
    await asyncio.sleep(0.1)

    mock_run_evolution.assert_called_once()
    # The evolution_config is the 4th positional arg (index 3)
    evo_config = mock_run_evolution.call_args[0][3]
    assert evo_config.n_seq == 5
    assert evo_config.population_cap == 20
    assert evo_config.n_emigrate == 3
    assert evo_config.reset_interval == 5
    assert evo_config.n_reset == 3
    assert evo_config.n_top == 8


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_start_run_threads_inference_params(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """POST /api/evolution/start threads inference params as generation_config kwarg."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    resp = await client.post(
        "/api/evolution/start",
        json={
            "prompt_id": "test-prompt",
            "inference_temperature": 0.5,
            "top_p": 0.9,
            "top_k": 40,
            "max_tokens": 2048,
            "frequency_penalty": 0.3,
            "presence_penalty": 0.1,
        },
    )
    assert resp.status_code == 200

    # Wait briefly for the task to invoke run_evolution
    await asyncio.sleep(0.1)

    mock_run_evolution.assert_called_once()
    gen_config = mock_run_evolution.call_args.kwargs.get("generation_config")
    assert gen_config is not None
    assert isinstance(gen_config, GenerationConfig)
    assert gen_config.temperature == 0.5
    assert gen_config.top_p == 0.9
    assert gen_config.top_k == 40
    assert gen_config.max_tokens == 2048
    assert gen_config.frequency_penalty == 0.3
    assert gen_config.presence_penalty == 0.1


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_start_run_no_inference_params_passes_none(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """When no inference fields provided, generation_config kwarg is None."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    resp = await client.post(
        "/api/evolution/start",
        json={"prompt_id": "test-prompt"},
    )
    assert resp.status_code == 200

    # Wait briefly for the task to invoke run_evolution
    await asyncio.sleep(0.1)

    mock_run_evolution.assert_called_once()
    gen_config = mock_run_evolution.call_args.kwargs.get("generation_config")
    assert gen_config is None


# -- Thinking config threading --


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_thinking_config_threaded_to_run_evolution(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """POST with thinking fields builds thinking_config dict and passes to run_evolution."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    resp = await client.post(
        "/api/evolution/start",
        json={
            "prompt_id": "test-prompt",
            "meta_thinking_budget": 1024,
            "target_thinking_level": "low",
        },
    )
    assert resp.status_code == 200

    # Wait briefly for the task to invoke run_evolution
    await asyncio.sleep(0.1)

    mock_run_evolution.assert_called_once()
    thinking_config = mock_run_evolution.call_args.kwargs.get("thinking_config")
    assert thinking_config is not None
    assert thinking_config["meta"] == {"thinking_budget": 1024}
    assert thinking_config["target"] == {"thinking_level": "low"}
    # Judge not specified, so should not be in the dict
    assert "judge" not in thinking_config


@patch(
    "api.evolution.runner.run_evolution",
    new_callable=AsyncMock,
)
async def test_no_thinking_config_default(
    mock_run_evolution: AsyncMock,
    client: httpx.AsyncClient,
):
    """When no thinking fields provided, thinking_config kwarg is None."""
    mock_run_evolution.return_value = _make_evolution_result()

    await _setup_prompt_with_cases(client)

    resp = await client.post(
        "/api/evolution/start",
        json={"prompt_id": "test-prompt"},
    )
    assert resp.status_code == 200

    # Wait briefly for the task to invoke run_evolution
    await asyncio.sleep(0.1)

    mock_run_evolution.assert_called_once()
    thinking_config = mock_run_evolution.call_args.kwargs.get("thinking_config")
    assert thinking_config is None
