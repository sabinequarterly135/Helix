"""File format schemas for prompt sidecar files.

Provides serialization models for the JSON sidecar files stored alongside
each prompt's template:
- variables.json -> VariablesSchema
- config.json -> PromptConfigSchema
- tools.json -> ToolsSchema
- tools.yaml -> ToolsYamlSchema (Phase 31)
- mocks.yaml -> MocksSchema (Phase 31)
"""

from typing import Any

import yaml
from pydantic import BaseModel, Field

from api.config.models import GenerationConfig
from api.registry.models import VariableDefinition


class VariablesSchema(BaseModel):
    """Schema for variables.json sidecar file.

    Contains the list of variable definitions for a prompt template.
    """

    variables: list[VariableDefinition]

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> "VariablesSchema":
        """Deserialize from JSON string."""
        return cls.model_validate_json(text)


class PromptConfigSchema(BaseModel):
    """Schema for config.json sidecar file.

    Contains per-prompt configuration overrides that get merged
    onto the global GeneConfig via load_prompt_config.

    All fields are optional (None = use global default). The to_json()
    method uses exclude_none to keep config.json files clean and
    backward-compatible with existing prompts.
    """

    # Models (existing)
    meta_model: str | None = None
    target_model: str | None = None
    judge_model: str | None = None

    # Providers (new -- always paired with models conceptually, but
    # no cross-field validator; pairing enforced by UI per CFG-05)
    meta_provider: str | None = None
    target_provider: str | None = None
    judge_provider: str | None = None

    # Per-role temperature (new -- supersedes generation.temperature for per-prompt)
    meta_temperature: float | None = None
    target_temperature: float | None = None
    judge_temperature: float | None = None

    # Per-role thinking budget (new)
    meta_thinking_budget: int | None = None
    target_thinking_budget: int | None = None
    judge_thinking_budget: int | None = None

    # Tool Mocker config (Phase 55)
    tool_mocker_mode: str | None = None  # "static" or "llm", default None means "static"
    tool_mocker_provider: str | None = None
    tool_mocker_model: str | None = None
    max_tool_steps: int | None = None

    # Legacy generation config (kept for backward compat with existing config.json files)
    generation: GenerationConfig | None = None

    def to_json(self) -> str:
        """Serialize to JSON string, excluding None fields."""
        return self.model_dump_json(indent=2, exclude_none=True)

    @classmethod
    def from_json(cls, text: str) -> "PromptConfigSchema":
        """Deserialize from JSON string."""
        return cls.model_validate_json(text)


class ToolsSchema(BaseModel):
    """Schema for tools.json sidecar file.

    Contains tool definitions following OpenAI/OpenRouter tool schema format.
    """

    tools: list[dict[str, Any]]

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> "ToolsSchema":
        """Deserialize from JSON string."""
        return cls.model_validate_json(text)


# -- Phase 31: YAML-based tool schema and mock models --


class ToolParameter(BaseModel):
    """Parameter definition for a tool schema.

    Attributes:
        name: Parameter name.
        type: Parameter type (e.g. "string", "integer", "boolean").
        description: Human-readable description.
        required: Whether this parameter is required.
        enum: Optional list of allowed values.
    """

    name: str
    type: str
    description: str | None = None
    required: bool = False
    enum: list[str] | None = None


class ToolSchemaDefinition(BaseModel):
    """Human-readable tool schema definition for tools.yaml.

    Distinct from ToolsSchema (tools.json) which uses the OpenAI API format.

    Attributes:
        name: Tool function name.
        description: Human-readable description of the tool.
        parameters: List of parameter definitions.
        returns: Description of what the tool returns.
    """

    name: str
    description: str | None = None
    parameters: list[ToolParameter] = Field(default_factory=list)
    returns: str | None = None


class ToolsYamlSchema(BaseModel):
    """Schema for tools.yaml sidecar file.

    Human-readable tool schema definitions alongside the existing tools.json.
    """

    tools: list[ToolSchemaDefinition] = Field(default_factory=list)

    def to_yaml(self) -> str:
        """Serialize to YAML string, excluding None fields."""
        data = self.model_dump(exclude_none=True)
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

    @classmethod
    def from_yaml(cls, text: str) -> "ToolsYamlSchema":
        """Deserialize from YAML string. Handles empty/None safely."""
        raw = yaml.safe_load(text) or {}
        return cls.model_validate(raw)


class MockScenario(BaseModel):
    """A single mock response scenario for a tool.

    Attributes:
        match_args: Key-value pairs to match against tool call arguments.
            Use "*" as a value wildcard to match any value for that key.
        response: Jinja2 template string for the mock response.
    """

    match_args: dict[str, Any]
    response: str


class MockDefinition(BaseModel):
    """Mock response definition for a single tool.

    Attributes:
        tool_name: Name of the tool being mocked.
        scenarios: List of match scenarios; first match wins.
    """

    tool_name: str
    scenarios: list[MockScenario]


class MocksSchema(BaseModel):
    """Schema for mocks.yaml sidecar file.

    Contains mock response fixtures per tool with scenario-based matching.
    """

    mocks: list[MockDefinition] = Field(default_factory=list)

    def to_yaml(self) -> str:
        """Serialize to YAML string, excluding None fields."""
        data = self.model_dump(exclude_none=True)
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

    @classmethod
    def from_yaml(cls, text: str) -> "MocksSchema":
        """Deserialize from YAML string. Handles empty/None safely."""
        raw = yaml.safe_load(text) or {}
        return cls.model_validate(raw)


# Rebuild PromptRecord now that ToolSchemaDefinition, MockDefinition, and
# PersonaProfile are defined. PromptRecord uses string forward references
# to avoid circular imports.
from api.registry.models import PromptRecord  # noqa: E402
from api.synthesis.models import PersonaProfile  # noqa: E402, F401

PromptRecord.model_rebuild()
