"""Tests for wizard template generation endpoint (POST /api/wizard/generate)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx

from api.web.routers.wizard import _format_user_prompt
from api.web.schemas import WizardGenerateRequest
from api.types import LLMResponse, ModelRole


# -- Helpers --

VALID_WIZARD_REQUEST = {
    "id": "test-prompt",
    "purpose": "Handle customer IVR calls",
    "description": "An IVR prompt for routing calls",
    "variables": [
        {"name": "customer_name", "var_type": "string", "description": "The caller's name"},
        {"name": "department", "var_type": "string", "is_anchor": True},
    ],
    "constraints": "Keep responses under 100 words",
    "behaviors": "Always greet the customer by name",
    "include_tools": False,
}

CANNED_LLM_YAML = """id: test-prompt
purpose: Handle customer IVR calls
template: |
  Hello {{ customer_name }}, how can I help you today?
  Routing to {{ department }}.
variables:
  - name: customer_name
    type: string
  - name: department
    type: string
    is_anchor: true
"""

CANNED_LLM_YAML_WITH_FENCES = f"```yaml\n{CANNED_LLM_YAML}```"


def _make_mock_provider(response_content: str) -> AsyncMock:
    """Create a mock LLM provider that returns a canned response."""
    mock_provider = AsyncMock()
    mock_provider.chat_completion.return_value = LLMResponse(
        content=response_content,
        tool_calls=None,
        model_used="gemini-2.5-pro",
        role=ModelRole.META,
        input_tokens=100,
        output_tokens=200,
        cost_usd=0.001,
        timestamp=datetime.now(timezone.utc),
    )
    # Support async context manager
    mock_provider.__aenter__.return_value = mock_provider
    mock_provider.__aexit__.return_value = None
    return mock_provider


# -- Test 1: Valid request returns 200 with yaml_template --


@patch("api.web.routers.wizard.create_provider")
async def test_generate_valid_request_returns_yaml(
    mock_create_provider: AsyncMock, client: httpx.AsyncClient
):
    """POST /api/wizard/generate with valid input returns 200 and a yaml_template string."""
    mock_provider = _make_mock_provider(CANNED_LLM_YAML)
    mock_create_provider.return_value = mock_provider

    resp = await client.post("/api/wizard/generate", json=VALID_WIZARD_REQUEST)

    assert resp.status_code == 200
    data = resp.json()
    assert "yaml_template" in data
    assert len(data["yaml_template"]) > 0
    assert "test-prompt" in data["yaml_template"]


# -- Test 2: Response strips markdown code fences --


@patch("api.web.routers.wizard.create_provider")
async def test_generate_strips_markdown_fences(
    mock_create_provider: AsyncMock, client: httpx.AsyncClient
):
    """Response yaml_template does not contain markdown code fences (``` stripped)."""
    mock_provider = _make_mock_provider(CANNED_LLM_YAML_WITH_FENCES)
    mock_create_provider.return_value = mock_provider

    resp = await client.post("/api/wizard/generate", json=VALID_WIZARD_REQUEST)

    assert resp.status_code == 200
    data = resp.json()
    assert "```" not in data["yaml_template"]
    assert data["yaml_template"].strip().startswith("id:")


# -- Test 3: Missing required field returns 422 --


async def test_generate_missing_purpose_returns_422(client: httpx.AsyncClient):
    """POST /api/wizard/generate with missing required field (purpose) returns 422."""
    incomplete_request = {
        "id": "test-prompt",
        # purpose is missing
        "variables": [],
    }
    resp = await client.post("/api/wizard/generate", json=incomplete_request)
    assert resp.status_code == 422


# -- Test 4: Endpoint uses ModelRole.META for LLM call --


@patch("api.web.routers.wizard.create_provider")
async def test_generate_uses_meta_role(mock_create_provider: AsyncMock, client: httpx.AsyncClient):
    """Wizard endpoint uses ModelRole.META for the LLM call."""
    mock_provider = _make_mock_provider(CANNED_LLM_YAML)
    mock_create_provider.return_value = mock_provider

    resp = await client.post("/api/wizard/generate", json=VALID_WIZARD_REQUEST)
    assert resp.status_code == 200

    # Verify chat_completion was called with role=ModelRole.META
    mock_provider.chat_completion.assert_called_once()
    call_kwargs = mock_provider.chat_completion.call_args
    assert call_kwargs.kwargs.get("role") == ModelRole.META or (
        len(call_kwargs.args) >= 3 and call_kwargs.args[2] == ModelRole.META
    )


# ===========================================================================
# Wizard language/channel awareness (LANG-04)
# ===========================================================================


class TestWizardLanguageChannel:
    """Test _format_user_prompt includes language and channel when provided."""

    def test_language_spanish_included_in_prompt(self) -> None:
        """_format_user_prompt with language='es' includes 'Language:' section."""
        body = WizardGenerateRequest(
            id="test",
            purpose="Test purpose",
            language="es",
        )
        result = _format_user_prompt(body)
        assert "Language:" in result
        assert "es" in result

    def test_channel_voice_included_in_prompt(self) -> None:
        """_format_user_prompt with channel='voice' includes 'Channel:' section."""
        body = WizardGenerateRequest(
            id="test",
            purpose="Test purpose",
            channel="voice",
        )
        result = _format_user_prompt(body)
        assert "Channel:" in result
        assert "voice" in result.lower()

    def test_no_language_no_channel_sections(self) -> None:
        """_format_user_prompt without language/channel does NOT include those sections."""
        body = WizardGenerateRequest(
            id="test",
            purpose="Test purpose",
        )
        result = _format_user_prompt(body)
        assert "Language:" not in result
        assert "Channel:" not in result

    def test_english_language_no_section(self) -> None:
        """_format_user_prompt with language='en' does NOT include Language section."""
        body = WizardGenerateRequest(
            id="test",
            purpose="Test purpose",
            language="en",
        )
        result = _format_user_prompt(body)
        assert "Language:" not in result

    def test_text_channel_no_section(self) -> None:
        """_format_user_prompt with channel='text' does NOT include Channel section."""
        body = WizardGenerateRequest(
            id="test",
            purpose="Test purpose",
            channel="text",
        )
        result = _format_user_prompt(body)
        assert "Channel:" not in result
