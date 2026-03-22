"""Prompt registry sub-package.

Provides the PromptRegistry service for registering, loading, and managing prompts
with their full configuration (template, variables, tools, per-prompt config).
"""

from api.registry.models import (
    ArtifactConfig,
    PromptRecord,
    PromptRegistration,
    VariableDefinition,
)
from api.registry.sections import PromptSection, SectionParser
from api.registry.service import PromptRegistry

__all__ = [
    "ArtifactConfig",
    "PromptRecord",
    "PromptRegistration",
    "PromptRegistry",
    "PromptSection",
    "SectionParser",
    "VariableDefinition",
]
