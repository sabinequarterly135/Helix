"""Evolution event model for streaming infrastructure.

Defines the EvolutionEvent Pydantic model representing a single
streaming event from an evolution run, and the EVENT_TYPES constant
set enumerating all valid event type strings.

Exports:
    EvolutionEvent: Pydantic model for a single evolution streaming event.
    EVENT_TYPES: Set of all valid event type strings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class EvolutionEvent(BaseModel):
    """A single streaming event from an evolution run.

    Attributes:
        event_id: Monotonically increasing integer assigned by EventBus.
        run_id: Unique identifier for the evolution run.
        type: Event type string (one of EVENT_TYPES).
        timestamp: UTC ISO-format timestamp, auto-generated if not provided.
        data: Arbitrary event payload dict, defaults to empty.
    """

    event_id: int
    run_id: str
    type: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    data: dict[str, Any] = Field(default_factory=dict)


# All valid event types emitted during an evolution run.
EVENT_TYPES: set[str] = {
    "generation_started",
    "candidate_evaluated",
    "migration",
    "island_reset",
    "generation_complete",
    "evolution_complete",
}

# All valid event types emitted during a synthesis run.
SYNTHESIS_EVENT_TYPES: set[str] = {
    "synthesis_started",
    "conversation_started",
    "conversation_scored",
    "conversation_persisted",
    "synthesis_complete",
    "synthesis_failed",
}
