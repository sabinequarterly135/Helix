"""Feature parity tests for retry and cost tracking across all providers.

Verifies that retry behavior (COMPAT-01) and cost tracking (COMPAT-02)
work identically for gemini, openrouter, and openai providers through
the unified LiteLLMProvider client.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from api.exceptions import GatewayError, RetryableError
from api.gateway.cost import CostTracker, estimate_cost_from_tokens
from api.gateway.litellm_provider import LiteLLMProvider
from api.types import LLMResponse, ModelRole


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


def _make_rate_limit_error():
    """Create an openai.RateLimitError for testing."""
    return openai.RateLimitError(
        message="Rate limited",
        response=MagicMock(status_code=429),
        body=None,
    )


def _make_internal_server_error(status_code=500):
    """Create an openai.InternalServerError for testing."""
    mock_response = MagicMock(status_code=status_code)
    return openai.InternalServerError(
        message="Server error",
        response=mock_response,
        body=None,
    )


def _make_connection_error():
    """Create an openai.APIConnectionError for testing."""
    return openai.APIConnectionError(request=MagicMock())


def _make_bad_request_error():
    """Create an openai.BadRequestError for testing."""
    return openai.BadRequestError(
        message="Bad request",
        response=MagicMock(status_code=400),
        body=None,
    )


ALL_PROVIDERS = ["gemini", "openrouter", "openai"]


@patch("tenacity.nap.time.sleep", return_value=None)
class TestRetryParity:
    """Verify retry behavior is identical across all three providers.

    Each test parametrizes across gemini, openrouter, and openai to prove
    that the unified LiteLLMProvider retries (or does not retry) identically
    regardless of provider.
    """

    @pytest.mark.parametrize("provider_name", ALL_PROVIDERS)
    async def test_retry_on_429_then_succeed(self, mock_sleep, provider_name):
        """First call raises RateLimitError (429), second succeeds."""
        provider = LiteLLMProvider(provider=provider_name, api_key="test")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=[_make_rate_limit_error(), _mock_completion()]
        )

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gemini-2.5-flash",
            role=ModelRole.TARGET,
        )

        assert response.content == "Hello!"
        assert provider._client.chat.completions.create.call_count == 2

    @pytest.mark.parametrize("provider_name", ALL_PROVIDERS)
    async def test_retry_on_500_then_succeed(self, mock_sleep, provider_name):
        """First call raises InternalServerError (500), second succeeds."""
        provider = LiteLLMProvider(provider=provider_name, api_key="test")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=[_make_internal_server_error(500), _mock_completion()]
        )

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gemini-2.5-flash",
            role=ModelRole.TARGET,
        )

        assert response.content == "Hello!"
        assert provider._client.chat.completions.create.call_count == 2

    @pytest.mark.parametrize("provider_name", ALL_PROVIDERS)
    async def test_retry_on_503_then_succeed(self, mock_sleep, provider_name):
        """First call raises InternalServerError (503), second succeeds."""
        provider = LiteLLMProvider(provider=provider_name, api_key="test")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=[_make_internal_server_error(503), _mock_completion()]
        )

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gemini-2.5-flash",
            role=ModelRole.TARGET,
        )

        assert response.content == "Hello!"
        assert provider._client.chat.completions.create.call_count == 2

    @pytest.mark.parametrize("provider_name", ALL_PROVIDERS)
    async def test_exhausted_retries_propagates_error(self, mock_sleep, provider_name):
        """All 4 attempts raise RateLimitError -> RetryableError propagated."""
        provider = LiteLLMProvider(provider=provider_name, api_key="test")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=[
                _make_rate_limit_error(),
                _make_rate_limit_error(),
                _make_rate_limit_error(),
                _make_rate_limit_error(),
            ]
        )

        with pytest.raises(RetryableError):
            await provider.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="gemini-2.5-flash",
                role=ModelRole.TARGET,
            )

        assert provider._client.chat.completions.create.call_count == 4

    @pytest.mark.parametrize("provider_name", ALL_PROVIDERS)
    async def test_retry_on_connection_error_then_succeed(self, mock_sleep, provider_name):
        """APIConnectionError triggers retry, second call succeeds."""
        provider = LiteLLMProvider(provider=provider_name, api_key="test")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=[_make_connection_error(), _mock_completion()]
        )

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gemini-2.5-flash",
            role=ModelRole.TARGET,
        )

        assert response.content == "Hello!"
        assert provider._client.chat.completions.create.call_count == 2

    @pytest.mark.parametrize("provider_name", ALL_PROVIDERS)
    async def test_no_retry_on_400_bad_request(self, mock_sleep, provider_name):
        """BadRequestError (400) raises GatewayError immediately, no retry."""
        provider = LiteLLMProvider(provider=provider_name, api_key="test")
        provider._client.chat.completions.create = AsyncMock(side_effect=_make_bad_request_error())

        with pytest.raises(GatewayError):
            await provider.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="gemini-2.5-flash",
                role=ModelRole.TARGET,
            )

        # Only 1 call — no retry for non-retryable errors
        assert provider._client.chat.completions.create.call_count == 1


# Model names used for cost lookups, per provider
PROVIDER_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openrouter": "openai/gpt-4o-mini",
    "openai": "openai/gpt-4o-mini",
}


class TestCostParity:
    """Verify cost tracking works identically across all three providers.

    Tests token extraction from LLMResponse, known/unknown model pricing,
    CostTracker aggregation, and estimate_cost_from_tokens coverage.
    """

    @pytest.mark.parametrize("provider_name", ALL_PROVIDERS)
    async def test_token_counts_extracted_correctly(self, provider_name):
        """chat_completion returns correct input_tokens and output_tokens."""
        model = PROVIDER_MODELS[provider_name]
        mock_resp = _mock_completion(model=model, prompt_tokens=1000, completion_tokens=500)

        provider = LiteLLMProvider(provider=provider_name, api_key="test")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model=model,
            role=ModelRole.TARGET,
        )

        assert response.input_tokens == 1000
        assert response.output_tokens == 500

    @pytest.mark.parametrize("provider_name", ALL_PROVIDERS)
    async def test_known_model_has_nonzero_cost(self, provider_name):
        """Known model returns cost_usd > 0 for all providers."""
        model = PROVIDER_MODELS[provider_name]
        mock_resp = _mock_completion(model=model, prompt_tokens=1000, completion_tokens=500)

        provider = LiteLLMProvider(provider=provider_name, api_key="test")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model=model,
            role=ModelRole.TARGET,
        )

        assert response.cost_usd > 0, (
            f"Expected non-zero cost for known model {model} on {provider_name}"
        )

    @pytest.mark.parametrize("provider_name", ALL_PROVIDERS)
    async def test_unknown_model_returns_zero_cost(self, provider_name):
        """Unknown model returns cost_usd == 0.0 gracefully, no crash."""
        unknown_model = "totally-unknown-model-xyz"
        mock_resp = _mock_completion(model=unknown_model, prompt_tokens=100, completion_tokens=50)

        provider = LiteLLMProvider(provider=provider_name, api_key="test")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model=unknown_model,
            role=ModelRole.TARGET,
        )

        assert response.cost_usd == 0.0

    async def test_cost_tracker_aggregates_mixed_providers(self):
        """CostTracker.record() + summary() works with responses from mixed providers."""
        from datetime import datetime, timezone

        tracker = CostTracker()

        # Simulate responses from each provider
        responses = [
            LLMResponse(
                content="gemini response",
                model_used="gemini-2.5-flash",
                role=ModelRole.META,
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.000045,
                timestamp=datetime.now(timezone.utc),
            ),
            LLMResponse(
                content="openrouter response",
                model_used="openai/gpt-4o-mini",
                role=ModelRole.TARGET,
                input_tokens=200,
                output_tokens=100,
                cost_usd=0.000090,
                timestamp=datetime.now(timezone.utc),
            ),
            LLMResponse(
                content="openai response",
                model_used="openai/gpt-4o",
                role=ModelRole.JUDGE,
                input_tokens=300,
                output_tokens=150,
                cost_usd=0.002250,
                timestamp=datetime.now(timezone.utc),
            ),
        ]

        for r in responses:
            tracker.record(r)

        summary = tracker.summary()
        assert summary["total_calls"] == 3
        assert summary["total_input_tokens"] == 600
        assert summary["total_output_tokens"] == 300
        assert summary["total_cost_usd"] == pytest.approx(0.000045 + 0.000090 + 0.002250)

    async def test_cost_tracker_by_role_separates_providers(self):
        """CostTracker.by_role() correctly separates costs from different providers/roles."""
        from datetime import datetime, timezone

        tracker = CostTracker()

        tracker.record(
            LLMResponse(
                content="meta",
                model_used="gemini-2.5-flash",
                role=ModelRole.META,
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
                timestamp=datetime.now(timezone.utc),
            )
        )
        tracker.record(
            LLMResponse(
                content="target",
                model_used="openai/gpt-4o-mini",
                role=ModelRole.TARGET,
                input_tokens=200,
                output_tokens=100,
                cost_usd=0.02,
                timestamp=datetime.now(timezone.utc),
            )
        )
        tracker.record(
            LLMResponse(
                content="judge",
                model_used="openai/gpt-4o",
                role=ModelRole.JUDGE,
                input_tokens=300,
                output_tokens=150,
                cost_usd=0.03,
                timestamp=datetime.now(timezone.utc),
            )
        )

        by_role = tracker.by_role()

        assert ModelRole.META in by_role
        assert ModelRole.TARGET in by_role
        assert ModelRole.JUDGE in by_role

        assert by_role[ModelRole.META]["total_calls"] == 1
        assert by_role[ModelRole.META]["total_cost_usd"] == pytest.approx(0.01)
        assert by_role[ModelRole.TARGET]["total_calls"] == 1
        assert by_role[ModelRole.TARGET]["total_cost_usd"] == pytest.approx(0.02)
        assert by_role[ModelRole.JUDGE]["total_calls"] == 1
        assert by_role[ModelRole.JUDGE]["total_cost_usd"] == pytest.approx(0.03)

    def test_estimate_cost_covers_all_provider_namespaces(self):
        """estimate_cost_from_tokens covers at least one model per provider namespace."""
        # Gemini direct API model (gemini-*)
        gemini_cost = estimate_cost_from_tokens("gemini-2.5-flash", 1000, 500)
        assert gemini_cost is not None and gemini_cost > 0, "Missing gemini-* pricing"

        # OpenAI namespace (openai/*)
        openai_cost = estimate_cost_from_tokens("openai/gpt-4o-mini", 1000, 500)
        assert openai_cost is not None and openai_cost > 0, "Missing openai/* pricing"

        # Anthropic namespace (anthropic/*)
        anthropic_cost = estimate_cost_from_tokens("anthropic/claude-sonnet-4", 1000, 500)
        assert anthropic_cost is not None and anthropic_cost > 0, "Missing anthropic/* pricing"
