"""Cost tracking and estimation for LLM API calls.

Provides a static pricing table for common OpenRouter and Gemini direct API models,
token-based cost estimation, and an in-memory cost aggregator.
"""

import logging
from collections import defaultdict

from api.types import LLMResponse, ModelRole

logger = logging.getLogger(__name__)

# Static pricing table for common OpenRouter and Gemini direct API models.
# Prices in USD per million tokens.
# Source: OpenRouter pricing pages, Google AI Studio (approximate, updated periodically).
MODEL_PRICING: dict[str, dict[str, float]] = {
    "anthropic/claude-sonnet-4": {
        "input_per_million": 3.0,
        "output_per_million": 15.0,
    },
    "anthropic/claude-haiku-3.5": {
        "input_per_million": 0.80,
        "output_per_million": 4.0,
    },
    "anthropic/claude-opus-4": {
        "input_per_million": 15.0,
        "output_per_million": 75.0,
    },
    "openai/gpt-4o": {
        "input_per_million": 2.50,
        "output_per_million": 10.0,
    },
    "openai/gpt-4o-mini": {
        "input_per_million": 0.15,
        "output_per_million": 0.60,
    },
    "openai/gpt-4.1": {
        "input_per_million": 2.0,
        "output_per_million": 8.0,
    },
    "openai/gpt-4.1-mini": {
        "input_per_million": 0.40,
        "output_per_million": 1.60,
    },
    "google/gemini-2.0-flash-001": {
        "input_per_million": 0.10,
        "output_per_million": 0.40,
    },
    "google/gemini-2.5-pro-preview": {
        "input_per_million": 1.25,
        "output_per_million": 10.0,
    },
    "meta-llama/llama-3.3-70b-instruct": {
        "input_per_million": 0.30,
        "output_per_million": 0.30,
    },
    # Gemini direct API models (different name format from OpenRouter)
    "gemini-2.5-pro": {
        "input_per_million": 1.25,
        "output_per_million": 10.0,
    },
    "gemini-2.5-flash": {
        "input_per_million": 0.15,
        "output_per_million": 0.60,
    },
    "gemini-2.0-flash-lite": {
        "input_per_million": 0.0,
        "output_per_million": 0.0,
    },
    "gemini-3-flash-preview": {
        "input_per_million": 0.15,
        "output_per_million": 0.60,
    },
}


def estimate_cost_from_tokens(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimate cost from token counts using static pricing table.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o-mini").
        input_tokens: Number of input/prompt tokens.
        output_tokens: Number of output/completion tokens.

    Returns:
        Estimated cost in USD, or None if model is not in pricing table.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None

    cost = (input_tokens * pricing["input_per_million"] / 1_000_000) + (
        output_tokens * pricing["output_per_million"] / 1_000_000
    )
    return cost


class CostTracker:
    """In-memory aggregator for LLM call costs.

    Records individual LLMResponse objects and provides
    summary aggregation by total and by role.
    Persistence to DB happens separately when the evolution run completes.
    """

    def __init__(self):
        self._records: list[LLMResponse] = []

    def record(self, response: LLMResponse) -> None:
        """Record a single LLM call response."""
        self._records.append(response)

    def summary(self) -> dict:
        """Aggregate totals across all recorded calls.

        Uses a snapshot copy of _records to avoid inconsistent reads when
        concurrent asyncio tasks append to _records during iteration.

        Returns:
            Dict with total_calls, total_input_tokens, total_output_tokens, total_cost_usd.
        """
        records = list(self._records)
        return {
            "total_calls": len(records),
            "total_input_tokens": sum(r.input_tokens for r in records),
            "total_output_tokens": sum(r.output_tokens for r in records),
            "total_cost_usd": sum(r.cost_usd for r in records),
        }

    def by_role(self) -> dict[ModelRole, dict]:
        """Break down costs by ModelRole (meta/target/judge).

        Uses a snapshot copy of _records to avoid inconsistent reads when
        concurrent asyncio tasks append to _records during iteration.

        Returns:
            Dict mapping ModelRole to summary dict (same structure as summary()).
        """
        records = list(self._records)
        grouped: dict[ModelRole, list[LLMResponse]] = defaultdict(list)
        for r in records:
            grouped[r.role].append(r)

        result = {}
        for role, records in grouped.items():
            result[role] = {
                "total_calls": len(records),
                "total_input_tokens": sum(r.input_tokens for r in records),
                "total_output_tokens": sum(r.output_tokens for r in records),
                "total_cost_usd": sum(r.cost_usd for r in records),
            }
        return result

    def reset(self) -> None:
        """Clear all recorded data."""
        self._records.clear()
