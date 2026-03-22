"""Tests for Format Guide CRUD API endpoints.

Covers:
- GET /api/prompts/{id}/format-guides returns all format guides (empty initially)
- PUT /api/prompts/{id}/format-guides/{tool_name} creates/updates a format guide
- DELETE /api/prompts/{id}/format-guides/{tool_name} deletes a format guide
- POST /api/prompts/{id}/format-guides/generate-sample rejects when not in LLM mode
- Validation: invalid JSON rejected, empty examples rejected
"""

from __future__ import annotations

import httpx


PROMPT_ID = "test-fmt"


async def _register_prompt(
    client: httpx.AsyncClient,
    prompt_id: str = PROMPT_ID,
) -> httpx.Response:
    """POST a new prompt and return the response."""
    return await client.post(
        "/api/prompts/",
        json={
            "id": prompt_id,
            "purpose": "Test prompt for format guides",
            "template": "You are a helpful assistant.",
        },
    )


class TestListFormatGuides:
    """GET /api/prompts/{prompt_id}/format-guides."""

    async def test_list_format_guides_empty(self, client: httpx.AsyncClient):
        """Returns empty list when no format guides exist."""
        await _register_prompt(client)
        resp = await client.get(f"/api/prompts/{PROMPT_ID}/format-guides")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_format_guides_returns_created(self, client: httpx.AsyncClient):
        """After creating 2 guides, GET returns both."""
        await _register_prompt(client)
        # Create two format guides
        await client.put(
            f"/api/prompts/{PROMPT_ID}/format-guides/tool_a",
            json=['{"key": "val1"}'],
        )
        await client.put(
            f"/api/prompts/{PROMPT_ID}/format-guides/tool_b",
            json=['{"key": "val2"}'],
        )

        resp = await client.get(f"/api/prompts/{PROMPT_ID}/format-guides")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        tool_names = {g["tool_name"] for g in data}
        assert tool_names == {"tool_a", "tool_b"}


class TestUpsertFormatGuide:
    """PUT /api/prompts/{prompt_id}/format-guides/{tool_name}."""

    async def test_upsert_format_guide_creates(self, client: httpx.AsyncClient):
        """PUT with valid JSON examples creates a new format guide."""
        await _register_prompt(client)
        resp = await client.put(
            f"/api/prompts/{PROMPT_ID}/format-guides/my_tool",
            json=['{"action": "transfer", "target": "agent"}'],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["prompt_id"] == PROMPT_ID
        assert data["tool_name"] == "my_tool"
        assert len(data["examples"]) == 1
        assert "transfer" in data["examples"][0]

    async def test_upsert_format_guide_updates(self, client: httpx.AsyncClient):
        """PUT same prompt_id+tool_name with different examples updates existing row."""
        await _register_prompt(client)
        # Create initial
        await client.put(
            f"/api/prompts/{PROMPT_ID}/format-guides/my_tool",
            json=['{"v": 1}'],
        )

        # Update with new examples
        resp = await client.put(
            f"/api/prompts/{PROMPT_ID}/format-guides/my_tool",
            json=['{"v": 2}', '{"v": 3}'],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["examples"]) == 2
        assert '{"v": 2}' in data["examples"]
        assert '{"v": 3}' in data["examples"]

    async def test_upsert_format_guide_invalid_json(self, client: httpx.AsyncClient):
        """PUT with non-JSON string in examples returns 400."""
        await _register_prompt(client)
        resp = await client.put(
            f"/api/prompts/{PROMPT_ID}/format-guides/my_tool",
            json=["not valid json"],
        )
        assert resp.status_code == 400
        assert "not valid JSON" in resp.json()["detail"]

    async def test_upsert_format_guide_empty_examples(self, client: httpx.AsyncClient):
        """PUT with empty examples list returns 400."""
        await _register_prompt(client)
        resp = await client.put(
            f"/api/prompts/{PROMPT_ID}/format-guides/my_tool",
            json=[],
        )
        assert resp.status_code == 400


class TestDeleteFormatGuide:
    """DELETE /api/prompts/{prompt_id}/format-guides/{tool_name}."""

    async def test_delete_format_guide(self, client: httpx.AsyncClient):
        """DELETE existing format guide returns {deleted: true}."""
        await _register_prompt(client)
        # Create first
        await client.put(
            f"/api/prompts/{PROMPT_ID}/format-guides/my_tool",
            json=['{"key": "val"}'],
        )

        # Delete
        resp = await client.delete(f"/api/prompts/{PROMPT_ID}/format-guides/my_tool")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify it's gone
        list_resp = await client.get(f"/api/prompts/{PROMPT_ID}/format-guides")
        assert list_resp.json() == []

    async def test_delete_format_guide_not_found(self, client: httpx.AsyncClient):
        """DELETE nonexistent format guide returns 404."""
        await _register_prompt(client)
        resp = await client.delete(f"/api/prompts/{PROMPT_ID}/format-guides/nonexistent")
        assert resp.status_code == 404


class TestGenerateSample:
    """POST /api/prompts/{prompt_id}/format-guides/generate-sample."""

    async def test_generate_sample_no_llm_config(self, client: httpx.AsyncClient):
        """POST generate-sample without tool_mocker_mode=llm returns 400."""
        await _register_prompt(client)
        resp = await client.post(
            f"/api/prompts/{PROMPT_ID}/format-guides/generate-sample",
            json={"tool_name": "my_tool", "scenario_type": "success"},
        )
        assert resp.status_code == 400
        assert "llm" in resp.json()["detail"].lower()
