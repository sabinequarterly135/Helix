"""Tests for LLMProvider Protocol.

Verifies that LiteLLMProvider satisfies the LLMProvider Protocol
via runtime_checkable isinstance checks.
"""


class TestProtocolDefinition:
    """Verify LLMProvider Protocol defines expected methods."""

    def test_protocol_has_required_methods(self):
        """LLMProvider defines chat_completion, close, __aenter__, __aexit__."""
        from api.gateway.protocol import LLMProvider

        # Protocol should define these methods
        assert hasattr(LLMProvider, "chat_completion")
        assert hasattr(LLMProvider, "close")
        assert hasattr(LLMProvider, "__aenter__")
        assert hasattr(LLMProvider, "__aexit__")


class TestProtocolSatisfaction:
    """Verify LiteLLMProvider satisfies the LLMProvider Protocol."""

    def test_protocol_litellm_satisfies(self):
        """isinstance(LiteLLMProvider(...), LLMProvider) is True."""
        from api.gateway.litellm_provider import LiteLLMProvider
        from api.gateway.protocol import LLMProvider

        provider = LiteLLMProvider(provider="gemini", api_key="test-key")
        assert isinstance(provider, LLMProvider)
