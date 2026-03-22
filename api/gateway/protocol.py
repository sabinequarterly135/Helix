"""LLMProvider Protocol for multi-provider abstraction.

Defines the runtime_checkable Protocol that LiteLLMProvider satisfies,
enabling interchangeable use across all supported providers (Gemini,
OpenRouter, OpenAI) via a single unified client.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from api.types import LLMResponse, ModelRole


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM API providers.

    Any class implementing chat_completion, close, __aenter__, and __aexit__
    with compatible signatures satisfies this Protocol at runtime.

    Usage:
        from api.gateway import create_provider

        provider = create_provider("gemini", api_key="...")
        # provider satisfies LLMProvider and works for any registered provider
    """

    async def chat_completion(
        self,
        messages: list[dict],
        model: str,
        role: ModelRole,
        **kwargs,
    ) -> LLMResponse: ...

    async def close(self) -> None: ...

    async def __aenter__(self): ...

    async def __aexit__(self, exc_type, exc_val, exc_tb): ...
