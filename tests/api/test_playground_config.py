"""Tests for Playground Config API endpoints (GET/PUT).

Covers:
- GET /api/prompts/{id}/playground-config returns defaults (None) when no row exists
- PUT /api/prompts/{id}/playground-config creates config with turn_limit and budget
- PUT then GET returns consistent values
- PUT twice with different values updates correctly
- PUT with partial updates (only turn_limit or only budget) persists both
"""

from __future__ import annotations

import httpx


PROMPT_ID = "test-pgcfg"


async def _register_prompt(
    client: httpx.AsyncClient,
    prompt_id: str = PROMPT_ID,
) -> httpx.Response:
    """POST a new prompt and return the response."""
    return await client.post(
        "/api/prompts/",
        json={
            "id": prompt_id,
            "purpose": "Test prompt for playground config",
            "template": "You are a helpful assistant.",
        },
    )


class TestGetPlaygroundConfig:
    """GET /api/prompts/{prompt_id}/playground-config."""

    async def test_get_playground_config_defaults(self, client: httpx.AsyncClient):
        """Returns turn_limit=None and budget=None when no PromptConfig row exists."""
        await _register_prompt(client)
        resp = await client.get(f"/api/prompts/{PROMPT_ID}/playground-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["turn_limit"] is None
        assert data["budget"] is None


class TestPutPlaygroundConfig:
    """PUT /api/prompts/{prompt_id}/playground-config."""

    async def test_put_playground_config_creates(self, client: httpx.AsyncClient):
        """PUT with turn_limit=10 and budget=5.0 creates config row."""
        await _register_prompt(client)
        resp = await client.put(
            f"/api/prompts/{PROMPT_ID}/playground-config",
            json={"turn_limit": 10, "budget": 5.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["turn_limit"] == 10
        assert data["budget"] == 5.0

    async def test_put_then_get_playground_config(self, client: httpx.AsyncClient):
        """PUT then GET returns same values."""
        await _register_prompt(client)
        await client.put(
            f"/api/prompts/{PROMPT_ID}/playground-config",
            json={"turn_limit": 15, "budget": 3.0},
        )

        resp = await client.get(f"/api/prompts/{PROMPT_ID}/playground-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["turn_limit"] == 15
        assert data["budget"] == 3.0

    async def test_put_playground_config_updates(self, client: httpx.AsyncClient):
        """PUT twice with different values, second one sticks."""
        await _register_prompt(client)
        await client.put(
            f"/api/prompts/{PROMPT_ID}/playground-config",
            json={"turn_limit": 10, "budget": 5.0},
        )

        resp = await client.put(
            f"/api/prompts/{PROMPT_ID}/playground-config",
            json={"turn_limit": 20, "budget": 10.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["turn_limit"] == 20
        assert data["budget"] == 10.0

    async def test_put_playground_config_partial_update(self, client: httpx.AsyncClient):
        """PUT with only turn_limit, then PUT with only budget, both persist."""
        await _register_prompt(client)
        # Set turn_limit only
        await client.put(
            f"/api/prompts/{PROMPT_ID}/playground-config",
            json={"turn_limit": 8},
        )

        # Set budget only
        resp = await client.put(
            f"/api/prompts/{PROMPT_ID}/playground-config",
            json={"budget": 2.5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["turn_limit"] == 8
        assert data["budget"] == 2.5
