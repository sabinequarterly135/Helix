"""Tests for MockMatcher engine: scenario-based mock response resolution.

Covers:
- Exact argument matching
- Wildcard "*" matching (any value, key must exist)
- Unknown tool returns None
- No matching scenario returns None
- First-match-wins ordering
- Jinja2 template rendering with argument substitution
- Jinja2 rendering error handling (graceful fallback)
"""

from __future__ import annotations

import pytest

from api.registry.mock_matcher import MockMatcher
from api.registry.schemas import MockDefinition, MockScenario


@pytest.fixture
def sample_mocks() -> list[MockDefinition]:
    """Build mock definitions for a transfer_to_number tool with multiple scenarios."""
    return [
        MockDefinition(
            tool_name="transfer_to_number",
            scenarios=[
                MockScenario(
                    match_args={"target": "ventas"},
                    response="Transferring to sales department. Customer issue: {{ summary }}",
                ),
                MockScenario(
                    match_args={"target": "soporte"},
                    response="Transferring to support. Issue: {{ summary }}",
                ),
                MockScenario(
                    match_args={"target": "*"},
                    response="Transferring to {{ target }}",
                ),
            ],
        ),
        MockDefinition(
            tool_name="hang_up",
            scenarios=[
                MockScenario(
                    match_args={},
                    response="Call ended.",
                ),
            ],
        ),
    ]


class TestMockMatcherExactMatch:
    """Exact argument matching scenarios."""

    def test_exact_match_returns_rendered_response(self, sample_mocks):
        """MockMatcher.match() with exact args matches first scenario and renders Jinja2."""
        result = MockMatcher.match(
            "transfer_to_number",
            {"target": "ventas", "summary": "car issue"},
            sample_mocks,
        )
        assert result == "Transferring to sales department. Customer issue: car issue"

    def test_exact_match_second_scenario(self, sample_mocks):
        """MockMatcher.match() with different exact args matches second scenario."""
        result = MockMatcher.match(
            "transfer_to_number",
            {"target": "soporte", "summary": "billing question"},
            sample_mocks,
        )
        assert result == "Transferring to support. Issue: billing question"


class TestMockMatcherWildcard:
    """Wildcard '*' matching scenarios."""

    def test_wildcard_matches_any_value(self, sample_mocks):
        """Wildcard '*' matches any value when key is present in call_args."""
        result = MockMatcher.match(
            "transfer_to_number",
            {"target": "unknown_dept"},
            sample_mocks,
        )
        assert result == "Transferring to unknown_dept"

    def test_wildcard_requires_key_present(self, sample_mocks):
        """Wildcard '*' requires the key to exist in call_args; missing key = no match."""
        result = MockMatcher.match(
            "transfer_to_number",
            {},
            sample_mocks,
        )
        assert result is None


class TestMockMatcherNoMatch:
    """No-match scenarios."""

    def test_unknown_tool_returns_none(self, sample_mocks):
        """MockMatcher.match() with unknown tool_name returns None."""
        result = MockMatcher.match(
            "unknown_tool",
            {"target": "ventas"},
            sample_mocks,
        )
        assert result is None

    def test_no_matching_scenario_returns_none(self, sample_mocks):
        """MockMatcher.match() with no matching scenario returns None."""
        result = MockMatcher.match(
            "transfer_to_number",
            {},
            sample_mocks,
        )
        assert result is None

    def test_empty_mocks_list_returns_none(self):
        """MockMatcher.match() with empty mocks list returns None."""
        result = MockMatcher.match("any_tool", {"key": "val"}, [])
        assert result is None


class TestMockMatcherFirstMatchWins:
    """First-match-wins ordering."""

    def test_first_match_wins_over_wildcard(self, sample_mocks):
        """Exact match scenario (first) wins over wildcard (third), even though both match."""
        result = MockMatcher.match(
            "transfer_to_number",
            {"target": "ventas", "summary": "test"},
            sample_mocks,
        )
        # "ventas" exact match wins over "*" wildcard
        assert "sales department" in result

    def test_first_match_wins_ordering(self):
        """When two exact scenarios both match, the first one wins."""
        mocks = [
            MockDefinition(
                tool_name="greet",
                scenarios=[
                    MockScenario(match_args={"lang": "en"}, response="Hello"),
                    MockScenario(match_args={"lang": "en"}, response="Hi"),
                ],
            )
        ]
        result = MockMatcher.match("greet", {"lang": "en"}, mocks)
        assert result == "Hello"


class TestMockMatcherJinja2:
    """Jinja2 template rendering."""

    def test_template_renders_arguments(self, sample_mocks):
        """Jinja2 {{ argument_name }} templates are rendered with call_args values."""
        result = MockMatcher.match(
            "transfer_to_number",
            {"target": "ventas", "summary": "car issue"},
            sample_mocks,
        )
        assert "car issue" in result

    def test_template_with_missing_variable_returns_raw(self):
        """Jinja2 rendering error (missing required variable) returns raw template string."""
        mocks = [
            MockDefinition(
                tool_name="greet",
                scenarios=[
                    MockScenario(
                        match_args={"lang": "en"},
                        response="Hello {{ missing_var }}",
                    ),
                ],
            )
        ]
        result = MockMatcher.match("greet", {"lang": "en"}, mocks)
        # Should return raw template on undefined error, not crash
        assert result is not None
        assert "Hello" in result

    def test_template_with_invalid_syntax_returns_raw(self):
        """Jinja2 syntax error in template returns raw template string."""
        mocks = [
            MockDefinition(
                tool_name="greet",
                scenarios=[
                    MockScenario(
                        match_args={"lang": "en"},
                        response="Hello {{ broken }%}",
                    ),
                ],
            )
        ]
        result = MockMatcher.match("greet", {"lang": "en"}, mocks)
        # Should return raw template on syntax error, not crash
        assert result is not None

    def test_empty_match_args_matches_any_call(self):
        """Scenario with empty match_args matches any call_args."""
        mocks = [
            MockDefinition(
                tool_name="hang_up",
                scenarios=[
                    MockScenario(match_args={}, response="Call ended."),
                ],
            )
        ]
        result = MockMatcher.match("hang_up", {"reason": "done"}, mocks)
        assert result == "Call ended."


class TestModelExtensions:
    """PromptRegistration and PromptRecord field extensions."""

    def test_prompt_registration_has_tool_schemas_field(self):
        """PromptRegistration has optional tool_schemas field defaulting to None."""
        from api.registry.models import PromptRegistration

        reg = PromptRegistration(
            id="test-prompt",
            purpose="Test",
            template="Hello {{ name }}",
        )
        assert reg.tool_schemas is None

    def test_prompt_registration_accepts_tool_schemas(self):
        """PromptRegistration accepts tool_schemas as list[dict]."""
        from api.registry.models import PromptRegistration

        reg = PromptRegistration(
            id="test-prompt",
            purpose="Test",
            template="Hello {{ name }}",
            tool_schemas=[{"name": "transfer", "parameters": []}],
        )
        assert reg.tool_schemas is not None
        assert len(reg.tool_schemas) == 1

    def test_prompt_registration_has_mocks_field(self):
        """PromptRegistration has optional mocks field defaulting to None."""
        from api.registry.models import PromptRegistration

        reg = PromptRegistration(
            id="test-prompt",
            purpose="Test",
            template="Hello {{ name }}",
        )
        assert reg.mocks is None

    def test_prompt_registration_accepts_mocks(self):
        """PromptRegistration accepts mocks as list[dict]."""
        from api.registry.models import PromptRegistration

        reg = PromptRegistration(
            id="test-prompt",
            purpose="Test",
            template="Hello {{ name }}",
            mocks=[{"tool_name": "transfer", "scenarios": []}],
        )
        assert reg.mocks is not None
        assert len(reg.mocks) == 1

    def test_prompt_record_has_tool_schemas_field(self):
        """PromptRecord has optional tool_schemas field defaulting to None."""
        from datetime import datetime, timezone

        from api.registry.models import PromptRecord

        record = PromptRecord(
            id="test",
            purpose="Test",
            template_variables=set(),
            anchor_variables=set(),
            created_at=datetime.now(timezone.utc),
        )
        assert record.tool_schemas is None

    def test_prompt_record_accepts_tool_schemas(self):
        """PromptRecord accepts tool_schemas as list[ToolSchemaDefinition]."""
        from datetime import datetime, timezone

        from api.registry.models import PromptRecord
        from api.registry.schemas import ToolSchemaDefinition

        record = PromptRecord(
            id="test",
            purpose="Test",
            template_variables=set(),
            anchor_variables=set(),
            created_at=datetime.now(timezone.utc),
            tool_schemas=[ToolSchemaDefinition(name="transfer")],
        )
        assert record.tool_schemas is not None
        assert len(record.tool_schemas) == 1

    def test_prompt_record_has_mocks_field(self):
        """PromptRecord has optional mocks field defaulting to None."""
        from datetime import datetime, timezone

        from api.registry.models import PromptRecord

        record = PromptRecord(
            id="test",
            purpose="Test",
            template_variables=set(),
            anchor_variables=set(),
            created_at=datetime.now(timezone.utc),
        )
        assert record.mocks is None

    def test_prompt_record_accepts_mocks(self):
        """PromptRecord accepts mocks as list[MockDefinition]."""
        from datetime import datetime, timezone

        from api.registry.models import PromptRecord
        from api.registry.schemas import MockDefinition, MockScenario

        record = PromptRecord(
            id="test",
            purpose="Test",
            template_variables=set(),
            anchor_variables=set(),
            created_at=datetime.now(timezone.utc),
            mocks=[
                MockDefinition(
                    tool_name="t", scenarios=[MockScenario(match_args={}, response="ok")]
                )
            ],
        )
        assert record.mocks is not None
        assert len(record.mocks) == 1


class TestApiSchemaExtensions:
    """API schema extensions for tool_schemas and mocks."""

    def test_prompt_detail_has_tool_schemas(self):
        """PromptDetail has optional tool_schemas field."""
        from api.web.schemas import PromptDetail

        detail = PromptDetail(
            id="test",
            purpose="Test",
            template_variables=["name"],
            anchor_variables=[],
            template="Hello {{ name }}",
        )
        assert detail.tool_schemas is None

    def test_prompt_detail_has_mocks(self):
        """PromptDetail has optional mocks field."""
        from api.web.schemas import PromptDetail

        detail = PromptDetail(
            id="test",
            purpose="Test",
            template_variables=["name"],
            anchor_variables=[],
            template="Hello {{ name }}",
        )
        assert detail.mocks is None

    def test_create_prompt_request_has_tool_schemas(self):
        """CreatePromptRequest has optional tool_schemas field."""
        from api.web.schemas import CreatePromptRequest

        req = CreatePromptRequest(
            id="test",
            purpose="Test",
            template="Hello",
        )
        assert req.tool_schemas is None

    def test_create_prompt_request_has_mocks(self):
        """CreatePromptRequest has optional mocks field."""
        from api.web.schemas import CreatePromptRequest

        req = CreatePromptRequest(
            id="test",
            purpose="Test",
            template="Hello",
        )
        assert req.mocks is None
