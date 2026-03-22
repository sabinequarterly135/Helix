"""LineageCollector: accumulates lineage events during evolution.

Provides serialization to/from dict lists for persistence
in EvolutionRun.extra_metadata.
"""

from __future__ import annotations

from api.lineage.models import LineageEvent


class LineageCollector:
    """Accumulates LineageEvent instances and serializes them for storage.

    Usage:
        collector = LineageCollector()
        collector.record(LineageEvent(candidate_id="x", generation=0))
        data = collector.to_dict_list()  # persist this
        collector.from_dict_list(data)   # restore later
    """

    def __init__(self) -> None:
        self._events: list[LineageEvent] = []

    def record(self, event: LineageEvent) -> None:
        """Append a lineage event to the internal list."""
        self._events.append(event)

    def to_dict_list(self) -> list[dict]:
        """Serialize all events to a list of dicts (JSON-safe).

        Uses a snapshot copy of _events to avoid inconsistent reads when
        concurrent asyncio tasks append to _events during iteration.
        """
        events = list(self._events)
        return [e.model_dump() for e in events]

    def from_dict_list(self, data: list[dict]) -> None:
        """Reconstitute events from a list of dicts and append to internal list."""
        for d in data:
            self._events.append(LineageEvent.model_validate(d))

    @property
    def events(self) -> list[LineageEvent]:
        """Return a copy of the internal events list (read-only access)."""
        return list(self._events)
