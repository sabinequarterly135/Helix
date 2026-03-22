"""Tests for WebSocket evolution endpoint protocol.

Uses Starlette's TestClient for synchronous WebSocket testing.
Tests the basic connect/subscribe protocol flow.
"""

from __future__ import annotations

import asyncio
import threading
import time

from starlette.testclient import TestClient

from api.web.app import create_app
from api.web.event_bus import EventBus
from api.web.run_manager import RunManager


def _make_test_client() -> tuple[TestClient, EventBus]:
    """Create a TestClient with RunManager and EventBus set up on app state."""
    app = create_app()
    bus = EventBus()
    app.state.run_manager = RunManager()
    app.state.event_bus = bus
    return TestClient(app), bus


def test_ws_connect_and_receive_connected():
    """WebSocket /ws/evolution/{run_id} connects and sends connected message."""
    client, bus = _make_test_client()
    run_id = "test-run-id"
    bus.create_run(run_id)

    def publish_complete():
        time.sleep(0.1)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(bus.publish(run_id, "evolution_complete", {}))
        loop.close()

    t = threading.Thread(target=publish_complete)
    t.start()

    with client.websocket_connect(f"/ws/evolution/{run_id}") as ws:
        data = ws.receive_json()
        assert data == {"type": "connected", "run_id": "test-run-id"}

        # Send subscribe to proceed through the protocol
        ws.send_json({"type": "subscribe", "last_event_id": 0})

        # Read the completion event so connection closes cleanly
        ev = ws.receive_json()
        assert ev["type"] == "evolution_complete"

    t.join(timeout=5)


def test_ws_disconnect_cleanly():
    """WebSocket connects, receives connected message, and disconnects cleanly."""
    client, bus = _make_test_client()
    run_id = "test-run-id"
    bus.create_run(run_id)

    with client.websocket_connect(f"/ws/evolution/{run_id}") as ws:
        data = ws.receive_json()
        assert data["type"] == "connected"
    # No exception raised -- disconnect is clean (before subscribe)
