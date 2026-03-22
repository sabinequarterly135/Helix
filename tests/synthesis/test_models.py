"""Tests for synthesis models and PersonasSchema YAML sidecar.

Covers:
- PersonaProfile validation (required fields, defaults)
- SynthesisConfig defaults
- ConversationRecord fields and optionals
- SynthesisResult computed fields
- PersonasSchema YAML round-trip (to_yaml -> from_yaml)
- PersonasSchema empty/missing content handling
- PromptRegistry.load_prompt() personas loading from DB
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.storage.models import Base, Persona
from api.synthesis.models import (
    ConversationRecord,
    PersonaProfile,
    SynthesisConfig,
    SynthesisResult,
)
from api.synthesis.personas import PersonasSchema


# --- PersonaProfile validation ---


class TestPersonaProfile:
    """Tests for PersonaProfile model validation."""

    def test_valid_persona_all_fields(self) -> None:
        """PersonaProfile validates with all required fields provided."""
        persona = PersonaProfile(
            id="frustrated-caller",
            role="Frustrated customer",
            traits=["impatient", "emotional"],
            communication_style="Short, aggressive sentences",
            goal="Get transferred without stating reason",
            edge_cases=["Refuse to answer questions"],
            behavior_criteria=["Stay calm"],
        )
        assert persona.id == "frustrated-caller"
        assert persona.role == "Frustrated customer"
        assert persona.traits == ["impatient", "emotional"]
        assert persona.communication_style == "Short, aggressive sentences"
        assert persona.goal == "Get transferred without stating reason"
        assert persona.edge_cases == ["Refuse to answer questions"]
        assert persona.behavior_criteria == ["Stay calm"]

    def test_persona_defaults_empty_lists(self) -> None:
        """edge_cases and behavior_criteria default to empty lists."""
        persona = PersonaProfile(
            id="basic",
            role="Basic user",
            traits=["friendly"],
            communication_style="Normal",
            goal="Get help",
        )
        assert persona.edge_cases == []
        assert persona.behavior_criteria == []

    def test_persona_rejects_missing_role(self) -> None:
        """PersonaProfile rejects creation without required role field."""
        with pytest.raises(Exception):
            PersonaProfile(
                id="no-role",
                traits=["friendly"],
                communication_style="Normal",
                goal="Get help",
            )

    def test_persona_language_and_channel_explicit(self) -> None:
        """PersonaProfile with language='es' and channel='voice' stores values correctly."""
        persona = PersonaProfile(
            id="spanish-voice",
            role="Spanish speaker",
            traits=["bilingual"],
            communication_style="Conversational",
            goal="Get help in Spanish",
            language="es",
            channel="voice",
        )
        assert persona.language == "es"
        assert persona.channel == "voice"

    def test_persona_language_channel_defaults(self) -> None:
        """PersonaProfile without language/channel gets defaults 'en' and 'text'."""
        persona = PersonaProfile(
            id="default-lang",
            role="Default user",
            traits=["normal"],
            communication_style="Standard",
            goal="Get help",
        )
        assert persona.language == "en"
        assert persona.channel == "text"

    def test_persona_rejects_missing_goal(self) -> None:
        """PersonaProfile rejects creation without required goal field."""
        with pytest.raises(Exception):
            PersonaProfile(
                id="no-goal",
                role="Some role",
                traits=["friendly"],
                communication_style="Normal",
            )


# --- SynthesisConfig defaults ---


class TestSynthesisConfig:
    """Tests for SynthesisConfig model defaults."""

    def test_default_values(self) -> None:
        """SynthesisConfig defaults: num_conversations=5, max_turns=10, persona_ids=None."""
        config = SynthesisConfig()
        assert config.num_conversations == 5
        assert config.max_turns == 10
        assert config.persona_ids is None

    def test_custom_values(self) -> None:
        """SynthesisConfig accepts custom values."""
        config = SynthesisConfig(
            num_conversations=10,
            max_turns=20,
            persona_ids=["p1", "p2"],
        )
        assert config.num_conversations == 10
        assert config.max_turns == 20
        assert config.persona_ids == ["p1", "p2"]


# --- ConversationRecord ---


class TestConversationRecord:
    """Tests for ConversationRecord model."""

    def test_required_fields(self) -> None:
        """ConversationRecord stores persona_id, chat_history, variables, turns."""
        record = ConversationRecord(
            persona_id="test-persona",
            chat_history=[{"role": "user", "content": "Hello"}],
            variables={"name": "Test"},
            turns=1,
        )
        assert record.persona_id == "test-persona"
        assert len(record.chat_history) == 1
        assert record.variables == {"name": "Test"}
        assert record.turns == 1

    def test_optional_fields_default_none(self) -> None:
        """score, passed, persisted_case_id default to None."""
        record = ConversationRecord(
            persona_id="test",
            chat_history=[],
            variables={},
            turns=0,
        )
        assert record.score is None
        assert record.passed is None
        assert record.persisted_case_id is None


# --- SynthesisResult ---


class TestSynthesisResult:
    """Tests for SynthesisResult model."""

    def test_computed_fields(self) -> None:
        """SynthesisResult stores total_conversations, total_persisted, total_discarded."""
        result = SynthesisResult(
            total_conversations=5,
            total_persisted=2,
            total_discarded=3,
            conversations=[
                ConversationRecord(
                    persona_id="p1",
                    chat_history=[],
                    variables={},
                    turns=3,
                    score=-1.0,
                    passed=False,
                    persisted_case_id="case-1",
                ),
                ConversationRecord(
                    persona_id="p1",
                    chat_history=[],
                    variables={},
                    turns=5,
                    score=0.0,
                    passed=True,
                ),
            ],
        )
        assert result.total_conversations == 5
        assert result.total_persisted == 2
        assert result.total_discarded == 3
        assert len(result.conversations) == 2


# --- PersonasSchema YAML round-trip ---


class TestPersonasSchema:
    """Tests for PersonasSchema YAML sidecar."""

    def test_round_trip_yaml(self) -> None:
        """PersonasSchema.to_yaml() then from_yaml() produces identical model."""
        original = PersonasSchema(
            personas=[
                PersonaProfile(
                    id="test-persona",
                    role="Test role",
                    traits=["trait1", "trait2"],
                    communication_style="Normal",
                    goal="Test goal",
                    edge_cases=["edge1"],
                    behavior_criteria=["criteria1"],
                ),
            ]
        )
        yaml_text = original.to_yaml()
        restored = PersonasSchema.from_yaml(yaml_text)
        assert restored == original

    def test_from_yaml_empty_string(self) -> None:
        """PersonasSchema.from_yaml('') returns empty personas list."""
        schema = PersonasSchema.from_yaml("")
        assert schema.personas == []

    def test_from_yaml_none_content(self) -> None:
        """PersonasSchema.from_yaml with content that parses to None returns empty list."""
        schema = PersonasSchema.from_yaml("---\n")
        assert schema.personas == []

    def test_to_yaml_produces_valid_yaml(self) -> None:
        """to_yaml() produces parseable YAML string."""
        schema = PersonasSchema(
            personas=[
                PersonaProfile(
                    id="p1",
                    role="Role",
                    traits=["t1"],
                    communication_style="Direct",
                    goal="Goal",
                ),
            ]
        )
        yaml_text = schema.to_yaml()
        assert "personas:" in yaml_text
        assert "role: Role" in yaml_text

    def test_round_trip_yaml_with_language_channel(self) -> None:
        """PersonasSchema YAML round-trip preserves language and channel fields."""
        original = PersonasSchema(
            personas=[
                PersonaProfile(
                    id="zh-voice",
                    role="Chinese voice user",
                    traits=["fluent"],
                    communication_style="Conversational",
                    goal="Get help in Chinese via voice",
                    language="zh",
                    channel="voice",
                ),
            ]
        )
        yaml_text = original.to_yaml()
        restored = PersonasSchema.from_yaml(yaml_text)
        assert restored.personas[0].language == "zh"
        assert restored.personas[0].channel == "voice"
        assert restored == original

    def test_from_yaml_missing_language_channel_gets_defaults(self) -> None:
        """YAML without language/channel fields parses with defaults applied."""
        yaml_text = (
            "personas:\n"
            "- id: old-persona\n"
            "  role: Legacy user\n"
            "  traits:\n"
            "  - legacy\n"
            "  communication_style: Old style\n"
            "  goal: Legacy goal\n"
        )
        schema = PersonasSchema.from_yaml(yaml_text)
        assert len(schema.personas) == 1
        assert schema.personas[0].language == "en"
        assert schema.personas[0].channel == "text"

    def test_multiple_personas_round_trip(self) -> None:
        """Multiple personas round-trip correctly through YAML."""
        original = PersonasSchema(
            personas=[
                PersonaProfile(
                    id="p1",
                    role="Role 1",
                    traits=["t1"],
                    communication_style="Style 1",
                    goal="Goal 1",
                ),
                PersonaProfile(
                    id="p2",
                    role="Role 2",
                    traits=["t2", "t3"],
                    communication_style="Style 2",
                    goal="Goal 2",
                    edge_cases=["ec1"],
                ),
            ]
        )
        yaml_text = original.to_yaml()
        restored = PersonasSchema.from_yaml(yaml_text)
        assert len(restored.personas) == 2
        assert restored.personas[0].id == "p1"
        assert restored.personas[1].id == "p2"
        assert restored == original


# --- PromptRegistry.load_prompt() personas DB integration ---


class TestPromptRegistryPersonasIntegration:
    """Tests for PromptRegistry loading personas from the database."""

    @pytest.fixture
    async def session_factory(self):
        """Create an in-memory SQLite engine with all tables."""
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

    @pytest.mark.asyncio
    async def test_load_prompt_with_personas(self, session_factory) -> None:
        """load_prompt() loads personas from Persona table when rows exist."""
        from api.registry.service import PromptRegistry
        from api.registry.models import PromptRegistration

        registry = PromptRegistry(session_factory)
        await registry.register(
            PromptRegistration(
                id="test-prompt",
                purpose="Test purpose",
                template="Hello {{ name }}!",
            )
        )

        # Insert a persona row directly in the DB
        async with session_factory() as session:
            session.add(Persona(
                prompt_id="test-prompt",
                persona_id="test-persona",
                role="Test role",
                traits=["trait1"],
                communication_style="Direct",
                goal="Test goal",
                edge_cases=[],
                behavior_criteria=[],
            ))
            await session.commit()

        record = await registry.load_prompt("test-prompt")

        assert len(record.personas) == 1
        assert record.personas[0].id == "test-persona"
        assert record.personas[0].role == "Test role"

    @pytest.mark.asyncio
    async def test_load_prompt_without_personas(self, session_factory) -> None:
        """load_prompt() returns empty personas list when no Persona rows exist."""
        from api.registry.service import PromptRegistry
        from api.registry.models import PromptRegistration

        registry = PromptRegistry(session_factory)
        await registry.register(
            PromptRegistration(
                id="test-prompt",
                purpose="Test purpose",
                template="Hello {{ name }}!",
            )
        )

        record = await registry.load_prompt("test-prompt")

        assert record.personas == []
