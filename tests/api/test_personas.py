"""Tests for Persona CRUD API endpoints (DB-backed, replaces YAML).

Covers:
- GET /{prompt_id}/personas returns default personas when no DB rows exist
- POST /{prompt_id}/personas creates a persona in DB (201)
- POST /{prompt_id}/personas returns 409 on duplicate persona_id for same prompt
- PUT /{prompt_id}/personas/{persona_id} updates persona fields in DB
- PUT /{prompt_id}/personas/{persona_id} returns 404 if persona not found
- DELETE /{prompt_id}/personas/{persona_id} removes persona from DB (204)
- DELETE /{prompt_id}/personas/{persona_id} returns 404 if persona not found
- GET /{prompt_id}/personas/export returns JSON array of all personas from DB
- POST /{prompt_id}/personas/import merges personas into DB, skips existing
- Default personas are materialized to DB on first write operation
- PersonaProfileResponse shape is unchanged
"""

from __future__ import annotations

import pytest

from api.storage.database import Database


PROMPT_ID = "test-prompt"


@pytest.fixture
async def db_session(tmp_path):
    """Create an in-memory SQLite database with all tables and yield a session."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test_personas.db'}"
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
                "purpose": "Test prompt for personas",
                "template": "You are a helpful assistant.",
            },
        )
        yield c


class TestGetPersonas:
    """GET /api/prompts/{prompt_id}/personas."""

    async def test_returns_defaults_when_no_db_rows(self, client_db):
        """Returns 3 default personas when no DB rows exist for prompt."""
        resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/personas")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        ids = {p["id"] for p in data}
        assert ids == {"confused-user", "adversarial-user", "impatient-user"}

    async def test_response_shape_unchanged(self, client_db):
        """PersonaProfileResponse shape is unchanged."""
        resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/personas")
        assert resp.status_code == 200
        data = resp.json()
        p = data[0]
        # Verify all expected fields are present
        assert "id" in p
        assert "role" in p
        assert "traits" in p
        assert "communication_style" in p
        assert "goal" in p
        assert "edge_cases" in p
        assert "behavior_criteria" in p
        assert "language" in p
        assert "channel" in p


class TestCreatePersona:
    """POST /api/prompts/{prompt_id}/personas."""

    async def test_creates_persona_201(self, client_db):
        """Creates a new persona and returns 201."""
        payload = {
            "id": "new-persona",
            "role": "Friendly user",
            "traits": ["kind", "patient"],
            "communication_style": "warm",
            "goal": "Get help politely",
        }
        resp = await client_db.post(f"/api/prompts/{PROMPT_ID}/personas", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "new-persona"
        assert data["role"] == "Friendly user"

    async def test_conflict_on_duplicate_id(self, client_db):
        """Returns 409 when persona with same ID already exists."""
        payload = {
            "id": "dup-persona",
            "role": "User A",
            "traits": ["trait"],
            "communication_style": "neutral",
            "goal": "goal",
        }
        resp1 = await client_db.post(f"/api/prompts/{PROMPT_ID}/personas", json=payload)
        assert resp1.status_code == 201

        resp2 = await client_db.post(f"/api/prompts/{PROMPT_ID}/personas", json=payload)
        assert resp2.status_code == 409

    async def test_materializes_defaults_on_first_write(self, client_db):
        """Default personas are materialized to DB on first write operation."""
        # Create a new persona -- defaults should be materialized first
        payload = {
            "id": "test-materialze",
            "role": "Test",
            "traits": ["test"],
            "communication_style": "test",
            "goal": "test",
        }
        await client_db.post(f"/api/prompts/{PROMPT_ID}/personas", json=payload)

        # List should show 3 defaults + 1 new = 4
        resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/personas")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4
        ids = {p["id"] for p in data}
        assert "confused-user" in ids
        assert "test-materialze" in ids


class TestUpdatePersona:
    """PUT /api/prompts/{prompt_id}/personas/{persona_id}."""

    async def test_updates_persona(self, client_db):
        """Updates an existing persona's fields."""
        # Create first
        payload = {
            "id": "upd-persona",
            "role": "Original role",
            "traits": ["trait"],
            "communication_style": "neutral",
            "goal": "original goal",
        }
        await client_db.post(f"/api/prompts/{PROMPT_ID}/personas", json=payload)

        # Update
        update = {"role": "Updated role", "goal": "updated goal"}
        resp = await client_db.put(f"/api/prompts/{PROMPT_ID}/personas/upd-persona", json=update)
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "Updated role"
        assert data["goal"] == "updated goal"
        # Unchanged field preserved
        assert data["communication_style"] == "neutral"

    async def test_404_on_missing_persona(self, client_db):
        """Returns 404 when persona_id does not exist."""
        resp = await client_db.put(
            f"/api/prompts/{PROMPT_ID}/personas/nonexistent",
            json={"role": "nope"},
        )
        assert resp.status_code == 404


class TestDeletePersona:
    """DELETE /api/prompts/{prompt_id}/personas/{persona_id}."""

    async def test_deletes_persona_204(self, client_db):
        """Deletes a persona and returns 204."""
        payload = {
            "id": "del-persona",
            "role": "To delete",
            "traits": ["trait"],
            "communication_style": "neutral",
            "goal": "goal",
        }
        await client_db.post(f"/api/prompts/{PROMPT_ID}/personas", json=payload)

        resp = await client_db.delete(f"/api/prompts/{PROMPT_ID}/personas/del-persona")
        assert resp.status_code == 204

        # Verify gone
        get_resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/personas")
        ids = {p["id"] for p in get_resp.json()}
        assert "del-persona" not in ids

    async def test_404_on_missing_persona(self, client_db):
        """Returns 404 when persona to delete does not exist."""
        resp = await client_db.delete(f"/api/prompts/{PROMPT_ID}/personas/nonexistent")
        assert resp.status_code == 404


class TestLanguageChannelFields:
    """Language and channel field support in persona CRUD."""

    async def test_create_persona_with_language_channel(self, client_db):
        """Create persona with language='es', channel='voice' returns them in response."""
        payload = {
            "id": "spanish-voice",
            "role": "Spanish voice caller",
            "traits": ["bilingual"],
            "communication_style": "Conversational",
            "goal": "Get help in Spanish over phone",
            "language": "es",
            "channel": "voice",
        }
        resp = await client_db.post(f"/api/prompts/{PROMPT_ID}/personas", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["language"] == "es"
        assert data["channel"] == "voice"

    async def test_list_personas_returns_language_channel_defaults(self, client_db):
        """List personas returns language/channel with correct defaults."""
        resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/personas")
        assert resp.status_code == 200
        data = resp.json()
        for persona in data:
            assert persona["language"] == "en"
            assert persona["channel"] == "text"

    async def test_update_persona_language_channel(self, client_db):
        """Update persona language and channel via PUT."""
        # Create first
        payload = {
            "id": "update-lang",
            "role": "Updatable",
            "traits": ["flexible"],
            "communication_style": "neutral",
            "goal": "be updated",
        }
        await client_db.post(f"/api/prompts/{PROMPT_ID}/personas", json=payload)

        # Update language and channel
        update = {"language": "fr", "channel": "voice"}
        resp = await client_db.put(f"/api/prompts/{PROMPT_ID}/personas/update-lang", json=update)
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == "fr"
        assert data["channel"] == "voice"


class TestExportPersonas:
    """GET /api/prompts/{prompt_id}/personas/export."""

    async def test_export_returns_json_array(self, client_db):
        """Export returns all personas as JSON array."""
        resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/personas/export")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 3  # defaults


class TestImportPersonas:
    """POST /api/prompts/{prompt_id}/personas/import."""

    async def test_import_adds_new_personas(self, client_db):
        """Import adds new personas and skips existing IDs."""
        # First get defaults (3 personas)
        resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/personas")
        assert resp.status_code == 200

        # Import: 1 new + 1 existing ID
        import_payload = [
            {
                "id": "imported-persona",
                "role": "Imported",
                "traits": ["new"],
                "communication_style": "formal",
                "goal": "test import",
            },
            {
                "id": "confused-user",
                "role": "Duplicate",
                "traits": ["dup"],
                "communication_style": "dup",
                "goal": "dup",
            },
        ]
        resp = await client_db.post(
            f"/api/prompts/{PROMPT_ID}/personas/import", json=import_payload
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["added_count"] == 1
        assert data["skipped_count"] == 1

        # Verify total count
        get_resp = await client_db.get(f"/api/prompts/{PROMPT_ID}/personas")
        assert len(get_resp.json()) == 4  # 3 defaults + 1 imported
