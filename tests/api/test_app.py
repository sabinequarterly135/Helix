"""Tests for the FastAPI app foundation: health, docs, CORS, exception handlers."""

from __future__ import annotations

import httpx
from fastapi import FastAPI

from api.web.app import create_app
from api.exceptions import PromptAlreadyExistsError, PromptNotFoundError


async def test_health_returns_ok(client: httpx.AsyncClient):
    """GET /health returns 200 with {status: ok}."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_docs_returns_html(client: httpx.AsyncClient):
    """GET /docs returns 200 with Swagger UI HTML."""
    resp = await client.get("/docs")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


async def test_cors_preflight(client: httpx.AsyncClient):
    """OPTIONS /health with localhost:5173 origin returns CORS headers."""
    resp = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "http://localhost:5173" in resp.headers.get("access-control-allow-origin", "")


async def test_not_found_exception_handler(app: FastAPI):
    """PromptNotFoundError triggers 404 response."""

    # Add a test-only route that raises the domain exception
    @app.get("/test-404")
    async def raise_not_found():
        raise PromptNotFoundError("test-prompt not found")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/test-404")

    assert resp.status_code == 404
    assert "test-prompt not found" in resp.json()["detail"]


async def test_already_exists_exception_handler(app: FastAPI):
    """PromptAlreadyExistsError triggers 409 response."""

    @app.get("/test-409")
    async def raise_already_exists():
        raise PromptAlreadyExistsError("test-prompt already exists")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/test-409")

    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


async def test_value_error_exception_handler(app: FastAPI):
    """ValueError triggers 400 response."""

    @app.get("/test-400")
    async def raise_value_error():
        raise ValueError("bad input")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/test-400")

    assert resp.status_code == 400
    assert "bad input" in resp.json()["detail"]


# --- CORS_ORIGINS env var tests ---


async def test_cors_origins_env_var_custom(monkeypatch):
    """CORS_ORIGINS env var with comma-separated origins configures middleware."""
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com,https://app.example.com")
    app = create_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.options(
            "/health",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200
    assert "https://example.com" in resp.headers.get("access-control-allow-origin", "")


async def test_cors_origins_default_no_env(monkeypatch):
    """Default CORS origins (no env var set) include localhost:5173 and localhost:3000."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    app = create_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # Check localhost:5173
        resp = await c.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert "http://localhost:5173" in resp.headers.get("access-control-allow-origin", "")

        # Check localhost:3000
        resp2 = await c.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp2.status_code == 200
        assert "http://localhost:3000" in resp2.headers.get("access-control-allow-origin", "")


async def test_cors_origins_wildcard(monkeypatch):
    """CORS_ORIGINS='*' sets wildcard origin."""
    monkeypatch.setenv("CORS_ORIGINS", "*")
    app = create_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.options(
            "/health",
            headers={
                "Origin": "https://any-domain.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200
    # Starlette CORS middleware with allow_origins=["*"] echoes the requesting
    # origin back (not a literal "*") — verify any origin is accepted
    assert resp.headers.get("access-control-allow-origin") == "https://any-domain.example.com"
