"""Unit tests for EventBus publish/subscribe/replay infrastructure."""

from __future__ import annotations

import asyncio


from api.web.event_bus import RING_BUFFER_SIZE, EventBus
from api.web.events import EvolutionEvent


class TestCreateRun:
    """Tests for EventBus.create_run()."""

    async def test_create_run_initializes_counter_buffer_subscribers(self):
        """create_run sets up counter, ring buffer, and subscriber set for a run_id."""
        bus = EventBus()
        bus.create_run("run-1")

        # Internal state should be initialized
        assert bus._counters["run-1"] == 0
        assert len(bus._buffers["run-1"]) == 0
        assert bus._buffers["run-1"].maxlen == RING_BUFFER_SIZE
        assert len(bus._subscribers["run-1"]) == 0


class TestPublish:
    """Tests for EventBus.publish()."""

    async def test_publish_wraps_into_evolution_event_with_monotonic_id(self):
        """publish creates EvolutionEvent with incrementing event_id and pushes to subscribers."""
        bus = EventBus()
        bus.create_run("run-1")
        queue, _ = bus.subscribe("run-1")

        await bus.publish("run-1", "generation_started", {"generation": 0})
        await bus.publish("run-1", "generation_complete", {"generation": 0})

        event1 = queue.get_nowait()
        event2 = queue.get_nowait()

        assert isinstance(event1, EvolutionEvent)
        assert event1.event_id == 1
        assert event1.run_id == "run-1"
        assert event1.type == "generation_started"
        assert event1.data == {"generation": 0}

        assert event2.event_id == 2
        assert event2.type == "generation_complete"

    async def test_two_subscribers_receive_independent_copies(self):
        """Two subscribers to same run_id each receive all published events."""
        bus = EventBus()
        bus.create_run("run-1")
        q1, _ = bus.subscribe("run-1")
        q2, _ = bus.subscribe("run-1")

        await bus.publish("run-1", "migration", {"generation": 1})

        event_q1 = q1.get_nowait()
        event_q2 = q2.get_nowait()

        # Both queues should have the same event
        assert event_q1.event_id == event_q2.event_id == 1
        assert event_q1.type == event_q2.type == "migration"


class TestSubscribeWithReplay:
    """Tests for EventBus.subscribe() with last_event_id replay."""

    async def test_subscribe_with_last_event_id_zero_returns_all_buffered(self):
        """subscribe with last_event_id=0 returns all buffered events as missed."""
        bus = EventBus()
        bus.create_run("run-1")

        # Publish some events before subscribing
        await bus.publish("run-1", "generation_started", {"generation": 0})
        await bus.publish("run-1", "candidate_evaluated", {"generation": 0})
        await bus.publish("run-1", "generation_complete", {"generation": 0})

        queue, missed = bus.subscribe("run-1", last_event_id=0)

        assert len(missed) == 3
        assert missed[0].event_id == 1
        assert missed[1].event_id == 2
        assert missed[2].event_id == 3

    async def test_subscribe_with_last_event_id_filters_correctly(self):
        """subscribe with last_event_id=5 returns only events with event_id > 5."""
        bus = EventBus()
        bus.create_run("run-1")

        # Publish 7 events
        for i in range(7):
            await bus.publish("run-1", "candidate_evaluated", {"index": i})

        queue, missed = bus.subscribe("run-1", last_event_id=5)

        assert len(missed) == 2
        assert missed[0].event_id == 6
        assert missed[1].event_id == 7


class TestUnsubscribe:
    """Tests for EventBus.unsubscribe()."""

    async def test_unsubscribe_removes_queue_from_delivery(self):
        """unsubscribe removes the queue so subsequent publishes do not reach it."""
        bus = EventBus()
        bus.create_run("run-1")
        queue, _ = bus.subscribe("run-1")

        # Unsubscribe
        bus.unsubscribe("run-1", queue)

        # Publish after unsubscribe
        await bus.publish("run-1", "migration", {})

        # Queue should be empty -- event was not delivered
        assert queue.empty()


class TestRingBuffer:
    """Tests for EventBus ring buffer behavior."""

    async def test_ring_buffer_evicts_oldest_when_full(self):
        """Publishing RING_BUFFER_SIZE+1 events evicts the oldest event."""
        bus = EventBus()
        bus.create_run("run-1")

        # Publish RING_BUFFER_SIZE + 1 events (no subscriber to avoid QueueFull)
        for i in range(RING_BUFFER_SIZE + 1):
            await bus.publish("run-1", "candidate_evaluated", {"index": i})

        # Buffer should have exactly RING_BUFFER_SIZE events
        assert len(bus._buffers["run-1"]) == RING_BUFFER_SIZE

        # The oldest event (event_id=1) should have been evicted
        # First event in buffer should be event_id=2
        first_in_buffer = bus._buffers["run-1"][0]
        assert first_in_buffer.event_id == 2

        # Last event should be event_id=RING_BUFFER_SIZE+1
        last_in_buffer = bus._buffers["run-1"][-1]
        assert last_in_buffer.event_id == RING_BUFFER_SIZE + 1


class TestDeadQueueCleanup:
    """Tests for automatic removal of full subscriber queues."""

    async def test_publish_to_full_queue_removes_subscriber(self):
        """Publishing to a QueueFull subscriber removes it from the subscriber set."""
        bus = EventBus()
        bus.create_run("run-1")

        # Create a very small queue that will fill up
        small_queue = asyncio.Queue(maxsize=1)
        bus._subscribers["run-1"].add(small_queue)

        # Fill the queue
        await bus.publish("run-1", "generation_started", {})
        # Queue is now full (maxsize=1)

        # This publish should cause QueueFull on small_queue and remove it
        await bus.publish("run-1", "generation_complete", {})

        # small_queue should have been removed from subscribers
        assert small_queue not in bus._subscribers["run-1"]


class TestCleanupRun:
    """Tests for EventBus.cleanup_run()."""

    async def test_cleanup_run_removes_subscribers(self):
        """cleanup_run removes subscriber set for the run."""
        bus = EventBus()
        bus.create_run("run-1")
        bus.subscribe("run-1")

        bus.cleanup_run("run-1")

        # Subscribers should be gone
        assert "run-1" not in bus._subscribers

        # Buffer should still exist (for late reconnectors per design)
        assert "run-1" in bus._buffers
