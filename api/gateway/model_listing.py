"""Fetch and cache available model lists from OpenRouter and Gemini APIs.

Provides standalone async functions that proxy upstream provider model
endpoints, normalize responses to a shared ModelInfo schema, and cache
results with a 5-minute TTL.  These functions are NOT methods on the
existing provider classes because model listing uses different base URLs
and authentication mechanisms than inference.

Usage:
    models = await fetch_openrouter_models(api_key)
    models = await fetch_gemini_models(api_key)
    # or with caching:
    models = await _get_cached_or_fetch("openrouter", lambda: fetch_openrouter_models(key))
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pydantic import BaseModel


class ModelInfo(BaseModel):
    """Normalized model metadata returned by the /api/models endpoint.

    Fields:
        id: Value passed to model= in API calls (e.g. "gemini-2.5-pro").
        name: Human-readable display name (e.g. "Gemini 2.5 Pro").
        context_length: Maximum input token limit, if known.
        input_price_per_mtok: USD per 1M input tokens (OpenRouter only).
        output_price_per_mtok: USD per 1M output tokens (OpenRouter only).
        provider: Source provider ("openrouter" or "gemini").
    """

    id: str
    name: str
    context_length: int | None = None
    input_price_per_mtok: float | None = None
    output_price_per_mtok: float | None = None
    provider: str


# ---------------------------------------------------------------------------
# Module-level cache: { key: (monotonic_timestamp, list[ModelInfo]) }
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, list[ModelInfo]]] = {}
CACHE_TTL_SECONDS: int = 300  # 5 minutes


async def _get_cached_or_fetch(
    key: str,
    fetcher: Callable[[], Awaitable[list[ModelInfo]]],
) -> list[ModelInfo]:
    """Return cached models if fresh, otherwise fetch and cache.

    Only successful fetches are cached.  If the fetcher raises, the
    exception propagates and the cache is NOT populated, so the next
    call will retry.
    """
    now = time.monotonic()
    if key in _cache:
        cached_at, data = _cache[key]
        if now - cached_at < CACHE_TTL_SECONDS:
            return data

    # Fetch -- let exceptions propagate (do NOT cache errors)
    data = await fetcher()
    _cache[key] = (time.monotonic(), data)
    return data


def clear_model_cache() -> None:
    """Clear the model cache.  Used between tests."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Provider fetchers
# ---------------------------------------------------------------------------


async def fetch_openrouter_models(api_key: str) -> list[ModelInfo]:
    """Fetch available models from the OpenRouter API.

    Returns normalized ModelInfo list with pricing converted from
    per-token USD strings to per-million-token floats.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/gene-prompter",
                "X-Title": "Helix",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        raw = resp.json()

    models: list[ModelInfo] = []
    for m in raw.get("data", []):
        pricing: dict[str, Any] = m.get("pricing") or {}
        prompt_price = pricing.get("prompt")
        completion_price = pricing.get("completion")

        models.append(
            ModelInfo(
                id=m["id"],
                name=m.get("name", m["id"]),
                context_length=m.get("context_length"),
                input_price_per_mtok=(float(prompt_price) * 1_000_000 if prompt_price else None),
                output_price_per_mtok=(
                    float(completion_price) * 1_000_000 if completion_price else None
                ),
                provider="openrouter",
            )
        )
    return models


async def fetch_openai_models(api_key: str) -> list[ModelInfo]:
    """Fetch available models from the OpenAI API.

    Returns normalized ModelInfo list for models that support
    chat completions.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        raw = resp.json()

    models: list[ModelInfo] = []
    for m in raw.get("data", []):
        model_id = m["id"]
        # Filter to chat-capable models (skip embeddings, tts, etc.)
        if any(
            skip in model_id for skip in ["embedding", "tts", "whisper", "dall-e", "moderation"]
        ):
            continue
        models.append(
            ModelInfo(
                id=model_id,
                name=model_id,
                context_length=None,
                provider="openai",
            )
        )
    return sorted(models, key=lambda m: m.id)


async def fetch_gemini_models(api_key: str) -> list[ModelInfo]:
    """Fetch available Gemini models from the native REST API.

    Uses the ``v1beta/models`` endpoint (NOT the OpenAI-compatible
    endpoint) because only the native endpoint returns ``inputTokenLimit``
    and ``displayName``.

    Only models whose ``supportedGenerationMethods`` include
    ``"generateContent"`` are returned.  The ``"models/"`` prefix is
    stripped from the name to produce the model ID used in API calls.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key, "pageSize": 1000},
            timeout=30.0,
        )
        resp.raise_for_status()
        raw = resp.json()

    models: list[ModelInfo] = []
    for m in raw.get("models", []):
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        model_id = m["name"].replace("models/", "")
        models.append(
            ModelInfo(
                id=model_id,
                name=m.get("displayName", model_id),
                context_length=m.get("inputTokenLimit"),
                provider="gemini",
            )
        )
    return models
