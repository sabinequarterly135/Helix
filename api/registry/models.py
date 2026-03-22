"""Pydantic models for prompt registration data.

Provides:
- VariableDefinition: Defines a template variable with anchor marking and type metadata
- ArtifactConfig: Bundled artifact configuration for change detection
- PromptRegistration: Input model for registering a new prompt
- PromptRecord: Output model representing a registered prompt
"""

import hashlib
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

from api.config.models import GeneConfig, GenerationConfig

if TYPE_CHECKING:
    from api.registry.schemas import MockDefinition, ToolSchemaDefinition
    from api.synthesis.models import PersonaProfile


class VariableDefinition(BaseModel):
    """Definition of a Jinja2 template variable.

    Attributes:
        name: Variable name (must match a Jinja2 template variable).
        description: Human-readable description of the variable's purpose.
        required: Whether this variable must be provided when rendering.
        is_anchor: If True, this variable is fixed during evolution --
            its placeholder must always remain in the template.
        var_type: Type hint for the variable value (e.g. "string", "integer",
            "float", "boolean", "json", "list"). None if unspecified.
        format: Free-form format hint (e.g. "email", "ISO-8601", "markdown", "url").
            None if unspecified.
    """

    name: str
    description: str | None = None
    required: bool = True
    is_anchor: bool = False
    var_type: str | None = None
    format: str | None = None
    # Phase 31: schema enrichment fields
    examples: list[Any] | None = None
    constraints: dict[str, Any] | None = None
    default: Any | None = None
    # Phase 45: nested type schemas (array-of-objects, nested objects)
    items_schema: list["VariableDefinition"] | None = None

    def fingerprint(self) -> str:
        """SHA-256 hash of type-affecting fields for change detection.

        Returns first 16 hex characters of the hash.
        """
        content = f"{self.name}:{self.var_type}:{self.description}:{self.format}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# Resolve self-referencing forward ref for items_schema
VariableDefinition.model_rebuild()


class ArtifactConfig(BaseModel):
    """Bundled artifact configuration for change detection.

    Attributes:
        target_model: The LLM model identifier.
        tools_hash: Precomputed hash of tool definitions.
        generation: Generation parameters (temperature, max_tokens, etc.).
    """

    target_model: str | None = None
    tools_hash: str | None = None
    generation: dict | None = None


# Slug pattern: lowercase alphanumeric + hyphens, 1-100 chars.
# Single char OR multi-char that doesn't start/end with hyphen.
_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


class PromptRegistration(BaseModel):
    """Input model for registering a new prompt.

    Attributes:
        id: Unique slug identifier (lowercase alphanumeric + hyphens, 1-100 chars).
        purpose: Human-readable description of what this prompt does.
        template: Jinja2 template content (the prompt text with {{variables}}).
        variables: Optional explicit variable definitions. If None, variables
            are auto-extracted from the template.
        tools: Optional OpenAI/OpenRouter tool definitions.
        target_model: Per-prompt target model override.
        generation: Per-prompt generation config override.
        description: Longer description beyond the existing purpose field.
        category_tags: Searchable tags (e.g. ["customer-service", "sales"]).
    """

    id: str
    purpose: str
    template: str
    variables: list[VariableDefinition] | None = None
    tools: list[dict[str, Any]] | None = None
    target_model: str | None = None
    generation: GenerationConfig | None = None
    description: str | None = None
    category_tags: list[str] = Field(default_factory=list)
    # Phase 31: YAML sidecar data (validated into Pydantic models by the service)
    tool_schemas: list[dict[str, Any]] | None = None
    mocks: list[dict[str, Any]] | None = None

    @field_validator("id")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate that id is a valid slug format."""
        if not v:
            raise ValueError("Prompt ID cannot be empty")
        if len(v) > 100:
            raise ValueError(f"Prompt ID must be <= 100 characters, got {len(v)}")
        if not _SLUG_PATTERN.match(v):
            raise ValueError(
                f"Prompt ID must be lowercase alphanumeric + hyphens, "
                f"not starting or ending with a hyphen. Got: '{v}'"
            )
        return v


class PromptRecord(BaseModel):
    """Output model representing a registered prompt.

    Attributes:
        id: Unique prompt identifier.
        purpose: Human-readable description of the prompt's purpose.
        template_variables: All variables found in the Jinja2 template.
        anchor_variables: Subset of variables marked as anchors (fixed during evolution).
        commit_hash: Git commit hash from registration, or None if not committed.
        created_at: Timestamp when the prompt was registered.
        config: Merged GeneConfig with per-prompt overrides applied, or None.
        tools: Tool definitions loaded from tools.json, or None.
        description: Longer description beyond the existing purpose field.
        category_tags: Searchable tags (e.g. ["customer-service", "sales"]).
        artifacts: Bundled artifact config for change detection, or None.
    """

    model_config = {"arbitrary_types_allowed": True}

    id: str
    purpose: str
    template: str | None = None
    template_variables: set[str]
    anchor_variables: set[str]
    commit_hash: str | None = None
    created_at: datetime
    config: GeneConfig | None = None
    tools: list[dict[str, Any]] | None = None
    description: str | None = None
    category_tags: list[str] = Field(default_factory=list)
    artifacts: ArtifactConfig | None = None
    # Phase 31: YAML sidecar data (typed Pydantic models)
    # String annotations to avoid circular import with schemas.py;
    # model_rebuild() is called in schemas.py after both modules load.
    tool_schemas: list["ToolSchemaDefinition"] | None = None
    mocks: list["MockDefinition"] | None = None
    # Phase 33: Persona profiles loaded from personas.yaml sidecar
    personas: list["PersonaProfile"] = Field(default_factory=list)
