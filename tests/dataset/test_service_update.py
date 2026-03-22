"""Tests for DatasetService.update_case() method."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.dataset.models import TestCase
from api.dataset.service import DatasetService
from api.exceptions import PromptNotFoundError
from api.registry.models import PromptRegistration
from api.registry.service import PromptRegistry
from api.storage.models import Base


@pytest.fixture
async def session_factory():
    """Create an in-memory SQLite engine with all tables and return a session factory."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def dataset_service(session_factory) -> DatasetService:
    """Create a DatasetService and register a test prompt."""
    registry = PromptRegistry(session_factory)
    await registry.register(
        PromptRegistration(
            id="test-prompt",
            purpose="Test prompt",
            template="Hello {{ name }}",
        )
    )
    return DatasetService(session_factory)


async def test_update_case_success(dataset_service: DatasetService):
    """update_case overwrites existing case and returns updated TestCase."""
    # Arrange: add a case first
    original = TestCase(name="original", tier="normal")
    added, _warnings = await dataset_service.add_case("test-prompt", original)

    # Act: update the case with new values
    updated_case = TestCase(
        id=added.id,
        name="updated-name",
        tier="critical",
        description="updated description",
    )
    result = await dataset_service.update_case("test-prompt", added.id, updated_case)

    # Assert: returned case has updated fields
    assert result.name == "updated-name"
    assert result.tier.value == "critical"
    assert result.description == "updated description"
    assert result.id == added.id

    # Assert: DB reflects changes
    fetched = await dataset_service.get_case("test-prompt", added.id)
    assert fetched.name == "updated-name"
    assert fetched.tier.value == "critical"


async def test_update_case_not_found(dataset_service: DatasetService):
    """update_case with nonexistent case_id raises ValueError."""
    case = TestCase(name="ghost")
    with pytest.raises(ValueError, match="not found"):
        await dataset_service.update_case("test-prompt", "nonexistent-id", case)


async def test_update_case_prompt_not_found(dataset_service: DatasetService):
    """update_case with nonexistent prompt raises PromptNotFoundError."""
    case = TestCase(name="ghost")
    with pytest.raises(PromptNotFoundError):
        await dataset_service.update_case("nonexistent-prompt", "some-id", case)
