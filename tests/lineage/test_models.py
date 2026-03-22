"""Tests for LineageEvent model serialization and defaults."""

from api.lineage.models import LineageEvent


class TestLineageEventDefaults:
    """LineageEvent should have sensible defaults for optional fields."""

    def test_minimal_construction(self):
        """LineageEvent can be constructed with just candidate_id and generation."""
        event = LineageEvent(candidate_id="abc-123", generation=1)
        assert event.candidate_id == "abc-123"
        assert event.generation == 1

    def test_default_values(self):
        """Unset fields should use documented defaults."""
        event = LineageEvent(candidate_id="x", generation=0)
        assert event.parent_ids == []
        assert event.island == 0
        assert event.fitness_score == 0.0
        assert event.rejected is False
        assert event.mutation_type == "rcc"
        assert event.survived is True


class TestLineageEventRoundTrip:
    """LineageEvent should survive model_dump/model_validate cycles."""

    def test_round_trip_preserves_all_fields(self):
        """All field values survive a dump/validate round trip."""
        event = LineageEvent(
            candidate_id="cand-1",
            parent_ids=["p1", "p2"],
            generation=5,
            island=2,
            fitness_score=0.85,
            rejected=True,
            mutation_type="structural",
            survived=False,
        )
        dumped = event.model_dump()
        restored = LineageEvent.model_validate(dumped)
        assert restored == event

    def test_round_trip_minimal(self):
        """Minimal event round-trips correctly."""
        event = LineageEvent(candidate_id="min", generation=0)
        restored = LineageEvent.model_validate(event.model_dump())
        assert restored == event

    def test_dump_produces_json_serializable_dict(self):
        """model_dump() output should be JSON-serializable (no custom types)."""
        import json

        event = LineageEvent(
            candidate_id="json-test",
            parent_ids=["a"],
            generation=3,
        )
        dumped = event.model_dump()
        # Should not raise
        serialized = json.dumps(dumped)
        assert isinstance(serialized, str)


# ===========================================================================
# ENG-04: template field on LineageEvent
# ===========================================================================


class TestLineageEventTemplateField:
    """ENG-04: Verify template field on LineageEvent for candidate tracking."""

    def test_template_defaults_to_none(self):
        """LineageEvent without template kwarg defaults to None."""
        event = LineageEvent(candidate_id="no-template", generation=0)
        assert event.template is None

    def test_template_explicit_none_serializes(self):
        """LineageEvent with template=None serializes and deserializes correctly."""
        event = LineageEvent(
            candidate_id="none-template",
            generation=1,
            template=None,
        )
        dumped = event.model_dump()
        assert dumped["template"] is None
        restored = LineageEvent.model_validate(dumped)
        assert restored.template is None
        assert restored == event

    def test_template_round_trip_with_value(self):
        """LineageEvent with template='some text' round-trips through model_dump/model_validate."""
        template_text = "You are a helpful assistant for {{ business_name }}."
        event = LineageEvent(
            candidate_id="with-template",
            parent_ids=["parent-1"],
            generation=3,
            fitness_score=0.9,
            template=template_text,
        )
        dumped = event.model_dump()
        assert dumped["template"] == template_text
        restored = LineageEvent.model_validate(dumped)
        assert restored.template == template_text
        assert restored == event
