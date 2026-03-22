"""Unit tests for EvolutionEvent model and EVENT_TYPES constant."""

from __future__ import annotations

from datetime import datetime, timezone

from api.web.events import EVENT_TYPES, EvolutionEvent


class TestEvolutionEventModel:
    """Tests for EvolutionEvent Pydantic model."""

    def test_construct_with_all_six_event_types(self):
        """EvolutionEvent can be constructed with each of the 6 event types."""
        expected_types = {
            "generation_started",
            "candidate_evaluated",
            "migration",
            "island_reset",
            "generation_complete",
            "evolution_complete",
        }
        for event_type in expected_types:
            event = EvolutionEvent(
                event_id=1,
                run_id="run-abc",
                type=event_type,
            )
            assert event.type == event_type

    def test_model_dump_produces_json_serializable_dict(self):
        """model_dump() returns dict with event_id, run_id, type, timestamp, data."""
        event = EvolutionEvent(
            event_id=42,
            run_id="run-xyz",
            type="generation_started",
            data={"generation": 1, "island_count": 4},
        )
        dumped = event.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["event_id"] == 42
        assert dumped["run_id"] == "run-xyz"
        assert dumped["type"] == "generation_started"
        assert "timestamp" in dumped
        assert dumped["data"] == {"generation": 1, "island_count": 4}

        # Verify JSON-serializable (no datetime objects, etc.)
        import json

        json_str = json.dumps(dumped)
        assert isinstance(json_str, str)

    def test_timestamp_auto_generated_utc_iso_format(self):
        """timestamp is auto-generated as UTC ISO format string when not provided."""
        before = datetime.now(timezone.utc)
        event = EvolutionEvent(
            event_id=1,
            run_id="run-abc",
            type="generation_started",
        )
        after = datetime.now(timezone.utc)

        # timestamp should be a string
        assert isinstance(event.timestamp, str)

        # Parse it back and verify it's within our time window
        parsed = datetime.fromisoformat(event.timestamp)
        assert parsed >= before.replace(microsecond=0) - __import__("datetime").timedelta(seconds=1)
        assert parsed <= after + __import__("datetime").timedelta(seconds=1)

    def test_data_defaults_to_empty_dict(self):
        """data field defaults to empty dict when not provided."""
        event = EvolutionEvent(
            event_id=1,
            run_id="run-abc",
            type="generation_started",
        )
        assert event.data == {}
        assert isinstance(event.data, dict)

    def test_data_default_is_independent_per_instance(self):
        """Each event gets its own default dict (no shared mutable default)."""
        event1 = EvolutionEvent(event_id=1, run_id="r1", type="migration")
        event2 = EvolutionEvent(event_id=2, run_id="r2", type="migration")
        event1.data["key"] = "value"
        assert "key" not in event2.data

    def test_event_id_is_positive_integer(self):
        """event_id is a positive integer."""
        event = EvolutionEvent(
            event_id=1,
            run_id="run-abc",
            type="generation_started",
        )
        assert isinstance(event.event_id, int)
        assert event.event_id > 0

    def test_explicit_timestamp_is_preserved(self):
        """When timestamp is provided explicitly, it is not overridden."""
        ts = "2026-01-01T00:00:00+00:00"
        event = EvolutionEvent(
            event_id=1,
            run_id="run-abc",
            type="generation_started",
            timestamp=ts,
        )
        assert event.timestamp == ts


class TestEventTypes:
    """Tests for EVENT_TYPES constant set."""

    def test_event_types_contains_all_six_types(self):
        """EVENT_TYPES set contains exactly the 6 expected event types."""
        expected = {
            "generation_started",
            "candidate_evaluated",
            "migration",
            "island_reset",
            "generation_complete",
            "evolution_complete",
        }
        assert EVENT_TYPES == expected

    def test_event_types_is_a_set(self):
        """EVENT_TYPES is a set (not list or tuple)."""
        assert isinstance(EVENT_TYPES, set)

    def test_event_types_has_six_elements(self):
        """EVENT_TYPES has exactly 6 elements."""
        assert len(EVENT_TYPES) == 6
