"""Declarative provider registry for OpenAI-compatible LLM endpoints.

Centralizes all provider configuration (base URLs, API key field names,
default headers) in a single data structure.  Adding a new provider
requires only a new entry in PROVIDER_REGISTRY.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    """Immutable configuration for an OpenAI-compatible LLM provider.

    Attributes:
        base_url: The provider's OpenAI-compatible API endpoint.
        api_key_field: The GeneConfig attribute name for the API key
                       (e.g., ``"gemini_api_key"``).
        default_headers: Optional provider-specific HTTP headers sent
                         with every request (e.g., OpenRouter's
                         ``HTTP-Referer``).
    """

    base_url: str
    api_key_field: str
    default_headers: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Registry: one entry per supported provider
# ---------------------------------------------------------------------------

PROVIDER_REGISTRY: dict[str, ProviderConfig] = {
    "gemini": ProviderConfig(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_field="gemini_api_key",
    ),
    "openrouter": ProviderConfig(
        base_url="https://openrouter.ai/api/v1",
        api_key_field="openrouter_api_key",
        default_headers={
            "HTTP-Referer": "https://github.com/gene-prompter",
            "X-Title": "Helix",
        },
    ),
    "openai": ProviderConfig(
        base_url="https://api.openai.com/v1",
        api_key_field="openai_api_key",
    ),
}

#: Alphabetically sorted list of supported provider names.
SUPPORTED_PROVIDERS: list[str] = sorted(PROVIDER_REGISTRY.keys())


def get_provider_config(provider: str) -> ProviderConfig:
    """Look up the :class:`ProviderConfig` for *provider*.

    Args:
        provider: Provider identifier (e.g., ``"gemini"``).

    Returns:
        The matching :class:`ProviderConfig`.

    Raises:
        ValueError: If *provider* is not in the registry.
    """
    try:
        return PROVIDER_REGISTRY[provider]
    except KeyError:
        raise ValueError(
            f"Unknown provider '{provider}'. Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        ) from None
