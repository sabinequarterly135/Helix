"""Tests for LLMMocker: LLM-based tool mock response generation.

Covers:
- Successful JSON generation from LLM
- Scenario types (success, failure, edge_case) in system prompt
- Error handling (LLM exception, invalid JSON)
- Session cache (hit, miss on different scenario_type)
- generate_sample preview method
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.registry.llm_mocker import LLMMocker
from api.types import LLMResponse, ModelRole


@pytest.fixture
def mock_provider():
    """Create a mock LLMProvider with AsyncMock chat_completion."""
    provider = MagicMock()
    provider.chat_completion = AsyncMock()
    return provider


@pytest.fixture
def format_guide_examples() -> list[str]:
    """Sample format guide examples for a transfer tool."""
    return [
        '{"status": "success", "department": "sales", "wait_time": 30}',
        '{"status": "success", "department": "support", "wait_time": 45}',
    ]


def _make_llm_response(content: str) -> LLMResponse:
    """Helper to create an LLMResponse with given content."""
    from datetime import datetime, timezone

    return LLMResponse(
        content=content,
        model_used="test-model",
        role=ModelRole.TOOL_MOCKER,
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
        timestamp=datetime.now(timezone.utc),
    )


class TestGenerateMockResponse:
    """Tests for LLMMocker.generate_mock_response."""

    async def test_returns_valid_json_string(self, mock_provider, format_guide_examples):
        """LLMMocker.generate_mock_response returns valid JSON string when provider returns JSON."""
        valid_json = '{"status": "success", "department": "billing", "wait_time": 15}'
        mock_provider.chat_completion.return_value = _make_llm_response(valid_json)

        mocker = LLMMocker(provider=mock_provider, model="test-model")
        result = await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "billing"},
            format_guide_examples=format_guide_examples,
        )

        assert result == valid_json
        mock_provider.chat_completion.assert_called_once()

    async def test_failure_scenario_includes_failure_context(
        self, mock_provider, format_guide_examples
    ):
        """LLMMocker.generate_mock_response with scenario_type='failure' includes failure context."""
        failure_json = '{"status": "error", "message": "Department not found"}'
        mock_provider.chat_completion.return_value = _make_llm_response(failure_json)

        mocker = LLMMocker(provider=mock_provider, model="test-model")
        result = await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "unknown"},
            format_guide_examples=format_guide_examples,
            scenario_type="failure",
        )

        assert result == failure_json
        # Verify system prompt mentions failure scenario
        call_args = mock_provider.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert (
            "failure" in system_msg["content"].lower() or "error" in system_msg["content"].lower()
        )

    async def test_edge_case_scenario_includes_edge_case_context(
        self, mock_provider, format_guide_examples
    ):
        """LLMMocker.generate_mock_response with scenario_type='edge_case' includes edge-case context."""
        edge_json = '{"status": "success", "department": "", "wait_time": 0}'
        mock_provider.chat_completion.return_value = _make_llm_response(edge_json)

        mocker = LLMMocker(provider=mock_provider, model="test-model")
        result = await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "edge"},
            format_guide_examples=format_guide_examples,
            scenario_type="edge_case",
        )

        assert result == edge_json
        call_args = mock_provider.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "edge" in system_msg["content"].lower()

    async def test_returns_none_on_llm_exception(self, mock_provider, format_guide_examples):
        """LLMMocker.generate_mock_response returns None when LLM call raises an exception."""
        mock_provider.chat_completion.side_effect = Exception("API timeout")

        mocker = LLMMocker(provider=mock_provider, model="test-model")
        result = await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "sales"},
            format_guide_examples=format_guide_examples,
        )

        assert result is None

    async def test_returns_none_on_invalid_json(self, mock_provider, format_guide_examples):
        """LLMMocker.generate_mock_response returns None when LLM returns invalid JSON."""
        mock_provider.chat_completion.return_value = _make_llm_response(
            "This is not valid JSON at all"
        )

        mocker = LLMMocker(provider=mock_provider, model="test-model")
        result = await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "sales"},
            format_guide_examples=format_guide_examples,
        )

        assert result is None


class TestSessionCache:
    """Tests for session cache behavior."""

    async def test_cache_returns_same_result_for_identical_inputs(
        self, mock_provider, format_guide_examples
    ):
        """Session cache returns same result for identical (tool_name, args_hash, scenario_type)."""
        valid_json = '{"status": "success", "department": "sales", "wait_time": 30}'
        mock_provider.chat_completion.return_value = _make_llm_response(valid_json)

        mocker = LLMMocker(provider=mock_provider, model="test-model")

        # First call - should hit LLM
        result1 = await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "sales"},
            format_guide_examples=format_guide_examples,
        )

        # Second call with same inputs - should return cached
        result2 = await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "sales"},
            format_guide_examples=format_guide_examples,
        )

        assert result1 == result2
        # LLM should only be called once
        assert mock_provider.chat_completion.call_count == 1

    async def test_cache_returns_different_result_for_different_scenario_type(
        self, mock_provider, format_guide_examples
    ):
        """Session cache returns different result for different scenario_type."""
        success_json = '{"status": "success"}'
        failure_json = '{"status": "error"}'

        mock_provider.chat_completion.side_effect = [
            _make_llm_response(success_json),
            _make_llm_response(failure_json),
        ]

        mocker = LLMMocker(provider=mock_provider, model="test-model")

        result_success = await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "sales"},
            format_guide_examples=format_guide_examples,
            scenario_type="success",
        )

        result_failure = await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "sales"},
            format_guide_examples=format_guide_examples,
            scenario_type="failure",
        )

        assert result_success == success_json
        assert result_failure == failure_json
        # LLM should be called twice (different scenario_type = different cache key)
        assert mock_provider.chat_completion.call_count == 2


class TestGenerateSample:
    """Tests for LLMMocker.generate_sample preview."""

    async def test_generate_sample_returns_preview(self, mock_provider, format_guide_examples):
        """LLMMocker.generate_sample returns a preview response string."""
        sample_json = '{"status": "success", "department": "demo", "wait_time": 10}'
        mock_provider.chat_completion.return_value = _make_llm_response(sample_json)

        mocker = LLMMocker(provider=mock_provider, model="test-model")
        result = await mocker.generate_sample(
            tool_name="transfer_to_number",
            format_guide_examples=format_guide_examples,
        )

        assert result == sample_json
        mock_provider.chat_completion.assert_called_once()


class TestClearCache:
    """Tests for cache clearing."""

    async def test_clear_cache_empties_session_cache(self, mock_provider, format_guide_examples):
        """clear_cache() empties the session cache, forcing a new LLM call."""
        valid_json = '{"status": "success"}'
        mock_provider.chat_completion.return_value = _make_llm_response(valid_json)

        mocker = LLMMocker(provider=mock_provider, model="test-model")

        # First call
        await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "sales"},
            format_guide_examples=format_guide_examples,
        )

        mocker.clear_cache()

        # Second call after clear should hit LLM again
        await mocker.generate_mock_response(
            tool_name="transfer_to_number",
            call_args={"target": "sales"},
            format_guide_examples=format_guide_examples,
        )

        assert mock_provider.chat_completion.call_count == 2
