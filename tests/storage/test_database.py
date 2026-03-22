"""Tests for SQLAlchemy ORM models and async database class.

Tests verify model fields and relationships using SQLAlchemy inspection
(no real database required).
"""

from sqlalchemy import inspect as sa_inspect


class TestEvolutionRunModel:
    """Test EvolutionRun ORM model has all required fields."""

    def test_evolution_run_has_all_required_columns(self):
        """VER-02: EvolutionRun model has all required fields."""
        from api.storage.models import EvolutionRun

        mapper = sa_inspect(EvolutionRun)
        column_names = {c.key for c in mapper.column_attrs}

        required = {
            "id",
            "created_at",
            "prompt_id",
            "status",
            "meta_model",
            "target_model",
            "judge_model",
            "hyperparameters",
            "total_input_tokens",
            "total_output_tokens",
            "total_cost_usd",
            "total_api_calls",
            "best_fitness_score",
            "generations_completed",
            "extra_metadata",
        }
        assert required.issubset(column_names), f"Missing columns: {required - column_names}"

    def test_evolution_run_id_is_primary_key(self):
        from api.storage.models import EvolutionRun

        mapper = sa_inspect(EvolutionRun)
        pk_cols = [c.name for c in mapper.primary_key]
        assert "id" in pk_cols

    def test_evolution_run_prompt_id_is_indexed(self):
        from api.storage.models import EvolutionRun

        mapper = sa_inspect(EvolutionRun)
        prompt_id_col = mapper.columns["prompt_id"]
        assert prompt_id_col.index is True or any(
            "prompt_id" in str(idx.columns) for idx in EvolutionRun.__table__.indexes
        )

    def test_evolution_run_status_defaults_to_running(self):
        from api.storage.models import EvolutionRun

        mapper = sa_inspect(EvolutionRun)
        status_col = mapper.columns["status"]
        assert status_col.default is not None


class TestLLMCallRecordModel:
    """Test LLMCallRecord ORM model has all required fields."""

    def test_llm_call_record_has_all_required_columns(self):
        """VER-02: LLMCallRecord model has all required fields."""
        from api.storage.models import LLMCallRecord

        mapper = sa_inspect(LLMCallRecord)
        column_names = {c.key for c in mapper.column_attrs}

        required = {
            "id",
            "evolution_run_id",
            "model",
            "role",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "generation_id",
            "timestamp",
            "request_type",
        }
        assert required.issubset(column_names), f"Missing columns: {required - column_names}"

    def test_llm_call_record_has_foreign_key(self):
        from api.storage.models import LLMCallRecord

        mapper = sa_inspect(LLMCallRecord)
        fk_col = mapper.columns["evolution_run_id"]
        assert len(fk_col.foreign_keys) > 0

    def test_llm_call_record_evolution_run_id_indexed(self):
        from api.storage.models import LLMCallRecord

        mapper = sa_inspect(LLMCallRecord)
        col = mapper.columns["evolution_run_id"]
        assert col.index is True or any(
            "evolution_run_id" in str(idx.columns) for idx in LLMCallRecord.__table__.indexes
        )


class TestModelRelationships:
    """Test relationships between ORM models."""

    def test_evolution_run_has_llm_calls_relationship(self):
        """VER-02: EvolutionRun has one-to-many relationship to LLMCallRecord."""
        from api.storage.models import EvolutionRun

        mapper = sa_inspect(EvolutionRun)
        relationships = {r.key for r in mapper.relationships}
        assert "llm_calls" in relationships

    def test_llm_call_record_has_evolution_run_relationship(self):
        from api.storage.models import LLMCallRecord

        mapper = sa_inspect(LLMCallRecord)
        relationships = {r.key for r in mapper.relationships}
        assert "evolution_run" in relationships

    def test_relationship_cascade_delete(self):
        from api.storage.models import EvolutionRun

        mapper = sa_inspect(EvolutionRun)
        llm_calls_rel = mapper.relationships["llm_calls"]
        cascade = llm_calls_rel.cascade
        assert "delete" in cascade or "all" in cascade


class TestDatabaseClass:
    """Test Database class for async engine and session factory."""

    def test_database_creates_engine(self):
        from api.storage.database import Database

        db = Database("postgresql://user:pass@localhost:5432/testdb")
        assert db.engine is not None

    def test_database_converts_url_prefix(self):
        from api.storage.database import Database

        db = Database("postgresql://user:pass@localhost:5432/testdb")
        assert "asyncpg" in str(db.engine.url)

    def test_database_preserves_asyncpg_url(self):
        from api.storage.database import Database

        db = Database("postgresql+asyncpg://user:pass@localhost:5432/testdb")
        assert "asyncpg" in str(db.engine.url)

    def test_database_has_session_factory(self):
        from api.storage.database import Database

        db = Database("postgresql://user:pass@localhost:5432/testdb")
        assert db.session_factory is not None

    async def test_database_get_session_returns_async_session(self):
        from sqlalchemy.ext.asyncio import AsyncSession

        from api.storage.database import Database

        db = Database("postgresql://user:pass@localhost:5432/testdb")
        session = await db.get_session()
        assert isinstance(session, AsyncSession)
        await session.close()


class TestBaseModel:
    """Test Base declarative base class."""

    def test_base_exports(self):
        from api.storage.models import Base

        assert hasattr(Base, "metadata")
