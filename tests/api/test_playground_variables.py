"""Tests for Playground Variables API endpoints (DB-backed persistence).

Covers:
- GET /api/prompts/{id}/variables returns all saved variable values from DB
- PUT /api/prompts/{id}/variables saves variable values to DB (upsert)
- PUT /api/prompts/{id}/variables with new variables creates rows, existing updates rows
- GET /api/prompts/{id}/variables returns empty dict when no variables saved
"""

from __future__ import annotations

import pytest

from api.storage.database import Database


PROMPT_ID = "test-prompt"


@pytest.fixture
async def db_session(tmp_path):
    """Create an in-memory SQLite database with all tables and yield a session."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test_pgvars.db'}"
    database = Database(db_url)
    await database.create_tables()
    session = await database.get_session()
    yield session
    await session.close()
    await database.close()


@pytest.fixture
def app_with_db(app, db_session):
    """Override get_db_session to use the test DB session."""
    from api.web.deps import get_db_session

    async def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    return app


@pytest.fixture
async def client_db(app_with_db):
    """Async HTTP client wired to the app with DB session.

    Automatically registers the test prompt in the DB before yielding.
    """
    import httpx

    transport = httpx.ASGITransport(app=app_with_db)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # Register the test prompt via API (DB-backed)
        await c.post(
            "/api/prompts/",
            json={
                "id": PROMPT_ID,
                "purpose": "Test prompt for playground variables",
                "template": "You are a helpful assistant with {{ name }}.",
            },
        )
        yield c


class TestGetVariables:
    """GET /api/prompts/{prompt_id}/variables."""

    async def test_returns_empty_dict_when_no_variables(self, client_db):
        """Returns empty variables dict when no variables saved."""
        resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/variables")
        assert resp.status_code == 200
        data = resp.json()
        assert data["prompt_id"] == PROMPT_ID
        assert data["variables"] == {}

    async def test_returns_saved_variables(self, client_db):
        """Returns saved variable values after they are PUT."""
        # Save variables
        await client_db.put(
            f"/api/prompts/{PROMPT_ID}/variables",
            json={"variables": {"name": "Alice", "greeting": "Hello"}},
        )

        # Get variables
        resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/variables")
        assert resp.status_code == 200
        data = resp.json()
        assert data["variables"]["name"] == "Alice"
        assert data["variables"]["greeting"] == "Hello"


class TestPutVariables:
    """PUT /api/prompts/{prompt_id}/variables."""

    async def test_saves_variables(self, client_db):
        """Saves variable values to DB."""
        resp = await client_db.put(
            f"/api/prompts/{PROMPT_ID}/variables",
            json={"variables": {"name": "Bob"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["variables"]["name"] == "Bob"

    async def test_upsert_creates_and_updates(self, client_db):
        """Creates new rows for new variables, updates existing rows."""
        # Create initial
        await client_db.put(
            f"/api/prompts/{PROMPT_ID}/variables",
            json={"variables": {"name": "Alice", "color": "blue"}},
        )

        # Upsert: update name, add new var, color stays
        resp = await client_db.put(
            f"/api/prompts/{PROMPT_ID}/variables",
            json={"variables": {"name": "Bob", "age": "30"}},
        )
        assert resp.status_code == 200

        # Verify the current state
        get_resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/variables")
        data = get_resp.json()
        assert data["variables"]["name"] == "Bob"  # updated
        assert data["variables"]["age"] == "30"  # new
        assert data["variables"]["color"] == "blue"  # untouched
