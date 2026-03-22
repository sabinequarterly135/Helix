"""Unified LLM provider using the OpenAI SDK for multi-provider support.

Uses openai.AsyncOpenAI with different base_url per provider to support
Gemini, OpenRouter, OpenAI, and any OpenAI-compatible endpoint.
Handles auth, retries, concurrency, and cost tracking.
"""

import asyncio
import logging
from datetime import UTC, datetime

import openai
from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from api.exceptions import GatewayError, RetryableError
from api.gateway.cost import estimate_cost_from_tokens
from api.gateway.registry import get_provider_config
from api.types import LLMResponse, ModelRole

logger = logging.getLogger(__name__)


class LiteLLMProvider:
    """Unified async LLM provider using the OpenAI SDK.

    All supported providers expose OpenAI-compatible chat completions
    endpoints. This class uses a single AsyncOpenAI client configured
    with the provider's base_url and API key.

    Features:
    - Single implementation for all providers (Gemini, OpenRouter, OpenAI, etc.)
    - Automatic retry with exponential backoff on 429 and 5xx
    - Concurrency limiting via asyncio.Semaphore
    - Cost extraction: X-OR-Cost header (OpenRouter) or static pricing fallback
    - Async context manager for clean lifecycle

    Usage:
        async with LiteLLMProvider(provider="gemini", api_key="...") as p:
            response = await p.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="gemini-2.5-flash",
                role=ModelRole.TARGET,
            )
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        concurrency_limit: int = 10,
        timeout: float = 120.0,
    ):
        self._provider = provider
        self._semaphore = asyncio.Semaphore(concurrency_limit)

        cfg = get_provider_config(provider)

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=cfg.base_url,
            timeout=timeout,
            default_headers=cfg.default_headers,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry=retry_if_exception_type(RetryableError),
        reraise=True,
    )
    async def chat_completion(
        self,
        messages: list[dict],
        model: str,
        role: ModelRole,
        **kwargs,
    ) -> LLMResponse:
        """Send a chat completion request via the OpenAI SDK.

        Args:
            messages: List of message dicts (role, content).
            model: Model identifier (e.g., "gemini-2.5-flash", "gpt-4o").
            role: The role this model plays (meta/target/judge).
            **kwargs: Additional parameters passed to chat.completions.create().
                      Supports: temperature, max_tokens, top_p, tools,
                      response_format, extra_body, etc.

        Returns:
            LLMResponse with content, usage, and cost data.

        Raises:
            RetryableError: On 429 or 5xx (triggers retry).
            GatewayError: On non-retryable errors (400, 401, etc.).
        """
        async with self._semaphore:
            try:
                response = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    **kwargs,
                )
            except openai.RateLimitError as exc:
                raise RetryableError(429, str(exc)) from exc
            except openai.InternalServerError as exc:
                raise RetryableError(getattr(exc, "status_code", 500), str(exc)) from exc
            except openai.APIConnectionError as exc:
                raise RetryableError(0, str(exc)) from exc
            except openai.APIStatusError as exc:
                raise GatewayError(
                    f"{self._provider}/{model} error {exc.status_code}: {exc.message}"
                ) from exc
            except openai.APIError as exc:
                raise GatewayError(f"{self._provider}/{model} error: {exc}") from exc

        # Extract usage
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        # Extract cost: X-OR-Cost header (OpenRouter) or static pricing
        cost = self._extract_cost(model, input_tokens, output_tokens)

        choice = response.choices[0]
        message = choice.message

        # Extract tool_calls as dicts
        tool_calls = None
        if message.tool_calls:
            tool_calls = [tc.model_dump() for tc in message.tool_calls]

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            model_used=response.model or model,
            role=role,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            generation_id=response.id,
            timestamp=datetime.now(UTC),
            finish_reason=choice.finish_reason,
        )

    def _extract_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Extract or estimate cost for a completion.

        Uses static pricing table for all providers.
        """
        estimated = estimate_cost_from_tokens(model, input_tokens, output_tokens)
        if estimated is not None:
            return estimated

        logger.warning(
            "No pricing for model '%s' (provider: %s). Cost recorded as $0.00.",
            model,
            self._provider,
        )
        return 0.0
