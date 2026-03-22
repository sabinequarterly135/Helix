"""Tests for provider factory function.

Tests cover:
- create_provider returns LiteLLMProvider for all supported providers
- create_provider raises ConfigError on unknown provider
- create_provider raises ConfigError when API key is missing
"""

from unittest.mock import MagicMock

import pytest

from api.exceptions import ConfigError
from api.gateway.factory import create_provider
from api.gateway.litellm_provider import LiteLLMProvider


class TestCreateProvider:
    """Tests for the create_provider factory function."""

    def test_create_provider_openrouter(self):
        """create_provider('openrouter', config) returns LiteLLMProvider."""
        config = MagicMock()
        config.openrouter_api_key = "test-or-key"
        config.concurrency_limit = 10

        provider = create_provider("openrouter", config)

        assert isinstance(provider, LiteLLMProvider)
        assert provider._provider == "openrouter"

    def test_create_provider_gemini(self):
        """create_provider('gemini', config) returns LiteLLMProvider."""
        config = MagicMock()
        config.gemini_api_key = "test-gemini-key"
        config.concurrency_limit = 10

        provider = create_provider("gemini", config)

        assert isinstance(provider, LiteLLMProvider)
        assert provider._provider == "gemini"

    def test_create_provider_openai(self):
        """create_provider('openai', config) returns LiteLLMProvider."""
        config = MagicMock()
        config.openai_api_key = "test-openai-key"
        config.concurrency_limit = 10

        provider = create_provider("openai", config)

        assert isinstance(provider, LiteLLMProvider)
        assert provider._provider == "openai"

    def test_create_provider_unknown_raises(self):
        """create_provider('unknown', config) raises ConfigError."""
        config = MagicMock()

        with pytest.raises(ConfigError, match="Unknown provider.*unknown"):
            create_provider("unknown", config)

    def test_create_provider_missing_gemini_key_raises(self):
        """create_provider('gemini', config_without_gemini_key) raises ConfigError."""
        config = MagicMock()
        config.gemini_api_key = None

        with pytest.raises(ConfigError, match="gemini_api_key"):
            create_provider("gemini", config)

    def test_create_provider_missing_openrouter_key_raises(self):
        """create_provider('openrouter', config_without_openrouter_key) raises ConfigError."""
        config = MagicMock()
        config.openrouter_api_key = None

        with pytest.raises(ConfigError, match="openrouter_api_key"):
            create_provider("openrouter", config)

    def test_create_provider_missing_openai_key_raises(self):
        """create_provider('openai', config_without_key) raises ConfigError."""
        config = MagicMock()
        config.openai_api_key = None

        with pytest.raises(ConfigError, match="openai_api_key"):
            create_provider("openai", config)

    def test_create_provider_respects_concurrency_override(self):
        """create_provider with explicit concurrency_limit uses the override."""
        config = MagicMock()
        config.openrouter_api_key = "test-key"
        config.concurrency_limit = 10

        provider = create_provider("openrouter", config, concurrency_limit=5)

        assert isinstance(provider, LiteLLMProvider)


