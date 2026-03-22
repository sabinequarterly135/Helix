"""Tests for gateway model listing functions (OpenRouter + Gemini) and cache behavior.

Tests cover:
- OpenRouter model fetching with pricing normalization
- Gemini model fetching with generateContent filtering
- TTL cache behavior (hit, miss, error bypass)
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from api.gateway.model_listing import (
    ModelInfo,
    _get_cached_or_fetch,
    clear_model_cache,
    fetch_gemini_models,
    fetch_openrouter_models,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear model cache before each test to avoid cross-test pollution."""
    clear_model_cache()
    yield
    clear_model_cache()


class TestFetchOpenRouterModels:
    """Tests for fetch_openrouter_models()."""

    async def test_fetch_openrouter_models_returns_normalized(self, httpx_mock):
        """OpenRouter models are normalized with per-million-token pricing."""
        httpx_mock.add_response(
            url="https://openrouter.ai/api/v1/models",
            json={
                "data": [
                    {
                        "id": "openai/gpt-4o-mini",
                        "name": "OpenAI: GPT-4o Mini",
                        "context_length": 128000,
                        "pricing": {
                            "prompt": "0.00000015",
                            "completion": "0.0000006",
                        },
                    },
                    {
                        "id": "anthropic/claude-sonnet-4",
                        "name": "Anthropic: Claude Sonnet 4",
                        "context_length": 200000,
                        "pricing": {
                            "prompt": "0.000003",
                            "completion": "0.000015",
                        },
                    },
                ]
            },
        )

        models = await fetch_openrouter_models("test-key")

        assert len(models) == 2
        assert models[0].id == "openai/gpt-4o-mini"
        assert models[0].name == "OpenAI: GPT-4o Mini"
        assert models[0].context_length == 128000
        assert models[0].input_price_per_mtok == pytest.approx(0.15)
        assert models[0].output_price_per_mtok == pytest.approx(0.6)
        assert models[0].provider == "openrouter"

        assert models[1].id == "anthropic/claude-sonnet-4"
        assert models[1].input_price_per_mtok == pytest.approx(3.0)
        assert models[1].output_price_per_mtok == pytest.approx(15.0)

    async def test_fetch_openrouter_models_handles_null_pricing(self, httpx_mock):
        """Models with null pricing fields get None in ModelInfo."""
        httpx_mock.add_response(
            url="https://openrouter.ai/api/v1/models",
            json={
                "data": [
                    {
                        "id": "free/model",
                        "name": "Free Model",
                        "context_length": 4096,
                        "pricing": {
                            "prompt": None,
                            "completion": None,
                        },
                    },
                ]
            },
        )

        models = await fetch_openrouter_models("test-key")

        assert len(models) == 1
        assert models[0].input_price_per_mtok is None
        assert models[0].output_price_per_mtok is None


class TestFetchGeminiModels:
    """Tests for fetch_gemini_models()."""

    async def test_fetch_gemini_models_returns_normalized(self, httpx_mock):
        """Gemini models are normalized, filtered by generateContent, and ID prefix stripped."""
        httpx_mock.add_response(
            url=httpx.URL(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": "test-gemini-key", "pageSize": "1000"},
            ),
            json={
                "models": [
                    {
                        "name": "models/gemini-2.5-pro",
                        "displayName": "Gemini 2.5 Pro",
                        "inputTokenLimit": 1048576,
                        "outputTokenLimit": 65536,
                        "supportedGenerationMethods": [
                            "generateContent",
                            "countTokens",
                        ],
                    },
                    {
                        "name": "models/gemini-2.5-flash",
                        "displayName": "Gemini 2.5 Flash",
                        "inputTokenLimit": 1048576,
                        "outputTokenLimit": 65536,
                        "supportedGenerationMethods": [
                            "generateContent",
                            "countTokens",
                        ],
                    },
                    {
                        "name": "models/text-embedding-004",
                        "displayName": "Text Embedding 004",
                        "inputTokenLimit": 2048,
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
        )

        models = await fetch_gemini_models("test-gemini-key")

        # Only 2 of 3 models support generateContent
        assert len(models) == 2
        assert models[0].id == "gemini-2.5-pro"  # "models/" prefix stripped
        assert models[0].name == "Gemini 2.5 Pro"
        assert models[0].context_length == 1048576
        assert models[0].provider == "gemini"
        assert models[0].input_price_per_mtok is None
        assert models[0].output_price_per_mtok is None

        assert models[1].id == "gemini-2.5-flash"

    async def test_fetch_gemini_models_uses_query_param_auth(self, httpx_mock):
        """Gemini listing uses key= query param, NOT Bearer header."""
        httpx_mock.add_response(
            json={"models": []},
        )

        await fetch_gemini_models("my-secret-key")

        request = httpx_mock.get_request()
        assert "key=my-secret-key" in str(request.url)
        assert "Authorization" not in request.headers


class TestCache:
    """Tests for _get_cached_or_fetch() cache behavior."""

    async def test_cache_hit_within_ttl(self):
        """Second call within TTL returns cached data without invoking fetcher."""
        call_count = 0

        async def fetcher():
            nonlocal call_count
            call_count += 1
            return [ModelInfo(id="m1", name="Model 1", provider="test")]

        result1 = await _get_cached_or_fetch("test-key", fetcher)
        result2 = await _get_cached_or_fetch("test-key", fetcher)

        assert call_count == 1
        assert result1 == result2

    async def test_cache_miss_after_ttl(self):
        """After TTL expires, fetcher is called again."""
        call_count = 0

        async def fetcher():
            nonlocal call_count
            call_count += 1
            return [ModelInfo(id="m1", name="Model 1", provider="test")]

        with patch("api.gateway.model_listing.time") as mock_time:
            mock_time.monotonic.side_effect = [
                0.0,  # First call: check cache (miss)
                0.0,  # First call: store timestamp
                400.0,  # Second call: check cache (expired -- 400 > 300 TTL)
                400.0,  # Second call: store timestamp
            ]

            await _get_cached_or_fetch("test-key2", fetcher)
            await _get_cached_or_fetch("test-key2", fetcher)

        assert call_count == 2

    async def test_failed_fetch_not_cached(self):
        """Failed fetches are not cached -- next call retries."""
        call_count = 0

        async def fetcher():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate HTTP error on first call
                response = httpx.Response(
                    status_code=500, request=httpx.Request("GET", "http://test")
                )
                raise httpx.HTTPStatusError(
                    "Server error", request=response.request, response=response
                )
            return [ModelInfo(id="m1", name="Model 1", provider="test")]

        # First call should raise
        with pytest.raises(httpx.HTTPStatusError):
            await _get_cached_or_fetch("test-key3", fetcher)

        # Second call should succeed (not serving cached error)
        result = await _get_cached_or_fetch("test-key3", fetcher)

        assert call_count == 2
        assert len(result) == 1
