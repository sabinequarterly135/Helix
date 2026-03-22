"""FastAPI dependency providers for shared services.

Each provider is a callable suitable for use with FastAPI's Depends().
Database engine is cached as a singleton; services are lightweight wrappers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.config.models import GeneConfig
from api.dataset.service import DatasetService
from api.registry.service import PromptRegistry
from api.storage.database import Database


@lru_cache
def get_config() -> GeneConfig:
    """Return the application configuration (cached singleton)."""
    return GeneConfig()


@lru_cache
def _get_database() -> Database:
    """Return a cached Database singleton.

    The engine and connection pool are created once and reused
    across all requests. This is critical for connection pooling.
    """
    config = get_config()
    if config.database_url is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    return Database(config.database_url)


def _get_session_factory() -> async_sessionmaker:
    """Return the async session factory from the cached Database."""
    return _get_database().session_factory


def get_registry(
    session_factory: async_sessionmaker = Depends(_get_session_factory),
) -> PromptRegistry:
    """Create a DB-backed PromptRegistry."""
    return PromptRegistry(session_factory)


def get_dataset_service(
    session_factory: async_sessionmaker = Depends(_get_session_factory),
) -> DatasetService:
    """Create a DB-backed DatasetService."""
    return DatasetService(session_factory)


def get_database() -> Database:
    """Return the cached Database instance.

    Raises:
        HTTPException: 503 if database_url is not configured.
    """
    return _get_database()


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """Yield an async database session for use in route handlers."""
    db = _get_database()
    session = await db.get_session()
    try:
        yield session
    finally:
        await session.close()
