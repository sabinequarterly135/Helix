"""Tests for LineageCollector record/export/import."""

from api.lineage.collector import LineageCollector
from api.lineage.models import LineageEvent


class TestLineageCollectorRecord:
    """LineageCollector.record() accumulates events."""

    def test_record_appends_event(self):
        collector = LineageCollector()
        event = LineageEvent(candidate_id="c1", generation=0)
        collector.record(event)
        assert len(collector.events) == 1
        assert collector.events[0].candidate_id == "c1"

    def test_record_multiple_events(self):
        collector = LineageCollector()
        for i in range(5):
            collector.record(LineageEvent(candidate_id=f"c{i}", generation=i))
        assert len(collector.events) == 5


class TestLineageCollectorExportImport:
    """LineageCollector serialization round-trips."""

    def test_empty_collector_returns_empty_list(self):
        collector = LineageCollector()
        assert collector.to_dict_list() == []

    def test_to_dict_list_returns_dicts(self):
        collector = LineageCollector()
        collector.record(LineageEvent(candidate_id="c1", generation=0))
        result = collector.to_dict_list()
        assert isinstance(result, list)
        assert isinstance(result[0], dict)
        assert result[0]["candidate_id"] == "c1"

    def test_from_dict_list_reconstitutes_events(self):
        collector = LineageCollector()
        collector.record(
            LineageEvent(
                candidate_id="c1",
                parent_ids=["p1"],
                generation=2,
                island=1,
                fitness_score=0.9,
                rejected=False,
                mutation_type="structural",
                survived=True,
            )
        )
        data = collector.to_dict_list()

        new_collector = LineageCollector()
        new_collector.from_dict_list(data)
        assert len(new_collector.events) == 1
        assert new_collector.events[0].candidate_id == "c1"
        assert new_collector.events[0].mutation_type == "structural"

    def test_round_trip_multiple_events(self):
        collector = LineageCollector()
        for i in range(3):
            collector.record(LineageEvent(candidate_id=f"c{i}", generation=i, island=i % 2))
        data = collector.to_dict_list()

        restored = LineageCollector()
        restored.from_dict_list(data)
        assert len(restored.events) == 3
        for i in range(3):
            assert restored.events[i].candidate_id == f"c{i}"


class TestLineageCollectorEventsProperty:
    """events property returns a copy (read-only access)."""

    def test_events_returns_list_copy(self):
        collector = LineageCollector()
        collector.record(LineageEvent(candidate_id="c1", generation=0))
        events = collector.events
        events.clear()  # Mutate the returned list
        assert len(collector.events) == 1  # Original unaffected
