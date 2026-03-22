"""Tests for dataset models: PriorityTier, TestCase, DatasetSummary, DatasetImportSchema."""

from datetime import datetime

import pytest

from api.dataset.models import DatasetSummary, PriorityTier, TestCase
from api.dataset.schemas import DatasetImportSchema


class TestPriorityTier:
    """Tests for PriorityTier enum."""

    def test_critical_value(self):
        assert PriorityTier.CRITICAL == "critical"

    def test_normal_value(self):
        assert PriorityTier.NORMAL == "normal"

    def test_low_value(self):
        assert PriorityTier.LOW == "low"

    def test_has_exactly_three_members(self):
        assert len(PriorityTier) == 3

    def test_default_is_normal(self):
        """PriorityTier default should be NORMAL when used as a model field default."""
        case = TestCase()
        assert case.tier == PriorityTier.NORMAL


class TestTestCase:
    """Tests for TestCase model."""

    def test_all_defaults(self):
        """TestCase requires no fields -- all have sensible defaults."""
        case = TestCase()
        assert case.id is not None
        assert len(case.id) > 0
        assert case.chat_history == []
        assert case.variables == {}
        assert case.tools is None
        assert case.expected_output is None
        assert case.tier == PriorityTier.NORMAL
        assert isinstance(case.created_at, datetime)
        assert case.tags == []
        assert case.name is None
        assert case.description is None

    def test_id_auto_generates_uuid(self):
        """Each TestCase gets a unique UUID if not provided."""
        case1 = TestCase()
        case2 = TestCase()
        assert case1.id != case2.id
        # UUID format check (36 chars with hyphens)
        assert len(case1.id) == 36
        assert case1.id.count("-") == 4

    def test_id_can_be_provided(self):
        case = TestCase(id="my-custom-id")
        assert case.id == "my-custom-id"

    def test_chat_history_defaults_to_empty_list(self):
        case = TestCase()
        assert case.chat_history == []

    def test_chat_history_with_messages(self):
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        case = TestCase(chat_history=history)
        assert case.chat_history == history
        assert len(case.chat_history) == 2

    def test_variables_defaults_to_empty_dict(self):
        case = TestCase()
        assert case.variables == {}

    def test_variables_with_values(self):
        case = TestCase(variables={"name": "Alice", "age": 30})
        assert case.variables == {"name": "Alice", "age": 30}

    def test_tools_defaults_to_none(self):
        case = TestCase()
        assert case.tools is None

    def test_tools_with_definitions(self):
        tools = [{"type": "function", "function": {"name": "get_weather"}}]
        case = TestCase(tools=tools)
        assert case.tools == tools

    def test_expected_output_defaults_to_none(self):
        case = TestCase()
        assert case.expected_output is None

    def test_expected_output_with_value(self):
        expected = {"content": "Hello!", "tool_calls": []}
        case = TestCase(expected_output=expected)
        assert case.expected_output == expected

    def test_tier_defaults_to_normal(self):
        case = TestCase()
        assert case.tier == PriorityTier.NORMAL

    def test_tier_can_be_set_to_critical(self):
        case = TestCase(tier=PriorityTier.CRITICAL)
        assert case.tier == PriorityTier.CRITICAL

    def test_tier_can_be_set_to_low(self):
        case = TestCase(tier=PriorityTier.LOW)
        assert case.tier == PriorityTier.LOW

    def test_created_at_defaults_to_now(self):
        before = datetime.now()
        case = TestCase()
        after = datetime.now()
        assert before <= case.created_at <= after

    def test_tags_defaults_to_empty_list(self):
        case = TestCase()
        assert case.tags == []

    def test_tags_with_values(self):
        case = TestCase(tags=["regression", "critical-path"])
        assert case.tags == ["regression", "critical-path"]

    def test_name_is_optional(self):
        case = TestCase()
        assert case.name is None

    def test_name_can_be_set(self):
        case = TestCase(name="My Test Case")
        assert case.name == "My Test Case"

    def test_description_is_optional(self):
        case = TestCase()
        assert case.description is None

    def test_description_can_be_set(self):
        case = TestCase(description="Tests edge case for empty input")
        assert case.description == "Tests edge case for empty input"

    def test_json_round_trip(self):
        """TestCase round-trips through JSON serialization."""
        original = TestCase(
            name="Round trip test",
            description="Testing serialization",
            chat_history=[{"role": "user", "content": "Hello"}],
            variables={"name": "Bob"},
            tools=[{"type": "function", "function": {"name": "search"}}],
            expected_output={"content": "Hi Bob!"},
            tier=PriorityTier.CRITICAL,
            tags=["test", "serialization"],
        )
        json_str = original.model_dump_json()
        restored = TestCase.model_validate_json(json_str)

        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.chat_history == original.chat_history
        assert restored.variables == original.variables
        assert restored.tools == original.tools
        assert restored.expected_output == original.expected_output
        assert restored.tier == original.tier
        assert restored.tags == original.tags
        assert restored.created_at == original.created_at

    def test_json_round_trip_with_defaults(self):
        """Default TestCase also round-trips correctly."""
        original = TestCase()
        json_str = original.model_dump_json()
        restored = TestCase.model_validate_json(json_str)
        assert restored.id == original.id
        assert restored.tier == original.tier

    def test_independent_default_lists(self):
        """Each TestCase gets its own list/dict instances (no shared mutable defaults)."""
        case1 = TestCase()
        case2 = TestCase()
        case1.chat_history.append({"role": "user", "content": "test"})
        assert case2.chat_history == []
        case1.tags.append("mutated")
        assert case2.tags == []


class TestDatasetSummary:
    """Tests for DatasetSummary model."""

    def test_dataset_summary_fields(self):
        summary = DatasetSummary(
            prompt_id="my-prompt",
            total_cases=10,
            critical_count=3,
            normal_count=5,
            low_count=2,
        )
        assert summary.prompt_id == "my-prompt"
        assert summary.total_cases == 10
        assert summary.critical_count == 3
        assert summary.normal_count == 5
        assert summary.low_count == 2

    def test_dataset_summary_zero_counts(self):
        summary = DatasetSummary(
            prompt_id="empty-prompt",
            total_cases=0,
            critical_count=0,
            normal_count=0,
            low_count=0,
        )
        assert summary.total_cases == 0


class TestDatasetImportSchema:
    """Tests for DatasetImportSchema."""

    def test_validates_list_of_case_dicts(self):
        raw = [
            {"name": "Case 1", "tier": "critical"},
            {"name": "Case 2"},
        ]
        schema = DatasetImportSchema.from_file_content(raw)
        assert len(schema.cases) == 2
        assert schema.cases[0]["name"] == "Case 1"

    def test_validates_wrapper_format(self):
        raw = {
            "cases": [
                {"name": "Case A"},
                {"name": "Case B"},
            ]
        }
        schema = DatasetImportSchema.from_file_content(raw)
        assert len(schema.cases) == 2
        assert schema.cases[0]["name"] == "Case A"

    def test_empty_list(self):
        schema = DatasetImportSchema.from_file_content([])
        assert schema.cases == []

    def test_empty_wrapper(self):
        schema = DatasetImportSchema.from_file_content({"cases": []})
        assert schema.cases == []

    def test_invalid_format_raises(self):
        """Non-list, non-dict input should raise."""
        with pytest.raises((ValueError, TypeError)):
            DatasetImportSchema.from_file_content("not valid")
