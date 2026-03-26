"""Tests for LiteLLMProvider (unified OpenAI SDK provider).

Tests cover model name handling, chat completion, error handling,
cost tracking, tool calls, thinking config, and context manager.
"""

from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from api.exceptions import GatewayError, RetryableError
from api.gateway.litellm_provider import LiteLLMProvider
from api.types import ModelRole


def _mock_completion(
    content="Hello!",
    model="gemini-2.5-flash",
    prompt_tokens=10,
    completion_tokens=5,
    response_id="gen-123",
    tool_calls=None,
    finish_reason="stop",
):
    """Create a mock OpenAI ChatCompletion response."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.model = model
    response.id = response_id

    return response


class TestProviderInit:
    """Test provider initialization and base_url selection."""

    def test_gemini_base_url(self):
        provider = LiteLLMProvider(provider="gemini", api_key="k")
        assert provider._provider == "gemini"
        assert "generativelanguage.googleapis.com" in str(provider._client.base_url)

    def test_openrouter_base_url(self):
        provider = LiteLLMProvider(provider="openrouter", api_key="k")
        assert "openrouter.ai" in str(provider._client.base_url)

    def test_openai_base_url(self):
        provider = LiteLLMProvider(provider="openai", api_key="k")
        assert "api.openai.com" in str(provider._client.base_url)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            LiteLLMProvider(provider="unsupported", api_key="k")


class TestModelNameNormalization:
    """Test model name normalization for different providers."""

    def test_gemini_strips_google_prefix(self):
        provider = LiteLLMProvider(provider="gemini", api_key="k")
        assert provider._normalize_model("google/gemini-3-flash-preview") == "gemini-3-flash-preview"

    def test_gemini_preserves_plain_name(self):
        provider = LiteLLMProvider(provider="gemini", api_key="k")
        assert provider._normalize_model("gemini-2.5-flash") == "gemini-2.5-flash"

    def test_openrouter_keeps_google_prefix(self):
        provider = LiteLLMProvider(provider="openrouter", api_key="k")
        assert provider._normalize_model("google/gemini-3-flash-preview") == "google/gemini-3-flash-preview"

    def test_openai_keeps_model_unchanged(self):
        provider = LiteLLMProvider(provider="openai", api_key="k")
        assert provider._normalize_model("gpt-4o") == "gpt-4o"

    async def test_gemini_chat_completion_strips_prefix(self):
        """Model name is normalized before API call."""
        mock_response = _mock_completion(model="gemini-3-flash-preview")
        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="google/gemini-3-flash-preview",
            role=ModelRole.TARGET,
        )

        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3-flash-preview"


class TestChatCompletion:
    """Test basic chat completion functionality."""

    async def test_chat_completion_success(self):
        """Returns LLMResponse with correct fields."""
        mock_response = _mock_completion(
            content="Test response",
            prompt_tokens=100,
            completion_tokens=50,
        )

        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gemini-2.5-flash",
            role=ModelRole.TARGET,
        )

        assert response.content == "Test response"
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.role == ModelRole.TARGET
        assert response.generation_id == "gen-123"
        assert response.finish_reason == "stop"

    async def test_chat_completion_with_tool_calls(self):
        """Extracts tool_calls from response."""
        tc = MagicMock()
        tc.model_dump.return_value = {
            "id": "call_123",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"location": "SF"}'},
        }
        mock_response = _mock_completion(tool_calls=[tc])

        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Weather?"}],
            model="gemini-2.5-flash",
            role=ModelRole.TARGET,
        )

        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["function"]["name"] == "get_weather"

    async def test_kwargs_passed_through(self):
        """Additional kwargs like temperature are passed to the SDK."""
        mock_response = _mock_completion()

        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gemini-2.5-flash",
            role=ModelRole.TARGET,
            temperature=0.5,
            max_tokens=100,
        )

        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 100

    async def test_extra_body_passed_through(self):
        """extra_body for Gemini thinking config is passed to SDK."""
        mock_response = _mock_completion()

        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gemini-2.5-pro",
            role=ModelRole.TARGET,
            extra_body={"google": {"thinking_config": {"thinking_budget": 2048}}},
        )

        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["extra_body"]["google"]["thinking_config"]["thinking_budget"] == 2048


class TestErrorHandling:
    """Test error mapping from OpenAI exceptions to our exceptions."""

    async def test_rate_limit_raises_retryable(self):
        """Rate limit errors raise RetryableError."""
        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError(
                message="Rate limited",
                response=MagicMock(status_code=429),
                body=None,
            )
        )

        with pytest.raises(RetryableError):
            await provider.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="gemini-2.5-flash",
                role=ModelRole.TARGET,
            )

    async def test_server_error_raises_retryable(self):
        """500 errors raise RetryableError."""
        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=openai.InternalServerError(
                message="Server error",
                response=MagicMock(status_code=500),
                body=None,
            )
        )

        with pytest.raises(RetryableError):
            await provider.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="gemini-2.5-flash",
                role=ModelRole.TARGET,
            )

    async def test_bad_request_raises_gateway_error(self):
        """400 errors raise GatewayError (not retryable)."""
        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=openai.BadRequestError(
                message="Bad request",
                response=MagicMock(status_code=400),
                body=None,
            )
        )

        with pytest.raises(GatewayError, match="error 400"):
            await provider.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="gemini-2.5-flash",
                role=ModelRole.TARGET,
            )

    async def test_auth_error_raises_gateway_error(self):
        """Auth errors raise GatewayError."""
        provider = LiteLLMProvider(provider="gemini", api_key="bad-key")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=openai.AuthenticationError(
                message="Invalid key",
                response=MagicMock(status_code=401),
                body=None,
            )
        )

        with pytest.raises(GatewayError, match="error 401"):
            await provider.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="gemini-2.5-flash",
                role=ModelRole.TARGET,
            )


class TestCostTracking:
    """Test cost extraction."""

    async def test_known_model_cost(self):
        """Known models get cost from static pricing table."""
        mock_response = _mock_completion(
            model="gemini-2.5-flash",
            prompt_tokens=1000,
            completion_tokens=500,
        )

        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gemini-2.5-flash",
            role=ModelRole.TARGET,
        )

        assert response.cost_usd > 0

    async def test_unknown_model_zero_cost(self):
        """Unknown models default to $0.00 cost."""
        mock_response = _mock_completion(model="unknown-model-xyz")

        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="unknown-model-xyz",
            role=ModelRole.TARGET,
        )

        assert response.cost_usd == 0.0


class TestContextManager:
    """Test async context manager lifecycle."""

    async def test_context_manager(self):
        """LiteLLMProvider works as async context manager."""
        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        async with provider as p:
            assert p is provider
