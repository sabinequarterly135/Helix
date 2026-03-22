"""Integration tests for WebSocket streaming with EventBus.

Tests the full subscribe-replay-stream protocol:
1. Client connects, receives connected message
2. Client sends subscribe with last_event_id
3. Server replays missed events from ring buffer
4. Server streams live events until evolution_complete
"""

from __future__ import annotations

import asyncio
import threading
import time

from starlette.testclient import TestClient

from api.web.app import create_app
from api.web.event_bus import EventBus
from api.web.run_manager import RunManager


def _make_streaming_client(
    event_bus: EventBus | None = None,
) -> tuple[TestClient, EventBus]:
    """Build a TestClient with RunManager and EventBus on app.state.

    Args:
        event_bus: Optional pre-configured EventBus. Creates a new one if None.

    Returns:
        Tuple of (TestClient, EventBus) for test access to both.
    """
    app = create_app()
    bus = event_bus or EventBus()
    app.state.run_manager = RunManager()
    app.state.event_bus = bus
    return TestClient(app), bus


def test_subscribe_and_receive_live_event():
    """Client connects, subscribes with last_event_id=0, receives live event."""
    client, bus = _make_streaming_client()
    run_id = "run-live-1"
    bus.create_run(run_id)

    def publish_events():
        """Publish events from a background thread after a short delay."""
        time.sleep(0.1)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(bus.publish(run_id, "generation_started", {"gen": 1}))
        loop.run_until_complete(bus.publish(run_id, "evolution_complete", {"best": 0.9}))
        loop.close()

    t = threading.Thread(target=publish_events)
    t.start()

    with client.websocket_connect(f"/ws/evolution/{run_id}") as ws:
        # 1. Receive connected message
        data = ws.receive_json()
        assert data == {"type": "connected", "run_id": run_id}

        # 2. Send subscribe
        ws.send_json({"type": "subscribe", "last_event_id": 0})

        # 3. Receive live events
        ev1 = ws.receive_json()
        assert ev1["type"] == "generation_started"
        assert ev1["data"] == {"gen": 1}

        ev2 = ws.receive_json()
        assert ev2["type"] == "evolution_complete"
        assert ev2["data"] == {"best": 0.9}

    t.join(timeout=5)


def test_replay_missed_events_on_reconnect():
    """Client reconnects with last_event_id=2, receives only events 3+ from buffer."""
    client, bus = _make_streaming_client()
    run_id = "run-replay-1"
    bus.create_run(run_id)

    # Pre-populate ring buffer with events
    loop = asyncio.new_event_loop()
    for i in range(1, 6):
        loop.run_until_complete(bus.publish(run_id, "generation_started", {"gen": i}))
    loop.close()

    def publish_complete():
        """Send evolution_complete so the connection can close."""
        time.sleep(0.2)
        loop2 = asyncio.new_event_loop()
        loop2.run_until_complete(bus.publish(run_id, "evolution_complete", {"done": True}))
        loop2.close()

    t = threading.Thread(target=publish_complete)
    t.start()

    with client.websocket_connect(f"/ws/evolution/{run_id}") as ws:
        # 1. Connected
        data = ws.receive_json()
        assert data["type"] == "connected"

        # 2. Subscribe with last_event_id=2 (missed events 3, 4, 5)
        ws.send_json({"type": "subscribe", "last_event_id": 2})

        # 3. Receive replayed events (3, 4, 5)
        replayed = []
        for _ in range(3):
            ev = ws.receive_json()
            replayed.append(ev)

        assert [e["event_id"] for e in replayed] == [3, 4, 5]
        assert all(e["type"] == "generation_started" for e in replayed)

        # 4. Receive live evolution_complete
        ev_complete = ws.receive_json()
        assert ev_complete["type"] == "evolution_complete"

    t.join(timeout=5)


def test_evolution_complete_closes_connection():
    """Connection closes cleanly after receiving evolution_complete."""
    client, bus = _make_streaming_client()
    run_id = "run-close-1"
    bus.create_run(run_id)

    def publish_complete():
        time.sleep(0.1)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(bus.publish(run_id, "evolution_complete", {"status": "done"}))
        loop.close()

    t = threading.Thread(target=publish_complete)
    t.start()

    with client.websocket_connect(f"/ws/evolution/{run_id}") as ws:
        data = ws.receive_json()
        assert data["type"] == "connected"

        ws.send_json({"type": "subscribe", "last_event_id": 0})

        ev = ws.receive_json()
        assert ev["type"] == "evolution_complete"
        # Connection should close cleanly after this -- the context manager exits

    t.join(timeout=5)


def test_multiple_clients_receive_all_events():
    """Two clients subscribing to same run_id both receive all events independently."""
    client, bus = _make_streaming_client()
    run_id = "run-multi-1"
    bus.create_run(run_id)

    results = {"client1": [], "client2": []}

    def publish_events():
        time.sleep(0.2)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(bus.publish(run_id, "generation_started", {"gen": 1}))
        loop.run_until_complete(bus.publish(run_id, "evolution_complete", {"done": True}))
        loop.close()

    def run_client(client_name: str):
        with client.websocket_connect(f"/ws/evolution/{run_id}") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"

            ws.send_json({"type": "subscribe", "last_event_id": 0})

            ev1 = ws.receive_json()
            results[client_name].append(ev1)

            ev2 = ws.receive_json()
            results[client_name].append(ev2)

    t_pub = threading.Thread(target=publish_events)
    t1 = threading.Thread(target=run_client, args=("client1",))
    t2 = threading.Thread(target=run_client, args=("client2",))

    t1.start()
    t2.start()
    t_pub.start()

    t_pub.join(timeout=5)
    t1.join(timeout=5)
    t2.join(timeout=5)

    # Both clients received the same events
    assert len(results["client1"]) == 2
    assert len(results["client2"]) == 2
    assert results["client1"][0]["type"] == "generation_started"
    assert results["client1"][1]["type"] == "evolution_complete"
    assert results["client2"][0]["type"] == "generation_started"
    assert results["client2"][1]["type"] == "evolution_complete"


def test_disconnect_unsubscribes_queue():
    """After client disconnects, its queue is unsubscribed from EventBus."""
    client, bus = _make_streaming_client()
    run_id = "run-unsub-1"
    bus.create_run(run_id)

    with client.websocket_connect(f"/ws/evolution/{run_id}") as ws:
        data = ws.receive_json()
        assert data["type"] == "connected"

        ws.send_json({"type": "subscribe", "last_event_id": 0})

        # Wait for the server-side handler to process the subscribe.
        # The ASGI handler runs in a background thread, so send_json
        # returns before subscribe() is called. Give it time.
        time.sleep(0.2)
        assert len(bus._subscribers.get(run_id, set())) == 1

    # After disconnect, subscriber should be removed.
    # Give the server-side finally block time to run unsubscribe.
    time.sleep(0.3)
    assert len(bus._subscribers.get(run_id, set())) == 0


def test_invalid_subscribe_defaults_last_event_id_to_zero():
    """Client that sends subscribe without last_event_id defaults to 0."""
    client, bus = _make_streaming_client()
    run_id = "run-default-1"
    bus.create_run(run_id)

    # Pre-populate with events
    loop = asyncio.new_event_loop()
    loop.run_until_complete(bus.publish(run_id, "generation_started", {"gen": 1}))
    loop.close()

    def publish_complete():
        time.sleep(0.2)
        loop2 = asyncio.new_event_loop()
        loop2.run_until_complete(bus.publish(run_id, "evolution_complete", {"done": True}))
        loop2.close()

    t = threading.Thread(target=publish_complete)
    t.start()

    with client.websocket_connect(f"/ws/evolution/{run_id}") as ws:
        data = ws.receive_json()
        assert data["type"] == "connected"

        # Send subscribe WITHOUT last_event_id
        ws.send_json({"type": "subscribe"})

        # Should receive all buffered events (default last_event_id=0)
        ev1 = ws.receive_json()
        assert ev1["type"] == "generation_started"
        assert ev1["event_id"] == 1

        ev2 = ws.receive_json()
        assert ev2["type"] == "evolution_complete"

    t.join(timeout=5)
