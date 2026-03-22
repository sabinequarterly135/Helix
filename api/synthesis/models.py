"""Pydantic models for synthetic test case generation.

Provides:
- PersonaProfile: Defines an adversarial persona for conversation simulation
- SynthesisConfig: Configuration for a synthesis run
- ConversationRecord: Result of a single simulated conversation
- SynthesisResult: Summary of a full synthesis run
"""

from typing import Any

from pydantic import BaseModel, Field


class PersonaProfile(BaseModel):
    """A persona profile for adversarial conversation generation.

    Attributes:
        id: Unique identifier for this persona.
        role: Role description (e.g., "Frustrated customer").
        traits: List of personality traits (e.g., ["impatient", "emotional"]).
        communication_style: How this persona communicates (e.g., "curt, uses slang").
        goal: What this persona is trying to achieve in the conversation.
        edge_cases: Specific edge-case behaviors to probe (optional).
        behavior_criteria: Criteria for scoring conversations with this persona (optional).
        language: ISO 639-1 language code (e.g., "en", "es", "zh"). Defaults to "en".
        channel: Communication channel -- "text" or "voice". Defaults to "text".
    """

    id: str
    role: str
    traits: list[str]
    communication_style: str
    goal: str
    edge_cases: list[str] = Field(default_factory=list)
    behavior_criteria: list[str] = Field(default_factory=list)
    language: str = "en"
    channel: str = "text"


class SynthesisConfig(BaseModel):
    """Configuration for a synthesis run.

    Attributes:
        num_conversations: Number of conversations to generate per persona.
        max_turns: Maximum number of turns per conversation.
        persona_ids: Specific persona IDs to use; None means all personas.
        scenario_context: Optional scenario description injected into persona
            system prompts to guide conversation context.
        review_mode: When True, engine buffers conversations instead of
            auto-persisting. All conversations are returned for frontend review.
    """

    num_conversations: int = 5
    max_turns: int = 10
    persona_ids: list[str] | None = None
    scenario_context: str | None = None
    review_mode: bool = False


class ConversationRecord(BaseModel):
    """Result of a single simulated conversation.

    Attributes:
        persona_id: ID of the persona that drove this conversation.
        chat_history: Full conversation as a list of message dicts.
        variables: Variable values used for template rendering.
        turns: Number of user turns in the conversation.
        score: Evaluation score (negative = failing). None if not scored.
        passed: Whether the conversation passed evaluation. None if not scored.
        persisted_case_id: ID of the persisted test case, if any.
        behavior_criteria: Criteria used for scoring, stored for review endpoint.
    """

    persona_id: str
    chat_history: list[dict[str, Any]]
    variables: dict[str, Any]
    turns: int
    score: float | None = None
    passed: bool | None = None
    persisted_case_id: str | None = None
    behavior_criteria: list[str] | None = None


class SynthesisResult(BaseModel):
    """Summary of a synthesis run.

    Attributes:
        total_conversations: Total conversations generated.
        total_persisted: Number of failing conversations persisted as test cases.
        total_discarded: Number of passing conversations discarded.
        conversations: All conversation records from this run.
    """

    total_conversations: int
    total_persisted: int
    total_discarded: int
    conversations: list[ConversationRecord]
