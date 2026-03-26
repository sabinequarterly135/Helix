"""Tests for Playground Chat SSE endpoint.

Covers:
- POST /api/prompts/{id}/chat returns SSE stream with token + done events (mocked LLM)
- POST /api/prompts/nonexistent/chat returns 404
- POST /api/prompts/{id}/chat with turn limit exceeded returns limit_reached event
- POST /api/prompts/{id}/chat renders template variables into system message
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx


PROMPT_ID = "test-chat"


async def _register_prompt(
    client: httpx.AsyncClient,
    prompt_id: str = PROMPT_ID,
    template: str = "You are a helpful assistant.",
) -> httpx.Response:
    """POST a new prompt and return the response."""
    return await client.post(
        "/api/prompts/",
        json={
            "id": prompt_id,
            "purpose": "Test prompt for playground chat",
            "template": template,
        },
    )


def _make_chunk(content: str | None = None, finish_reason: str | None = None, usage=None):
    """Build a mock streaming chunk with the structure expected by _sse_generator."""
    delta = SimpleNamespace(content=content)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(
        choices=[choice] if content is not None or finish_reason is not None else [],
        usage=usage,
    )


def _make_usage(prompt_tokens: int = 10, completion_tokens: int = 5):
    """Build a mock usage object."""
    return SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


async def _mock_stream(*chunks):
    """Create an async iterable that yields the given chunks."""
    for chunk in chunks:
        yield chunk


def _build_mock_provider(chunks):
    """Build a mock provider whose _client.chat.completions.create returns chunks."""
    mock_provider = AsyncMock()
    mock_provider._client.chat.completions.create = AsyncMock(
        return_value=_mock_stream(*chunks)
    )
    mock_provider.close = AsyncMock()
    mock_provider._normalize_model = lambda model: model
    return mock_provider


def _parse_sse_events(text: str) -> list[dict]:
    """Parse SSE text into a list of {event, data} dicts."""
    events = []
    current_event = None
    current_data = None

    for line in text.split("\n"):
        if line.startswith("event: "):
            current_event = line[len("event: "):]
        elif line.startswith("data: "):
            current_data = line[len("data: "):]
        elif line == "" and current_event is not None:
            events.append({
                "event": current_event,
                "data": json.loads(current_data) if current_data else None,
            })
            current_event = None
            current_data = None

    return events


class TestChatStream:
    """POST /api/prompts/{prompt_id}/chat."""

    async def test_chat_returns_sse_stream(self, client: httpx.AsyncClient):
        """POST with mocked provider returns SSE token events followed by done event."""
        await _register_prompt(client)

        chunks = [
            _make_chunk(content="Hello"),
            _make_chunk(content=" world"),
            _make_chunk(content=None, finish_reason="stop"),
            _make_chunk(usage=_make_usage(10, 5)),
        ]
        mock_provider = _build_mock_provider(chunks)

        with patch(
            "api.web.routers.playground.create_provider",
            return_value=mock_provider,
        ):
            resp = await client.post(
                f"/api/prompts/{PROMPT_ID}/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse_events(resp.text)
        event_names = [e["event"] for e in events]
        assert "token" in event_names
        assert "done" in event_names

        # Verify token content
        token_events = [e for e in events if e["event"] == "token"]
        combined = "".join(e["data"]["content"] for e in token_events)
        assert combined == "Hello world"

        # Verify done event has expected fields
        done_event = next(e for e in events if e["event"] == "done")
        assert "input_tokens" in done_event["data"]
        assert "output_tokens" in done_event["data"]
        assert "model" in done_event["data"]
        assert "finish_reason" in done_event["data"]

    async def test_chat_prompt_not_found(self, client: httpx.AsyncClient):
        """POST /api/prompts/nonexistent/chat returns 404."""
        resp = await client.post(
            "/api/prompts/nonexistent/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 404

    async def test_chat_turn_limit_exceeded(self, client: httpx.AsyncClient):
        """POST with more user messages than DB turn_limit returns limit_reached event."""
        await _register_prompt(client)

        # Set turn_limit=2 via playground config
        await client.put(
            f"/api/prompts/{PROMPT_ID}/playground-config",
            json={"turn_limit": 2},
        )

        # Send 3 user messages (exceeds limit of 2)
        resp = await client.post(
            f"/api/prompts/{PROMPT_ID}/chat",
            json={
                "messages": [
                    {"role": "user", "content": "msg1"},
                    {"role": "assistant", "content": "reply1"},
                    {"role": "user", "content": "msg2"},
                    {"role": "assistant", "content": "reply2"},
                    {"role": "user", "content": "msg3"},
                ],
            },
        )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse_events(resp.text)
        assert len(events) >= 1
        assert events[0]["event"] == "limit_reached"
        assert events[0]["data"]["reason"] == "turn_limit"
        assert events[0]["data"]["turns_used"] == 3
        assert events[0]["data"]["turn_limit"] == 2

    async def test_chat_renders_template_variables(self, client: httpx.AsyncClient):
        """POST with variables renders them into the system message."""
        await _register_prompt(
            client,
            template="You are an assistant for {{ name }}. Help them with {{ topic }}.",
        )

        captured_messages = []

        chunks = [
            _make_chunk(content="Sure!"),
            _make_chunk(content=None, finish_reason="stop"),
            _make_chunk(usage=_make_usage(10, 3)),
        ]
        mock_provider = _build_mock_provider(chunks)

        # Capture messages passed to the LLM
        original_create = mock_provider._client.chat.completions.create

        async def capturing_create(*args, **kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return original_create.return_value

        mock_provider._client.chat.completions.create = AsyncMock(
            side_effect=capturing_create
        )

        with patch(
            "api.web.routers.playground.create_provider",
            return_value=mock_provider,
        ):
            resp = await client.post(
                f"/api/prompts/{PROMPT_ID}/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "variables": {"name": "Alice", "topic": "cooking"},
                },
            )

        assert resp.status_code == 200

        # Verify the system message was rendered with variables
        assert len(captured_messages) >= 1
        system_msg = captured_messages[0]
        assert system_msg["role"] == "system"
        assert "Alice" in system_msg["content"]
        assert "cooking" in system_msg["content"]
