"""Tests for registry data models and file format schemas.

Covers:
- VariableDefinition fields and defaults
- VariableDefinition type metadata (var_type, format, fingerprint)
- VariableDefinition schema fields (examples, constraints, default) -- Phase 31
- ArtifactConfig model
- PromptRegistration validation (slug format, fields)
- PromptRecord fields and types
- VariablesSchema JSON serialization
- PromptConfigSchema JSON serialization
- ToolsSchema JSON serialization
- ToolsYamlSchema YAML serialization -- Phase 31
- MocksSchema YAML serialization -- Phase 31
"""

import json
from datetime import datetime, timezone

import pytest


class TestVariableDefinition:
    """Test VariableDefinition model."""

    def test_variable_definition_fields(self):
        """VariableDefinition has name, description, required, is_anchor with correct defaults."""
        from api.registry.models import VariableDefinition

        var = VariableDefinition(name="customer_name")
        assert var.name == "customer_name"
        assert var.description is None
        assert var.required is True
        assert var.is_anchor is False

    def test_variable_definition_all_fields(self):
        """VariableDefinition accepts all fields."""
        from api.registry.models import VariableDefinition

        var = VariableDefinition(
            name="business_type",
            description="Type of business for the prompt",
            required=False,
            is_anchor=True,
        )
        assert var.name == "business_type"
        assert var.description == "Type of business for the prompt"
        assert var.required is False
        assert var.is_anchor is True


class TestVariableDefinitionTypeMetadata:
    """Test VariableDefinition type metadata fields (EDM-02)."""

    def test_backward_compat_defaults_to_none(self):
        """VariableDefinition(name='x') still works with all new fields defaulting to None."""
        from api.registry.models import VariableDefinition

        var = VariableDefinition(name="x")
        assert var.var_type is None
        assert var.format is None

    def test_var_type_and_format_set(self):
        """VariableDefinition(name='x', var_type='string', format='email') sets both fields."""
        from api.registry.models import VariableDefinition

        var = VariableDefinition(name="x", var_type="string", format="email")
        assert var.var_type == "string"
        assert var.format == "email"

    def test_fingerprint_returns_16_char_hex(self):
        """VariableDefinition.fingerprint() returns a 16-char hex string."""
        from api.registry.models import VariableDefinition

        var = VariableDefinition(name="x", var_type="string", format="email")
        fp = var.fingerprint()
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)

    def test_fingerprint_deterministic(self):
        """Two VariableDefinitions with same name/type/format/description produce identical fingerprints."""
        from api.registry.models import VariableDefinition

        var1 = VariableDefinition(
            name="x", var_type="string", format="email", description="An email"
        )
        var2 = VariableDefinition(
            name="x", var_type="string", format="email", description="An email"
        )
        assert var1.fingerprint() == var2.fingerprint()

    def test_fingerprint_changes_with_var_type(self):
        """Changing var_type changes the fingerprint."""
        from api.registry.models import VariableDefinition

        var1 = VariableDefinition(name="x", var_type="string")
        var2 = VariableDefinition(name="x", var_type="integer")
        assert var1.fingerprint() != var2.fingerprint()


class TestArtifactConfig:
    """Test ArtifactConfig model (EDM-01)."""

    def test_backward_compat_all_none(self):
        """ArtifactConfig() with no args has all None fields."""
        from api.registry.models import ArtifactConfig

        ac = ArtifactConfig()
        assert ac.target_model is None
        assert ac.tools_hash is None
        assert ac.generation is None


class TestVariablesSchemaBackwardCompat:
    """Test that existing variables.json format (without var_type/format) deserializes."""

    def test_existing_format_deserializes(self):
        """Existing variables.json without var_type/format deserializes through VariablesSchema.from_json()."""
        from api.registry.schemas import VariablesSchema

        # Simulate existing variables.json format (no var_type or format fields)
        json_str = json.dumps(
            {
                "variables": [
                    {
                        "name": "customer_name",
                        "description": "Name",
                        "required": True,
                        "is_anchor": False,
                    }
                ]
            }
        )
        schema = VariablesSchema.from_json(json_str)
        assert len(schema.variables) == 1
        assert schema.variables[0].name == "customer_name"
        assert schema.variables[0].var_type is None
        assert schema.variables[0].format is None


class TestPromptRegistration:
    """Test PromptRegistration model."""

    def test_prompt_registration_fields(self):
        """PromptRegistration has all required and optional fields."""
        from api.registry.models import PromptRegistration

        reg = PromptRegistration(
            id="salon-assistant",
            purpose="Help customers book salon appointments",
            template="Hello {{ customer_name }}, welcome to {{ business_name }}.",
        )
        assert reg.id == "salon-assistant"
        assert reg.purpose == "Help customers book salon appointments"
        assert reg.template == "Hello {{ customer_name }}, welcome to {{ business_name }}."
        assert reg.variables is None
        assert reg.tools is None
        assert reg.target_model is None
        assert reg.generation is None

    def test_prompt_registration_slug_valid(self):
        """Valid slug formats are accepted."""
        from api.registry.models import PromptRegistration

        # Single character
        reg = PromptRegistration(id="a", purpose="test", template="test")
        assert reg.id == "a"

        # Multi-char with hyphens
        reg = PromptRegistration(id="my-prompt-v2", purpose="test", template="test")
        assert reg.id == "my-prompt-v2"

        # Alphanumeric only
        reg = PromptRegistration(id="prompt123", purpose="test", template="test")
        assert reg.id == "prompt123"

    def test_prompt_registration_slug_rejects_invalid(self):
        """Invalid slug formats are rejected."""
        from api.registry.models import PromptRegistration

        # Uppercase
        with pytest.raises(ValueError):
            PromptRegistration(id="My-Prompt", purpose="test", template="test")

        # Starts with hyphen
        with pytest.raises(ValueError):
            PromptRegistration(id="-invalid", purpose="test", template="test")

        # Ends with hyphen
        with pytest.raises(ValueError):
            PromptRegistration(id="invalid-", purpose="test", template="test")

        # Contains spaces
        with pytest.raises(ValueError):
            PromptRegistration(id="my prompt", purpose="test", template="test")

        # Contains underscores
        with pytest.raises(ValueError):
            PromptRegistration(id="my_prompt", purpose="test", template="test")

        # Empty string
        with pytest.raises(ValueError):
            PromptRegistration(id="", purpose="test", template="test")

    def test_prompt_registration_slug_max_length(self):
        """Slug must be <= 100 characters."""
        from api.registry.models import PromptRegistration

        # 100 chars should work
        long_id = "a" * 100
        reg = PromptRegistration(id=long_id, purpose="test", template="test")
        assert len(reg.id) == 100

        # 101 chars should fail
        with pytest.raises(ValueError):
            PromptRegistration(id="a" * 101, purpose="test", template="test")

    def test_prompt_registration_with_optional_fields(self):
        """PromptRegistration accepts variables, tools, target_model, generation."""
        from api.config.models import GenerationConfig
        from api.registry.models import PromptRegistration, VariableDefinition

        reg = PromptRegistration(
            id="full-prompt",
            purpose="A prompt with all options",
            template="Hello {{ name }}",
            variables=[VariableDefinition(name="name", description="Customer name")],
            tools=[{"type": "function", "function": {"name": "lookup", "parameters": {}}}],
            target_model="openai/gpt-4o",
            generation=GenerationConfig(temperature=0.5, max_tokens=2048),
        )
        assert len(reg.variables) == 1
        assert len(reg.tools) == 1
        assert reg.target_model == "openai/gpt-4o"
        assert reg.generation.temperature == 0.5


class TestPromptRecord:
    """Test PromptRecord model."""

    def test_prompt_record_fields(self):
        """PromptRecord has id, purpose, template_variables, anchor_variables, commit_hash, created_at."""
        from api.registry.models import PromptRecord

        now = datetime.now(timezone.utc)
        record = PromptRecord(
            id="salon-assistant",
            purpose="Help customers",
            template_variables={"customer_name", "business_name"},
            anchor_variables={"business_name"},
            commit_hash="abc123",
            created_at=now,
        )
        assert record.id == "salon-assistant"
        assert record.purpose == "Help customers"
        assert record.template_variables == {"customer_name", "business_name"}
        assert record.anchor_variables == {"business_name"}
        assert record.commit_hash == "abc123"
        assert record.created_at == now

    def test_prompt_record_defaults(self):
        """PromptRecord commit_hash defaults to None."""
        from api.registry.models import PromptRecord

        record = PromptRecord(
            id="test",
            purpose="test",
            template_variables=set(),
            anchor_variables=set(),
            created_at=datetime.now(timezone.utc),
        )
        assert record.commit_hash is None
        assert record.config is None


class TestPromptMetadata:
    """Test PromptRegistration and PromptRecord metadata fields (EDM-01)."""

    def test_registration_backward_compat(self):
        """PromptRegistration(id='x', purpose='p', template='t') still works with new fields defaulting."""
        from api.registry.models import PromptRegistration

        reg = PromptRegistration(id="x", purpose="p", template="t")
        assert reg.description is None
        assert reg.category_tags == []

    def test_registration_with_metadata(self):
        """PromptRegistration with description and category_tags sets both."""
        from api.registry.models import PromptRegistration

        reg = PromptRegistration(
            id="x",
            purpose="p",
            template="t",
            description="A helpful bot",
            category_tags=["customer-service"],
        )
        assert reg.description == "A helpful bot"
        assert reg.category_tags == ["customer-service"]

    def test_record_backward_compat(self):
        """PromptRecord with minimal args still works (backward compat)."""
        from api.registry.models import PromptRecord

        now = datetime.now(timezone.utc)
        record = PromptRecord(
            id="x",
            purpose="p",
            template_variables=set(),
            anchor_variables=set(),
            created_at=now,
        )
        assert record.description is None
        assert record.category_tags == []
        assert record.artifacts is None

    def test_record_with_all_metadata(self):
        """PromptRecord with description, category_tags, artifacts sets all fields."""
        from api.registry.models import ArtifactConfig, PromptRecord

        now = datetime.now(timezone.utc)
        artifacts = ArtifactConfig(target_model="openai/gpt-4o")
        record = PromptRecord(
            id="x",
            purpose="p",
            template_variables={"name"},
            anchor_variables=set(),
            created_at=now,
            description="A detailed description",
            category_tags=["sales", "onboarding"],
            artifacts=artifacts,
        )
        assert record.description == "A detailed description"
        assert record.category_tags == ["sales", "onboarding"]
        assert record.artifacts is not None
        assert record.artifacts.target_model == "openai/gpt-4o"

    def test_record_artifacts_can_hold_artifact_config(self):
        """PromptRecord.artifacts can hold an ArtifactConfig instance."""
        from api.registry.models import ArtifactConfig, PromptRecord

        now = datetime.now(timezone.utc)
        ac = ArtifactConfig(
            target_model="openai/gpt-4o",
            tools_hash="abc123",
            generation={"temperature": 0.7},
        )
        record = PromptRecord(
            id="x",
            purpose="p",
            template_variables=set(),
            anchor_variables=set(),
            created_at=now,
            artifacts=ac,
        )
        assert isinstance(record.artifacts, ArtifactConfig)
        assert record.artifacts.tools_hash == "abc123"

    def test_record_artifacts_none_valid(self):
        """PromptRecord with artifacts=None is valid (no artifacts tracked yet)."""
        from api.registry.models import PromptRecord

        now = datetime.now(timezone.utc)
        record = PromptRecord(
            id="x",
            purpose="p",
            template_variables=set(),
            anchor_variables=set(),
            created_at=now,
            artifacts=None,
        )
        assert record.artifacts is None


class TestVariablesSchema:
    """Test VariablesSchema JSON serialization."""

    def test_variables_schema_to_json(self):
        """VariablesSchema serializes to JSON matching variables.json format."""
        from api.registry.models import VariableDefinition
        from api.registry.schemas import VariablesSchema

        schema = VariablesSchema(
            variables=[
                VariableDefinition(name="customer_name", description="Name of customer"),
                VariableDefinition(name="business_type", is_anchor=True),
            ]
        )
        json_str = schema.to_json()
        parsed = json.loads(json_str)

        assert "variables" in parsed
        assert len(parsed["variables"]) == 2
        assert parsed["variables"][0]["name"] == "customer_name"
        assert parsed["variables"][0]["description"] == "Name of customer"
        assert parsed["variables"][1]["is_anchor"] is True

    def test_variables_schema_from_json(self):
        """VariablesSchema deserializes from JSON."""
        from api.registry.schemas import VariablesSchema

        json_str = json.dumps(
            {
                "variables": [
                    {"name": "greeting", "description": None, "required": True, "is_anchor": False}
                ]
            }
        )
        schema = VariablesSchema.from_json(json_str)
        assert len(schema.variables) == 1
        assert schema.variables[0].name == "greeting"


class TestPromptConfigSchema:
    """Test PromptConfigSchema JSON serialization."""

    def test_config_schema_fields(self):
        """PromptConfigSchema has target_model, generation, meta_model, judge_model."""
        from api.config.models import GenerationConfig
        from api.registry.schemas import PromptConfigSchema

        schema = PromptConfigSchema(
            target_model="openai/gpt-4o",
            generation=GenerationConfig(temperature=0.3),
        )
        assert schema.target_model == "openai/gpt-4o"
        assert schema.generation.temperature == 0.3
        assert schema.meta_model is None
        assert schema.judge_model is None

    def test_config_schema_to_json(self):
        """PromptConfigSchema serializes to JSON matching config.json format."""
        from api.config.models import GenerationConfig
        from api.registry.schemas import PromptConfigSchema

        schema = PromptConfigSchema(
            target_model="openai/gpt-4o",
            generation=GenerationConfig(temperature=0.5, max_tokens=2048),
        )
        json_str = schema.to_json()
        parsed = json.loads(json_str)

        assert parsed["target_model"] == "openai/gpt-4o"
        assert parsed["generation"]["temperature"] == 0.5
        assert parsed["generation"]["max_tokens"] == 2048

    def test_config_schema_from_json(self):
        """PromptConfigSchema deserializes from JSON."""
        from api.registry.schemas import PromptConfigSchema

        json_str = json.dumps(
            {
                "target_model": "openai/gpt-4o",
                "generation": {"temperature": 0.9},
            }
        )
        schema = PromptConfigSchema.from_json(json_str)
        assert schema.target_model == "openai/gpt-4o"
        assert schema.generation.temperature == 0.9


class TestToolsSchema:
    """Test ToolsSchema JSON serialization."""

    def test_tools_schema_to_json(self):
        """ToolsSchema serializes to JSON."""
        from api.registry.schemas import ToolsSchema

        schema = ToolsSchema(
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get current weather",
                        "parameters": {
                            "type": "object",
                            "properties": {"location": {"type": "string"}},
                        },
                    },
                }
            ]
        )
        json_str = schema.to_json()
        parsed = json.loads(json_str)

        assert "tools" in parsed
        assert len(parsed["tools"]) == 1
        assert parsed["tools"][0]["function"]["name"] == "get_weather"

    def test_tools_schema_from_json(self):
        """ToolsSchema deserializes from JSON."""
        from api.registry.schemas import ToolsSchema

        json_str = json.dumps({"tools": [{"type": "function", "function": {"name": "lookup"}}]})
        schema = ToolsSchema.from_json(json_str)
        assert len(schema.tools) == 1
        assert schema.tools[0]["function"]["name"] == "lookup"


# -- Phase 31: Variable schema fields (examples, constraints, default) --


class TestVariableDefinitionSchemaFields:
    """Test VariableDefinition extended schema fields (Phase 31 / PROMPT-01)."""

    def test_backward_compat_new_fields_default_none(self):
        """VariableDefinition(name='x') works with examples, constraints, default all None."""
        from api.registry.models import VariableDefinition

        var = VariableDefinition(name="x")
        assert var.examples is None
        assert var.constraints is None
        assert var.default is None

    def test_all_new_fields_set(self):
        """VariableDefinition accepts examples, constraints, default."""
        from api.registry.models import VariableDefinition

        var = VariableDefinition(
            name="x",
            examples=["a", "b"],
            constraints={"min_length": 3},
            default="hello",
        )
        assert var.examples == ["a", "b"]
        assert var.constraints == {"min_length": 3}
        assert var.default == "hello"

    def test_fingerprint_unchanged_with_new_fields(self):
        """Adding examples/constraints/default does NOT change the fingerprint."""
        from api.registry.models import VariableDefinition

        var_base = VariableDefinition(name="x", var_type="string", format="email")
        var_extended = VariableDefinition(
            name="x",
            var_type="string",
            format="email",
            examples=["a@b.com"],
            constraints={"min_length": 5},
            default="test@test.com",
        )
        assert var_base.fingerprint() == var_extended.fingerprint()

    def test_existing_variables_json_without_new_fields_deserializes(self):
        """Existing variables.json (without examples/constraints/default) still deserializes."""
        from api.registry.schemas import VariablesSchema

        json_str = json.dumps(
            {
                "variables": [
                    {
                        "name": "customer_name",
                        "description": "Name",
                        "required": True,
                        "is_anchor": False,
                        "var_type": "string",
                    }
                ]
            }
        )
        schema = VariablesSchema.from_json(json_str)
        assert len(schema.variables) == 1
        assert schema.variables[0].examples is None
        assert schema.variables[0].constraints is None
        assert schema.variables[0].default is None

    def test_variables_schema_roundtrip_with_new_fields(self):
        """VariablesSchema round-trip preserves examples, constraints, default."""
        from api.registry.models import VariableDefinition
        from api.registry.schemas import VariablesSchema

        original = VariablesSchema(
            variables=[
                VariableDefinition(
                    name="greeting",
                    var_type="string",
                    examples=["hello", "hi"],
                    constraints={"min_length": 2, "max_length": 50},
                    default="hello",
                )
            ]
        )
        json_str = original.to_json()
        restored = VariablesSchema.from_json(json_str)
        assert restored.variables[0].examples == ["hello", "hi"]
        assert restored.variables[0].constraints == {"min_length": 2, "max_length": 50}
        assert restored.variables[0].default == "hello"


# -- Phase 31: ToolsYamlSchema and MocksSchema YAML models --


class TestToolParameter:
    """Test ToolParameter model (PROMPT-03)."""

    def test_tool_parameter_fields(self):
        """ToolParameter has name, type, description, required, enum."""
        from api.registry.schemas import ToolParameter

        param = ToolParameter(name="target", type="string")
        assert param.name == "target"
        assert param.type == "string"
        assert param.description is None
        assert param.required is False
        assert param.enum is None

    def test_tool_parameter_all_fields(self):
        """ToolParameter accepts all fields including enum."""
        from api.registry.schemas import ToolParameter

        param = ToolParameter(
            name="department",
            type="string",
            description="Target department",
            required=True,
            enum=["ventas", "taller", "recepcion"],
        )
        assert param.required is True
        assert param.enum == ["ventas", "taller", "recepcion"]


class TestToolSchemaDefinition:
    """Test ToolSchemaDefinition model (PROMPT-03)."""

    def test_tool_schema_definition_fields(self):
        """ToolSchemaDefinition has name, description, parameters, returns."""
        from api.registry.schemas import ToolSchemaDefinition

        tool = ToolSchemaDefinition(name="transfer_to_number")
        assert tool.name == "transfer_to_number"
        assert tool.description is None
        assert tool.parameters == []
        assert tool.returns is None

    def test_tool_schema_definition_with_params(self):
        """ToolSchemaDefinition accepts parameters list."""
        from api.registry.schemas import ToolParameter, ToolSchemaDefinition

        tool = ToolSchemaDefinition(
            name="transfer_to_number",
            description="Transfer the call",
            parameters=[
                ToolParameter(name="target", type="string", required=True),
                ToolParameter(name="summary", type="string"),
            ],
            returns="Transfer confirmation",
        )
        assert len(tool.parameters) == 2
        assert tool.parameters[0].name == "target"
        assert tool.returns == "Transfer confirmation"


class TestToolsYamlSchema:
    """Test ToolsYamlSchema YAML serialization (PROMPT-03)."""

    def test_tools_yaml_roundtrip(self):
        """ToolsYamlSchema to_yaml()/from_yaml() round-trip preserves data."""
        from api.registry.schemas import (
            ToolParameter,
            ToolSchemaDefinition,
            ToolsYamlSchema,
        )

        original = ToolsYamlSchema(
            tools=[
                ToolSchemaDefinition(
                    name="transfer_to_number",
                    description="Transfer the call",
                    parameters=[
                        ToolParameter(name="target", type="string", required=True),
                    ],
                    returns="Transfer confirmation",
                )
            ]
        )
        yaml_str = original.to_yaml()
        restored = ToolsYamlSchema.from_yaml(yaml_str)
        assert len(restored.tools) == 1
        assert restored.tools[0].name == "transfer_to_number"
        assert restored.tools[0].parameters[0].name == "target"
        assert restored.tools[0].returns == "Transfer confirmation"

    def test_tools_yaml_empty_string_returns_empty_schema(self):
        """from_yaml with empty string returns valid empty schema."""
        from api.registry.schemas import ToolsYamlSchema

        schema = ToolsYamlSchema.from_yaml("")
        assert schema.tools == []

    def test_tools_yaml_excludes_none(self):
        """to_yaml excludes None fields for clean YAML output."""
        from api.registry.schemas import ToolSchemaDefinition, ToolsYamlSchema

        schema = ToolsYamlSchema(tools=[ToolSchemaDefinition(name="lookup")])
        yaml_str = schema.to_yaml()
        assert "description" not in yaml_str or "null" not in yaml_str


class TestMockScenario:
    """Test MockScenario model (PROMPT-04)."""

    def test_mock_scenario_fields(self):
        """MockScenario has match_args and response."""
        from api.registry.schemas import MockScenario

        scenario = MockScenario(
            match_args={"target": "ventas", "summary": "*"},
            response="Transferring to Ventas",
        )
        assert scenario.match_args == {"target": "ventas", "summary": "*"}
        assert scenario.response == "Transferring to Ventas"


class TestMockDefinition:
    """Test MockDefinition model (PROMPT-04)."""

    def test_mock_definition_fields(self):
        """MockDefinition has tool_name and scenarios."""
        from api.registry.schemas import MockDefinition, MockScenario

        mock = MockDefinition(
            tool_name="transfer_to_number",
            scenarios=[
                MockScenario(match_args={"target": "ventas"}, response="OK"),
            ],
        )
        assert mock.tool_name == "transfer_to_number"
        assert len(mock.scenarios) == 1


class TestMocksSchema:
    """Test MocksSchema YAML serialization (PROMPT-04)."""

    def test_mocks_yaml_roundtrip(self):
        """MocksSchema to_yaml()/from_yaml() round-trip preserves data."""
        from api.registry.schemas import MockDefinition, MockScenario, MocksSchema

        original = MocksSchema(
            mocks=[
                MockDefinition(
                    tool_name="transfer_to_number",
                    scenarios=[
                        MockScenario(
                            match_args={"target": "ventas", "summary": "*"},
                            response="Transferring to Ventas. Summary: {{ summary }}",
                        ),
                    ],
                )
            ]
        )
        yaml_str = original.to_yaml()
        restored = MocksSchema.from_yaml(yaml_str)
        assert len(restored.mocks) == 1
        assert restored.mocks[0].tool_name == "transfer_to_number"
        assert restored.mocks[0].scenarios[0].match_args["target"] == "ventas"
        assert "{{ summary }}" in restored.mocks[0].scenarios[0].response

    def test_mocks_yaml_empty_string_returns_empty_schema(self):
        """from_yaml with empty string returns valid empty schema."""
        from api.registry.schemas import MocksSchema

        schema = MocksSchema.from_yaml("")
        assert schema.mocks == []


# -- Phase 45: Nested variable types (items_schema) --


class TestVariableDefinitionItemsSchema:
    """Test VariableDefinition items_schema for nested/complex variable types (Phase 45)."""

    def test_backward_compat_items_schema_defaults_none(self):
        """VariableDefinition(name='x') still works -- items_schema defaults to None."""
        from api.registry.models import VariableDefinition

        var = VariableDefinition(name="x")
        assert var.items_schema is None

    def test_array_type_with_items_schema(self):
        """VariableDefinition with var_type='array' and items_schema creates valid nested definition."""
        from api.registry.models import VariableDefinition

        var = VariableDefinition(
            name="items",
            var_type="array",
            items_schema=[
                VariableDefinition(name="name", var_type="string"),
                VariableDefinition(name="quantity", var_type="integer"),
            ],
        )
        assert var.var_type == "array"
        assert len(var.items_schema) == 2
        assert var.items_schema[0].name == "name"
        assert var.items_schema[1].name == "quantity"

    def test_object_type_with_items_schema(self):
        """VariableDefinition with var_type='object' and items_schema creates valid nested definition."""
        from api.registry.models import VariableDefinition

        var = VariableDefinition(
            name="address",
            var_type="object",
            items_schema=[
                VariableDefinition(name="street", var_type="string"),
                VariableDefinition(name="city", var_type="string"),
            ],
        )
        assert var.var_type == "object"
        assert len(var.items_schema) == 2
        assert var.items_schema[0].name == "street"
        assert var.items_schema[1].name == "city"

    def test_variables_schema_roundtrip_preserves_items_schema(self):
        """VariablesSchema round-trip (to_json / from_json) preserves items_schema with nested VariableDefinitions."""
        from api.registry.models import VariableDefinition
        from api.registry.schemas import VariablesSchema

        original = VariablesSchema(
            variables=[
                VariableDefinition(
                    name="items",
                    var_type="array",
                    items_schema=[
                        VariableDefinition(name="name", var_type="string", is_anchor=True),
                        VariableDefinition(name="price", var_type="float"),
                    ],
                ),
                VariableDefinition(name="simple_var", var_type="string"),
            ]
        )
        json_str = original.to_json()
        restored = VariablesSchema.from_json(json_str)

        assert len(restored.variables) == 2
        assert restored.variables[0].items_schema is not None
        assert len(restored.variables[0].items_schema) == 2
        assert restored.variables[0].items_schema[0].name == "name"
        assert restored.variables[0].items_schema[0].is_anchor is True
        assert restored.variables[0].items_schema[1].name == "price"
        assert restored.variables[1].items_schema is None

    def test_existing_variables_json_without_items_schema_deserializes(self):
        """Existing variables.json without items_schema field deserializes without error (backward compat)."""
        from api.registry.schemas import VariablesSchema

        json_str = json.dumps(
            {"variables": [{"name": "x", "var_type": "string", "is_anchor": True}]}
        )
        schema = VariablesSchema.from_json(json_str)
        assert schema.variables[0].items_schema is None

    def test_fingerprint_unchanged_by_items_schema(self):
        """fingerprint() is unchanged by items_schema (items_schema not part of fingerprint)."""
        from api.registry.models import VariableDefinition

        var_base = VariableDefinition(name="x", var_type="array")
        var_with_schema = VariableDefinition(
            name="x",
            var_type="array",
            items_schema=[
                VariableDefinition(name="name", var_type="string"),
            ],
        )
        assert var_base.fingerprint() == var_with_schema.fingerprint()


class TestWizardVariableItemsSchema:
    """Test WizardVariable items_schema for API nested types (Phase 45)."""

    def test_wizard_variable_items_schema_defaults_none(self):
        """WizardVariable without items_schema defaults to None."""
        from api.web.schemas import WizardVariable

        wv = WizardVariable(name="x")
        assert wv.items_schema is None

    def test_wizard_variable_with_items_schema(self):
        """WizardVariable accepts items_schema with nested WizardVariables."""
        from api.web.schemas import WizardVariable

        wv = WizardVariable(
            name="items",
            var_type="array",
            items_schema=[
                WizardVariable(name="name", var_type="string"),
                WizardVariable(name="qty", var_type="integer"),
            ],
        )
        assert wv.items_schema is not None
        assert len(wv.items_schema) == 2
        assert wv.items_schema[0].name == "name"
