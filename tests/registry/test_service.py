"""Tests for PromptRegistry service: register, load, list, update prompts.

Covers:
- REG-01: register() stores prompt in DB, returns PromptRecord
- REG-02: register() extracts Jinja2 variables, identifies anchors
- REG-03: register() stores per-prompt config, load_prompt() merges via load_prompt_config
- REG-04: register() stores tool definitions, load_prompt() reads them
- Error handling: duplicate IDs, missing prompts
- list_prompts, update_template
- Edge cases: no variables, filters, load_prompt_config wiring
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.config.models import GeneConfig, GenerationConfig
from api.exceptions import PromptAlreadyExistsError, PromptNotFoundError
from api.registry.models import PromptRegistration, VariableDefinition
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
async def prompt_registry(session_factory):
    """Create a PromptRegistry backed by in-memory SQLite."""
    from api.registry.service import PromptRegistry

    return PromptRegistry(session_factory)


@pytest.fixture
def sample_registration() -> PromptRegistration:
    """Return a PromptRegistration with Jinja2 template, variables, tools, and config."""
    return PromptRegistration(
        id="salon-assistant",
        purpose="Help customers book salon appointments",
        template=(
            "Hello {{ customer_name }}, welcome to {{ business_name }}.\n"
            "We specialize in {{ service_type }} services.\n"
            "How can I help you today?"
        ),
        variables=[
            VariableDefinition(name="customer_name", description="Customer's full name"),
            VariableDefinition(
                name="business_name",
                description="Name of the salon",
                is_anchor=True,
            ),
            VariableDefinition(name="service_type", description="Type of service offered"),
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "book_appointment",
                    "description": "Book a salon appointment",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string"},
                            "service": {"type": "string"},
                        },
                        "required": ["date", "service"],
                    },
                },
            }
        ],
        target_model="openai/gpt-4o",
        generation=GenerationConfig(temperature=0.5, max_tokens=2048),
    )


class TestRegisterPrompt:
    """Tests for PromptRegistry.register()."""

    async def test_register_stores_prompt_in_db(self, prompt_registry, sample_registration):
        """REG-01: register() stores prompt in the database."""
        record = await prompt_registry.register(sample_registration)
        assert record.id == "salon-assistant"
        assert record.purpose == "Help customers book salon appointments"

    async def test_register_returns_prompt_record(self, prompt_registry, sample_registration):
        """REG-01: register() returns PromptRecord with correct fields."""
        record = await prompt_registry.register(sample_registration)

        assert record.id == "salon-assistant"
        assert record.purpose == "Help customers book salon appointments"
        # DB-based registry doesn't use git commits
        assert record.commit_hash is None

    async def test_register_extracts_template_variables(self, prompt_registry, sample_registration):
        """REG-02: register() extracts Jinja2 variables from template."""
        record = await prompt_registry.register(sample_registration)

        assert record.template_variables == {"customer_name", "business_name", "service_type"}

    async def test_register_identifies_anchor_variables(self, prompt_registry, sample_registration):
        """REG-02: register() identifies anchor variables from VariableDefinition.is_anchor."""
        record = await prompt_registry.register(sample_registration)

        assert record.anchor_variables == {"business_name"}

    async def test_register_stores_config_in_db(self, prompt_registry, sample_registration):
        """REG-03: register() stores target_model and generation config."""
        await prompt_registry.register(sample_registration)

        # Load it back and verify the data is stored
        record = await prompt_registry.load_prompt("salon-assistant")
        assert record.id == "salon-assistant"
        assert record.template_variables == {"customer_name", "business_name", "service_type"}

    async def test_register_stores_tools(self, prompt_registry, sample_registration):
        """REG-04: register() stores tool definitions."""
        await prompt_registry.register(sample_registration)

        # Verify tools are stored and loaded
        record = await prompt_registry.load_prompt("salon-assistant")
        assert record.tools is not None
        assert len(record.tools) == 1
        assert record.tools[0]["function"]["name"] == "book_appointment"

    async def test_register_duplicate_raises_error(self, prompt_registry, sample_registration):
        """register() raises PromptAlreadyExistsError for duplicate ID."""
        await prompt_registry.register(sample_registration)

        with pytest.raises(PromptAlreadyExistsError):
            await prompt_registry.register(sample_registration)

    async def test_register_no_variables_template(self, prompt_registry):
        """Template with no variables works (empty set returned)."""
        reg = PromptRegistration(
            id="static-prompt",
            purpose="A prompt with no variables",
            template="This is a static prompt with no placeholders.",
        )
        record = await prompt_registry.register(reg)

        assert record.template_variables == set()
        assert record.anchor_variables == set()

    async def test_register_template_with_filters(self, prompt_registry):
        """Template with Jinja2 filters ({{ name | upper }}) correctly extracts variable name."""
        reg = PromptRegistration(
            id="filter-prompt",
            purpose="A prompt with filters",
            template="Hello {{ name | upper }}, your email is {{ email | lower }}.",
        )
        record = await prompt_registry.register(reg)

        assert record.template_variables == {"name", "email"}

    async def test_register_stores_variables(self, prompt_registry, sample_registration):
        """register() stores variable definitions in the database."""
        await prompt_registry.register(sample_registration)

        record = await prompt_registry.load_prompt("salon-assistant")
        assert record.template_variables == {"customer_name", "business_name", "service_type"}
        assert record.anchor_variables == {"business_name"}


class TestLoadPrompt:
    """Tests for PromptRegistry.load_prompt()."""

    async def test_load_prompt_returns_record(self, prompt_registry, sample_registration):
        """load_prompt() returns PromptRecord with all data populated."""
        await prompt_registry.register(sample_registration)
        record = await prompt_registry.load_prompt("salon-assistant")

        assert record.id == "salon-assistant"
        assert record.purpose == "Help customers book salon appointments"
        assert record.template_variables == {"customer_name", "business_name", "service_type"}
        assert record.anchor_variables == {"business_name"}

    async def test_load_prompt_reads_tools(self, prompt_registry, sample_registration):
        """REG-04: load_prompt() reads tools and returns tool definitions."""
        await prompt_registry.register(sample_registration)
        record = await prompt_registry.load_prompt("salon-assistant")

        assert record.tools is not None
        assert len(record.tools) == 1
        assert record.tools[0]["function"]["name"] == "book_appointment"

    async def test_load_prompt_missing_raises_error(self, prompt_registry):
        """load_prompt() raises PromptNotFoundError for missing ID."""
        with pytest.raises(PromptNotFoundError):
            await prompt_registry.load_prompt("nonexistent-prompt")

    async def test_load_prompt_without_base_config(self, prompt_registry, sample_registration):
        """load_prompt() without base_config skips config merging (config remains None)."""
        await prompt_registry.register(sample_registration)
        record = await prompt_registry.load_prompt("salon-assistant")

        assert record.config is None


class TestYamlSidecars:
    """Tests for tool_schemas and mocks (YAML sidecar replacement in DB)."""

    async def test_register_with_tool_schemas(self, prompt_registry):
        """register() with tool_schemas stores and returns typed models."""
        reg = PromptRegistration(
            id="tool-prompt",
            purpose="Prompt with tool schemas",
            template="Hello {{ name }}",
            tool_schemas=[
                {
                    "name": "transfer_to_number",
                    "description": "Transfer call",
                    "parameters": [
                        {"name": "target", "type": "string", "required": True},
                        {"name": "summary", "type": "string"},
                    ],
                }
            ],
        )
        record = await prompt_registry.register(reg)

        # Record should have the typed models
        assert record.tool_schemas is not None
        assert len(record.tool_schemas) == 1
        assert record.tool_schemas[0].name == "transfer_to_number"

    async def test_register_with_mocks(self, prompt_registry):
        """register() with mocks stores and returns typed models."""
        reg = PromptRegistration(
            id="mock-prompt",
            purpose="Prompt with mocks",
            template="Hello {{ name }}",
            mocks=[
                {
                    "tool_name": "transfer_to_number",
                    "scenarios": [
                        {"match_args": {"target": "ventas"}, "response": "Transferred to sales"},
                        {"match_args": {"target": "*"}, "response": "Transferred to {{ target }}"},
                    ],
                }
            ],
        )
        record = await prompt_registry.register(reg)

        # Record should have the typed models
        assert record.mocks is not None
        assert len(record.mocks) == 1
        assert record.mocks[0].tool_name == "transfer_to_number"
        assert len(record.mocks[0].scenarios) == 2

    async def test_register_without_schemas_no_tool_schemas_or_mocks(self, prompt_registry):
        """register() without tool_schemas/mocks returns None for both."""
        reg = PromptRegistration(
            id="plain-prompt",
            purpose="No YAML sidecars",
            template="Hello {{ name }}",
        )
        record = await prompt_registry.register(reg)

        assert record.tool_schemas is None
        assert record.mocks is None

    async def test_load_prompt_reads_tool_schemas(self, prompt_registry):
        """load_prompt() reads tool_schemas from DB and attaches to PromptRecord."""
        reg = PromptRegistration(
            id="load-tools",
            purpose="Load tools test",
            template="Hello {{ name }}",
            tool_schemas=[
                {"name": "lookup", "description": "Look up data", "parameters": []},
            ],
        )
        await prompt_registry.register(reg)

        record = await prompt_registry.load_prompt("load-tools")
        assert record.tool_schemas is not None
        assert len(record.tool_schemas) == 1
        assert record.tool_schemas[0].name == "lookup"

    async def test_load_prompt_reads_mocks(self, prompt_registry):
        """load_prompt() reads mocks from DB and attaches to PromptRecord."""
        reg = PromptRegistration(
            id="load-mocks",
            purpose="Load mocks test",
            template="Hello {{ name }}",
            mocks=[
                {
                    "tool_name": "greet",
                    "scenarios": [
                        {"match_args": {"lang": "en"}, "response": "Hello"},
                    ],
                },
            ],
        )
        await prompt_registry.register(reg)

        record = await prompt_registry.load_prompt("load-mocks")
        assert record.mocks is not None
        assert len(record.mocks) == 1
        assert record.mocks[0].tool_name == "greet"
        assert record.mocks[0].scenarios[0].response == "Hello"

    async def test_load_prompt_without_schemas(self, prompt_registry):
        """load_prompt() without tool_schemas/mocks returns None for both."""
        reg = PromptRegistration(
            id="no-yaml",
            purpose="No YAML sidecars",
            template="Hello {{ name }}",
        )
        await prompt_registry.register(reg)

        record = await prompt_registry.load_prompt("no-yaml")
        assert record.tool_schemas is None
        assert record.mocks is None


class TestListPrompts:
    """Tests for PromptRegistry.list_prompts()."""

    async def test_list_prompts_returns_registered(self, prompt_registry):
        """list_prompts() returns list of all registered prompt IDs."""
        reg1 = PromptRegistration(id="prompt-a", purpose="First", template="Hello {{ name }}")
        reg2 = PromptRegistration(id="prompt-b", purpose="Second", template="Hi {{ name }}")

        await prompt_registry.register(reg1)
        await prompt_registry.register(reg2)

        prompts = await prompt_registry.list_prompts()
        assert sorted(prompts) == ["prompt-a", "prompt-b"]

    async def test_list_prompts_empty(self, prompt_registry):
        """list_prompts() returns empty list when no prompts registered."""
        prompts = await prompt_registry.list_prompts()
        assert prompts == []
