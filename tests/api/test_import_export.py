"""Comprehensive import/export flow tests for all data interchange endpoints.

Verifies end-to-end import/export flows across:
- Dataset import via file upload (JSON)
- Persona export as JSON array
- Settings GET/PUT round-trip (config export/import)
- Prompt config GET/PUT round-trip

These tests exercise the full HTTP layer through FastAPI's ASGI transport
to catch issues that may have been introduced during structural changes
(DB migration in Phase 62, package rename in Phase 64-01).
"""

from __future__ import annotations

import json

import httpx
import pytest


# -- Helpers --


async def _create_prompt(
    client: httpx.AsyncClient,
    prompt_id: str = "ie-test-prompt",
) -> dict:
    """Register a prompt and return the response JSON."""
    resp = await client.post(
        "/api/prompts/",
        json={
            "id": prompt_id,
            "purpose": "Import/export flow testing",
            "template": "Hello {{ name }}, welcome to {{ place }}",
        },
    )
    assert resp.status_code == 201, f"Failed to create prompt: {resp.text}"
    return resp.json()


# -- Test 1: Dataset import via file upload creates test cases in DB --


async def test_dataset_import_creates_cases_in_db(client: httpx.AsyncClient):
    """POST /{prompt_id}/dataset/import with JSON file creates test cases.

    Verifies:
    - Response is 200 with list of TestCaseResponse objects
    - Each imported case has an id, name, tier, and variables
    - Cases are persisted (GET /dataset confirms they exist)
    """
    await _create_prompt(client)

    cases_data = {
        "cases": [
            {
                "name": "import-flow-1",
                "variables": {"name": "Alice", "place": "Wonderland"},
                "tier": "normal",
                "tags": ["import-test"],
            },
            {
                "name": "import-flow-2",
                "variables": {"name": "Bob", "place": "Builderland"},
                "tier": "critical",
                "tags": ["import-test", "critical"],
            },
        ]
    }

    # Import via file upload
    resp = await client.post(
        "/api/prompts/ie-test-prompt/dataset/import",
        files={"file": ("cases.json", json.dumps(cases_data), "application/json")},
    )
    assert resp.status_code == 200
    imported = resp.json()
    assert isinstance(imported, list)
    assert len(imported) == 2

    # Verify each case has expected fields
    for case in imported:
        assert "id" in case
        assert "name" in case
        assert "tier" in case
        assert "variables" in case

    names = {c["name"] for c in imported}
    assert names == {"import-flow-1", "import-flow-2"}

    # Verify persistence: GET should return the imported cases
    list_resp = await client.get("/api/prompts/ie-test-prompt/dataset")
    assert list_resp.status_code == 200
    persisted = list_resp.json()
    assert len(persisted) == 2
    persisted_names = {c["name"] for c in persisted}
    assert persisted_names == {"import-flow-1", "import-flow-2"}


# -- Test 2: Dataset import with invalid JSON returns error --


async def test_dataset_import_invalid_json_returns_error(client: httpx.AsyncClient):
    """POST /{prompt_id}/dataset/import with invalid JSON returns 400.

    Verifies the endpoint handles malformed input gracefully with an
    appropriate error response rather than a 500.
    """
    await _create_prompt(client)

    resp = await client.post(
        "/api/prompts/ie-test-prompt/dataset/import",
        files={"file": ("bad.json", "{ not valid json !!!", "application/json")},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "detail" in data


# -- Test 3: Persona export returns JSON array of all personas --


async def test_persona_export_returns_all_personas(client: httpx.AsyncClient):
    """GET /{prompt_id}/personas/export returns JSON array of PersonaProfileResponse.

    Verifies:
    - Response is 200 with a list
    - Creating a custom persona makes it appear in the export
    - Export includes both default personas and custom ones
    """
    await _create_prompt(client)

    # Create a custom persona
    create_resp = await client.post(
        "/api/prompts/ie-test-prompt/personas",
        json={
            "id": "test-persona",
            "role": "Friendly helper",
            "traits": ["helpful", "patient"],
            "communication_style": "Warm and encouraging",
            "goal": "Help user accomplish their task",
        },
    )
    assert create_resp.status_code == 201

    # Export all personas
    export_resp = await client.get("/api/prompts/ie-test-prompt/personas/export")
    assert export_resp.status_code == 200
    exported = export_resp.json()
    assert isinstance(exported, list)
    assert len(exported) > 0

    # Our custom persona should be in the export
    exported_ids = {p["id"] for p in exported}
    assert "test-persona" in exported_ids

    # Each persona should have the expected shape
    for persona in exported:
        assert "id" in persona
        assert "role" in persona
        assert "traits" in persona
        assert "communication_style" in persona
        assert "goal" in persona


# -- Test 4: Persona export for prompt with no personas returns defaults or empty --


async def test_persona_export_no_custom_personas_returns_defaults(client: httpx.AsyncClient):
    """GET /{prompt_id}/personas/export for prompt with no custom personas.

    The endpoint returns default personas when no DB rows exist for the prompt.
    Verifies the response is a valid list (defaults are returned without DB rows).
    """
    await _create_prompt(client, prompt_id="ie-empty-personas")

    export_resp = await client.get("/api/prompts/ie-empty-personas/personas/export")
    assert export_resp.status_code == 200
    exported = export_resp.json()
    assert isinstance(exported, list)
    # Default personas should be returned (3 defaults)
    assert len(exported) == 3
    default_ids = {p["id"] for p in exported}
    assert "confused-user" in default_ids
    assert "adversarial-user" in default_ids
    assert "impatient-user" in default_ids


# -- Test 5: Settings GET returns current configuration (config export) --


async def test_settings_get_returns_config(client: httpx.AsyncClient):
    """GET /api/settings returns current configuration as structured JSON.

    Verifies the settings endpoint works as a config export mechanism,
    returning all role configurations, generation params, and provider list.
    """
    resp = await client.get("/api/settings/")
    assert resp.status_code == 200
    data = resp.json()

    # Should have all 3 roles
    for role in ("meta", "target", "judge"):
        assert role in data
        role_data = data[role]
        assert "provider" in role_data
        assert "model" in role_data
        assert "has_key" in role_data

    # Should have global fields
    assert "concurrency_limit" in data
    assert "generation" in data
    assert isinstance(data["generation"], dict)
    assert "providers" in data
    assert isinstance(data["providers"], list)


# -- Test 6: Settings PUT/GET round-trip (config import/export) --


async def test_settings_put_get_round_trip(client: httpx.AsyncClient):
    """PUT /api/settings then GET reflects the changes (round-trip).

    Verifies:
    - PUT updates configuration values in DB
    - Subsequent GET returns the updated values
    - This proves settings import/export round-trips correctly
    """
    # Update settings
    update_resp = await client.put(
        "/api/settings/",
        json={
            "meta_provider": "openai",
            "meta_model": "gpt-4o",
            "concurrency_limit": 5,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["meta"]["provider"] == "openai"
    assert updated["meta"]["model"] == "gpt-4o"
    assert updated["concurrency_limit"] == 5

    # GET should reflect changes
    get_resp = await client.get("/api/settings/")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["meta"]["provider"] == "openai"
    assert fetched["meta"]["model"] == "gpt-4o"
    assert fetched["concurrency_limit"] == 5


# -- Test 7: Prompt config GET/PUT round-trip --


async def test_prompt_config_get_put_round_trip(client: httpx.AsyncClient):
    """GET /{prompt_id}/config, PUT with modifications, GET again to verify.

    Verifies:
    - GET returns the effective prompt config with default values
    - PUT updates per-prompt overrides in DB
    - Subsequent GET returns the modified values
    - This proves prompt config import/export round-trips correctly
    """
    await _create_prompt(client)

    # GET initial config (should have global defaults)
    initial_resp = await client.get("/api/prompts/ie-test-prompt/config")
    assert initial_resp.status_code == 200
    initial = initial_resp.json()
    assert "meta" in initial
    assert "target" in initial
    assert "judge" in initial
    assert "overrides" in initial

    # PUT with per-prompt overrides
    update_resp = await client.put(
        "/api/prompts/ie-test-prompt/config",
        json={
            "meta_model": "custom-model",
            "meta_provider": "openai",
            "target_temperature": 0.5,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["meta"]["model"] == "custom-model"
    assert updated["meta"]["provider"] == "openai"

    # GET again should reflect the overrides
    final_resp = await client.get("/api/prompts/ie-test-prompt/config")
    assert final_resp.status_code == 200
    final = final_resp.json()
    assert final["meta"]["model"] == "custom-model"
    assert final["meta"]["provider"] == "openai"
    assert final["overrides"].get("meta_model") == "custom-model"
    assert final["overrides"].get("meta_provider") == "openai"
