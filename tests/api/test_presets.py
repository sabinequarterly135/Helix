"""Tests for Presets CRUD API endpoints.

Covers:
- GET /api/presets returns all presets (empty list initially)
- GET /api/presets?type=config returns only config presets
- POST /api/presets creates a new preset (201)
- PUT /api/presets/{id} updates an existing preset
- DELETE /api/presets/{id} removes a preset (204)
- PUT /api/presets/{id}/default marks preset as default (clears others of same type)
"""

from __future__ import annotations

import pytest

from api.storage.database import Database


@pytest.fixture
async def db_session(tmp_path):
    """Create an in-memory SQLite database with all tables and yield a session."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test_presets.db'}"
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

    # Register presets router if not already registered
    from api.web.routers import presets

    # Check if presets router is already included
    prefixes = [r.prefix for r in app.routes if hasattr(r, "prefix")]
    if "/api/presets" not in prefixes:
        app.include_router(presets.router, prefix="/api/presets", tags=["presets"])

    return app


@pytest.fixture
async def client_db(app_with_db):
    """Async HTTP client wired to the app with DB session."""
    import httpx

    transport = httpx.ASGITransport(app=app_with_db)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestListPresets:
    """GET /api/presets."""

    async def test_returns_empty_list_initially(self, client_db):
        """Returns empty list when no presets exist."""
        resp = await client_db.get("/api/presets")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_filter_by_type(self, client_db):
        """GET /api/presets?type=config returns only config presets."""
        # Create a config preset and an evolution preset
        await client_db.post(
            "/api/presets",
            json={"name": "Config 1", "type": "config", "data": {"key": "val"}},
        )
        await client_db.post(
            "/api/presets",
            json={"name": "Evo 1", "type": "evolution", "data": {"gen": 10}},
        )

        resp = await client_db.get("/api/presets?type=config")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["type"] == "config"
        assert data[0]["name"] == "Config 1"


class TestCreatePreset:
    """POST /api/presets."""

    async def test_creates_preset_201(self, client_db):
        """Creates a new preset and returns 201 with preset data."""
        payload = {"name": "My Preset", "type": "config", "data": {"key": "value"}}
        resp = await client_db.post("/api/presets", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Preset"
        assert data["type"] == "config"
        assert data["data"] == {"key": "value"}
        assert data["is_default"] is False
        assert "id" in data
        assert "created_at" in data


class TestUpdatePreset:
    """PUT /api/presets/{id}."""

    async def test_updates_preset(self, client_db):
        """Updates an existing preset."""
        # Create first
        create_resp = await client_db.post(
            "/api/presets",
            json={"name": "Original", "type": "config", "data": {"a": 1}},
        )
        preset_id = create_resp.json()["id"]

        # Update
        resp = await client_db.put(
            f"/api/presets/{preset_id}",
            json={"name": "Updated", "data": {"b": 2}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated"
        assert data["data"] == {"b": 2}
        assert data["type"] == "config"  # unchanged


class TestDeletePreset:
    """DELETE /api/presets/{id}."""

    async def test_deletes_preset_204(self, client_db):
        """Deletes a preset and returns 204."""
        create_resp = await client_db.post(
            "/api/presets",
            json={"name": "To Delete", "type": "evolution", "data": {}},
        )
        preset_id = create_resp.json()["id"]

        resp = await client_db.delete(f"/api/presets/{preset_id}")
        assert resp.status_code == 204

        # Verify gone
        list_resp = await client_db.get("/api/presets")
        assert len(list_resp.json()) == 0


class TestSetDefault:
    """PUT /api/presets/{id}/default."""

    async def test_marks_preset_as_default(self, client_db):
        """Marks a preset as default, clearing other defaults of same type."""
        # Create two config presets
        r1 = await client_db.post(
            "/api/presets",
            json={"name": "Preset A", "type": "config", "data": {}, "is_default": True},
        )
        r2 = await client_db.post(
            "/api/presets",
            json={"name": "Preset B", "type": "config", "data": {}},
        )
        id_a = r1.json()["id"]
        id_b = r2.json()["id"]

        # Set B as default
        resp = await client_db.put(f"/api/presets/{id_b}/default")
        assert resp.status_code == 200
        assert resp.json()["is_default"] is True

        # Verify A is no longer default
        list_resp = await client_db.get("/api/presets?type=config")
        for p in list_resp.json():
            if p["id"] == id_a:
                assert p["is_default"] is False
            elif p["id"] == id_b:
                assert p["is_default"] is True
