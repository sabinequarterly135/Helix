"""Tests for the provider registry module.

Tests cover:
- PROVIDER_REGISTRY contains entries for all supported providers
- ProviderConfig dataclass has correct fields
- get_provider_config returns correct config for known providers
- get_provider_config raises ValueError for unknown providers
- ProviderConfig is sufficient for any OpenAI-compatible provider
- OpenRouter has default_headers; Gemini and OpenAI do not
"""

import pytest

from api.gateway.registry import (
    PROVIDER_REGISTRY,
    SUPPORTED_PROVIDERS,
    ProviderConfig,
    get_provider_config,
)


class TestProviderRegistry:
    """Test that PROVIDER_REGISTRY contains the expected providers."""

    def test_registry_contains_gemini(self):
        """PROVIDER_REGISTRY has an entry for 'gemini'."""
        assert "gemini" in PROVIDER_REGISTRY

    def test_registry_contains_openrouter(self):
        """PROVIDER_REGISTRY has an entry for 'openrouter'."""
        assert "openrouter" in PROVIDER_REGISTRY

    def test_registry_contains_openai(self):
        """PROVIDER_REGISTRY has an entry for 'openai'."""
        assert "openai" in PROVIDER_REGISTRY


class TestProviderConfig:
    """Test that each registry entry is a ProviderConfig with correct fields."""

    def test_gemini_is_provider_config(self):
        """Gemini entry is a ProviderConfig instance."""
        assert isinstance(PROVIDER_REGISTRY["gemini"], ProviderConfig)

    def test_openrouter_is_provider_config(self):
        """OpenRouter entry is a ProviderConfig instance."""
        assert isinstance(PROVIDER_REGISTRY["openrouter"], ProviderConfig)

    def test_openai_is_provider_config(self):
        """OpenAI entry is a ProviderConfig instance."""
        assert isinstance(PROVIDER_REGISTRY["openai"], ProviderConfig)

    def test_config_has_base_url(self):
        """ProviderConfig has a base_url field."""
        cfg = PROVIDER_REGISTRY["gemini"]
        assert hasattr(cfg, "base_url")
        assert isinstance(cfg.base_url, str)

    def test_config_has_api_key_field(self):
        """ProviderConfig has an api_key_field field."""
        cfg = PROVIDER_REGISTRY["gemini"]
        assert hasattr(cfg, "api_key_field")
        assert isinstance(cfg.api_key_field, str)

    def test_config_has_default_headers(self):
        """ProviderConfig has a default_headers field."""
        cfg = PROVIDER_REGISTRY["openrouter"]
        assert hasattr(cfg, "default_headers")


class TestGetProviderConfig:
    """Test the get_provider_config lookup function."""

    def test_get_gemini_config(self):
        """get_provider_config('gemini') returns the gemini ProviderConfig."""
        cfg = get_provider_config("gemini")
        assert cfg is PROVIDER_REGISTRY["gemini"]
        assert cfg.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
        assert cfg.api_key_field == "gemini_api_key"

    def test_get_openrouter_config(self):
        """get_provider_config('openrouter') returns the openrouter ProviderConfig."""
        cfg = get_provider_config("openrouter")
        assert cfg is PROVIDER_REGISTRY["openrouter"]
        assert cfg.base_url == "https://openrouter.ai/api/v1"
        assert cfg.api_key_field == "openrouter_api_key"

    def test_get_openai_config(self):
        """get_provider_config('openai') returns the openai ProviderConfig."""
        cfg = get_provider_config("openai")
        assert cfg is PROVIDER_REGISTRY["openai"]
        assert cfg.base_url == "https://api.openai.com/v1"
        assert cfg.api_key_field == "openai_api_key"

    def test_unknown_provider_raises_value_error(self):
        """get_provider_config('unknown') raises ValueError with helpful message."""
        with pytest.raises(ValueError, match="Unknown provider.*unknown"):
            get_provider_config("unknown")

    def test_unknown_provider_lists_supported(self):
        """ValueError message lists supported providers."""
        with pytest.raises(ValueError, match="gemini.*openai.*openrouter"):
            get_provider_config("unknown")


class TestNewProviderExtensibility:
    """Test that adding a new provider requires only a registry entry."""

    def test_hypothetical_together_provider(self):
        """Adding a new provider (e.g., 'together') requires only a PROVIDER_REGISTRY entry.

        ProviderConfig fields are sufficient to configure any OpenAI-compatible endpoint.
        """
        together_config = ProviderConfig(
            base_url="https://api.together.xyz/v1",
            api_key_field="together_api_key",
        )
        assert together_config.base_url == "https://api.together.xyz/v1"
        assert together_config.api_key_field == "together_api_key"
        assert together_config.default_headers is None

    def test_hypothetical_provider_with_headers(self):
        """A new provider can specify custom default_headers."""
        custom_config = ProviderConfig(
            base_url="https://api.custom.ai/v1",
            api_key_field="custom_api_key",
            default_headers={"X-Custom-Header": "value"},
        )
        assert custom_config.default_headers == {"X-Custom-Header": "value"}


class TestOpenRouterHeaders:
    """Test that openrouter has default_headers; gemini and openai do not."""

    def test_openrouter_has_default_headers(self):
        """OpenRouter config includes HTTP-Referer and X-Title headers."""
        cfg = PROVIDER_REGISTRY["openrouter"]
        assert cfg.default_headers is not None
        assert "HTTP-Referer" in cfg.default_headers
        assert "X-Title" in cfg.default_headers
        assert cfg.default_headers["HTTP-Referer"] == "https://github.com/gene-prompter"
        assert cfg.default_headers["X-Title"] == "Helix"

    def test_gemini_has_no_default_headers(self):
        """Gemini config has no default_headers."""
        cfg = PROVIDER_REGISTRY["gemini"]
        assert cfg.default_headers is None

    def test_openai_has_no_default_headers(self):
        """OpenAI config has no default_headers."""
        cfg = PROVIDER_REGISTRY["openai"]
        assert cfg.default_headers is None


class TestSupportedProviders:
    """Test the SUPPORTED_PROVIDERS list."""

    def test_supported_providers_is_sorted(self):
        """SUPPORTED_PROVIDERS is sorted alphabetically."""
        assert SUPPORTED_PROVIDERS == sorted(SUPPORTED_PROVIDERS)

    def test_supported_providers_matches_registry(self):
        """SUPPORTED_PROVIDERS matches the registry keys."""
        assert set(SUPPORTED_PROVIDERS) == set(PROVIDER_REGISTRY.keys())

    def test_supported_providers_contains_all_three(self):
        """SUPPORTED_PROVIDERS contains gemini, openai, openrouter."""
        assert "gemini" in SUPPORTED_PROVIDERS
        assert "openai" in SUPPORTED_PROVIDERS
        assert "openrouter" in SUPPORTED_PROVIDERS
