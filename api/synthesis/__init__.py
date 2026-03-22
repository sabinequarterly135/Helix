"""Synthesis sub-package for adversarial synthetic test case generation.

Provides:
- PersonaProfile: Persona profile model for conversation simulation
- SynthesisConfig: Configuration for synthesis runs
- ConversationRecord: Result of a single simulated conversation
- SynthesisResult: Summary of a synthesis run
- PersonasSchema: YAML sidecar schema for persona storage
- SynthesisEngine: Core conversation simulation engine (import from synthesis.engine)
"""

from api.synthesis.models import (
    ConversationRecord,
    PersonaProfile,
    SynthesisConfig,
    SynthesisResult,
)
from api.synthesis.personas import PersonasSchema

__all__ = [
    "ConversationRecord",
    "PersonaProfile",
    "PersonasSchema",
    "SynthesisConfig",
    "SynthesisResult",
]
