"""E2E integration tests for synthesis pipeline and synthetic weight in fitness.

Covers requirements:
- TEST-01: SynthesisEngine.run_synthesis persists failing conversations as TestCases
  with "synthetic" tag, discards passing conversations.
- TEST-02: Synthetic CaseResults receive 0.5x weight multiplier in FitnessAggregator
  relative to human-authored (non-synthetic) cases.
- SYNTH-05/06: Auto-variable generation with priority chain (examples > existing > LLM).

Uses mock-based approach following patterns from tests/e2e/test_ivr_pipeline_mock.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.dataset.models import TestCase
from api.dataset.service import DatasetService
from api.evaluation.aggregator import FitnessAggregator
from api.evaluation.models import CaseResult
from api.registry.models import PromptRegistration, VariableDefinition
from api.registry.service import PromptRegistry
from api.storage.models import Base
from api.synthesis.engine import SynthesisEngine
from api.synthesis.models import (
    PersonaProfile,
    SynthesisConfig,
)
from api.types import LLMResponse, ModelRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(
    content: str | None = "response",
    tool_calls: list[dict] | None = None,
    role: ModelRole = ModelRole.TARGET,
) -> LLMResponse:
    """Create a minimal LLMResponse for mocking."""
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        model_used="mock-model",
        role=role,
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
        timestamp=datetime.now(timezone.utc),
    )


def _make_persona(**overrides: Any) -> PersonaProfile:
    """Create a test persona with sensible defaults."""
    defaults = {
        "id": "test-persona",
        "role": "Test user",
        "traits": ["direct"],
        "communication_style": "concise",
        "goal": "Test the assistant",
        "edge_cases": ["edge1"],
        "behavior_criteria": ["The assistant should respond appropriately"],
    }
    defaults.update(overrides)
    return PersonaProfile(**defaults)


async def _setup_db_services(prompt_id: str = "test-prompt"):
    """Create in-memory DB, register a prompt, and return DatasetService.

    Returns:
        DatasetService backed by in-memory SQLite with the prompt registered.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Register the prompt in the DB so DatasetService can find it
    registry = PromptRegistry(session_factory)
    await registry.register(
        PromptRegistration(
            id=prompt_id,
            purpose="Test prompt",
            template="You are a helpful assistant.",
        )
    )

    return DatasetService(session_factory)


def _build_synthesis_engine(
    meta_responses: list[LLMResponse],
    target_responses: list[LLMResponse],
    scorer_result: CaseResult | list[CaseResult],
    dataset_service: DatasetService,
) -> SynthesisEngine:
    """Build a SynthesisEngine with mocked providers and a real DatasetService.

    Args:
        meta_responses: Ordered LLMResponses for the meta (persona) provider.
        target_responses: Ordered LLMResponses for the target provider.
        scorer_result: CaseResult(s) the judge scorer returns. Single or list.
        dataset_service: Real DatasetService backed by database.

    Returns:
        Configured SynthesisEngine ready for run_synthesis().
    """
    meta_provider = AsyncMock()
    target_provider = AsyncMock()
    judge_scorer = AsyncMock()

    meta_provider.chat_completion.side_effect = meta_responses
    target_provider.chat_completion.side_effect = target_responses

    if isinstance(scorer_result, list):
        judge_scorer.score.side_effect = scorer_result
    else:
        judge_scorer.score.return_value = scorer_result

    return SynthesisEngine(
        meta_provider=meta_provider,
        target_provider=target_provider,
        judge_scorer=judge_scorer,
        dataset_service=dataset_service,
        meta_model="mock-meta",
        target_model="mock-target",
    )


# ===========================================================================
# TestSynthesisPipelinePersistence (TEST-01)
# ===========================================================================


class TestSynthesisPipelinePersistence:
    """E2E tests for synthesis pipeline: simulate -> score -> persist/discard."""

    async def test_failing_conversation_persisted_with_synthetic_tag(self) -> None:
        """TEST-01 core: Failing conversation is persisted with 'synthetic' tag."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        # Persona says something, then ends
        meta_responses = [
            _make_llm_response("I need help with my order", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        # Target responds
        target_responses = [
            _make_llm_response("Sorry, I can't help with that.", role=ModelRole.TARGET),
        ]
        # Judge returns failing score
        scorer_result = CaseResult(
            case_id="", score=-2, passed=False, reason="Failed behavioral criteria"
        )

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        persona = _make_persona()
        config = SynthesisConfig(num_conversations=1, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="You are a helpful assistant.",
            personas=[persona],
            config=config,
            existing_cases=[],
            tools=None,
            mocks=None,
        )

        # Verify persistence totals
        assert result.total_persisted == 1
        assert result.total_discarded == 0

        # Verify persisted case has synthetic tag
        cases = await dataset_service.list_cases(prompt_id)
        assert len(cases) >= 1
        latest_case = cases[-1]
        assert "synthetic" in latest_case.tags

        # Verify conversation record has persisted_case_id
        assert result.conversations[0].persisted_case_id is not None

    async def test_passing_conversation_discarded(self) -> None:
        """TEST-01 passing discard: Passing conversation is NOT persisted."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        meta_responses = [
            _make_llm_response("Hello there", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        target_responses = [
            _make_llm_response("Hello! How can I help?", role=ModelRole.TARGET),
        ]
        # Judge returns passing score
        scorer_result = CaseResult(case_id="", score=0, passed=True, reason="Passed all criteria")

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        persona = _make_persona()
        config = SynthesisConfig(num_conversations=1, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="You are a helpful assistant.",
            personas=[persona],
            config=config,
            existing_cases=[],
            tools=None,
            mocks=None,
        )

        assert result.total_persisted == 0
        assert result.total_discarded == 1

        # No cases should have been written
        cases = await dataset_service.list_cases(prompt_id)
        assert len(cases) == 0

    async def test_multi_persona_mixed_results(self) -> None:
        """TEST-01 multi-persona: Two personas, one failing + one passing."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        # Persona A: one turn + [END]
        # Persona B: one turn + [END]
        meta_responses = [
            # Persona A conversation
            _make_llm_response("I'm frustrated!", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
            # Persona B conversation
            _make_llm_response("Just checking in", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        target_responses = [
            # Response to Persona A
            _make_llm_response("I don't care about your problem.", role=ModelRole.TARGET),
            # Response to Persona B
            _make_llm_response("Everything looks good!", role=ModelRole.TARGET),
        ]
        # Persona A fails, Persona B passes
        scorer_results = [
            CaseResult(case_id="", score=-2, passed=False, reason="Failed"),
            CaseResult(case_id="", score=0, passed=True, reason="Passed"),
        ]

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_results, dataset_service
        )

        persona_a = _make_persona(id="persona-frustrated")
        persona_b = _make_persona(id="persona-friendly")
        config = SynthesisConfig(num_conversations=1, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="You are a helpful assistant.",
            personas=[persona_a, persona_b],
            config=config,
            existing_cases=[],
            tools=None,
            mocks=None,
        )

        assert result.total_persisted == 1
        assert result.total_discarded == 1
        assert result.total_conversations == 2

        # Both persona IDs should appear in conversations
        persona_ids = {conv.persona_id for conv in result.conversations}
        assert "persona-frustrated" in persona_ids
        assert "persona-friendly" in persona_ids


# ===========================================================================
# TestSyntheticWeightInFitness (TEST-02)
# ===========================================================================


class TestSyntheticWeightInFitness:
    """E2E tests for synthetic weight multiplier in FitnessAggregator."""

    def test_synthetic_half_weight_vs_human(self) -> None:
        """TEST-02 weight verification: Synthetic gets exactly 0.5x weight of human."""
        aggregator = FitnessAggregator()

        # Human case: normal tier, score=-2.0
        human_result = CaseResult(case_id="human-1", tier="normal", score=-2.0, synthetic=False)
        human_fitness = aggregator.aggregate([human_result])

        # Synthetic case: normal tier, score=-2.0
        synthetic_result = CaseResult(case_id="synth-1", tier="normal", score=-2.0, synthetic=True)
        synthetic_fitness = aggregator.aggregate([synthetic_result])

        # Human: -2.0 * 1.0 (normal multiplier) = -2.0
        # Synthetic: -2.0 * 1.0 * 0.5 (synthetic halving) = -1.0
        assert human_fitness.score == pytest.approx(-2.0)
        assert synthetic_fitness.score == pytest.approx(-1.0)
        assert synthetic_fitness.score == pytest.approx(0.5 * human_fitness.score)

    def test_mixed_synthetic_human_aggregation(self) -> None:
        """TEST-02 end-to-end weight: Mixed synthetic+human produces correct total."""
        aggregator = FitnessAggregator()

        results = [
            # Human normal: -1.0 * 1.0 = -1.0
            CaseResult(case_id="h1", tier="normal", score=-1.0, synthetic=False),
            # Human normal: -1.0 * 1.0 = -1.0
            CaseResult(case_id="h2", tier="normal", score=-1.0, synthetic=False),
            # Synthetic normal: -1.0 * 1.0 * 0.5 = -0.5
            CaseResult(case_id="s1", tier="normal", score=-1.0, synthetic=True),
        ]

        fitness = aggregator.aggregate(results)

        expected_score = -1.0 + -1.0 + -0.5
        assert fitness.score == pytest.approx(expected_score)
        assert fitness.score == pytest.approx(-2.5)


# ===========================================================================
# TestScenarioContext (SYN-04)
# ===========================================================================


class TestScenarioContext:
    """Tests for scenario_context pass-through in synthesis pipeline."""

    async def test_scenario_context_in_persona_system_prompt(self) -> None:
        """SYN-04: scenario_context appears in persona system prompt."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        # Persona says one thing, then ends
        meta_responses = [
            _make_llm_response("I have a billing issue", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        target_responses = [
            _make_llm_response("Let me help with billing.", role=ModelRole.TARGET),
        ]
        # Passing score so nothing is persisted
        scorer_result = CaseResult(case_id="", score=0, passed=True, reason="OK")

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        persona = _make_persona()
        config = SynthesisConfig(
            num_conversations=1,
            max_turns=10,
            scenario_context="The user is calling about a billing dispute",
        )

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="You are a helpful assistant.",
            personas=[persona],
            config=config,
            existing_cases=[],
            tools=None,
            mocks=None,
        )

        assert result.total_conversations == 1

        # Verify the meta provider received scenario_context in system prompt
        meta_call = engine._meta_provider.chat_completion.call_args_list[0]
        messages = meta_call.kwargs.get("messages") or meta_call[1].get("messages", [])
        system_msg = messages[0]["content"]
        assert "billing dispute" in system_msg
        assert "Scenario Context" in system_msg

    async def test_synthesis_without_scenario_context(self) -> None:
        """Existing behavior preserved: no scenario_context section when None."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        meta_responses = [
            _make_llm_response("Hello", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        target_responses = [
            _make_llm_response("Hi there!", role=ModelRole.TARGET),
        ]
        scorer_result = CaseResult(case_id="", score=0, passed=True, reason="OK")

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        persona = _make_persona()
        config = SynthesisConfig(num_conversations=1, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="You are a helpful assistant.",
            personas=[persona],
            config=config,
            existing_cases=[],
            tools=None,
            mocks=None,
        )

        assert result.total_conversations == 1

        # Verify NO scenario context section in system prompt
        meta_call = engine._meta_provider.chat_completion.call_args_list[0]
        messages = meta_call.kwargs.get("messages") or meta_call[1].get("messages", [])
        system_msg = messages[0]["content"]
        assert "Scenario Context" not in system_msg


# ===========================================================================
# TestAutoVariableGeneration (SYNTH-05/06)
# ===========================================================================


class TestAutoVariableGeneration:
    """Tests for auto-variable generation priority chain in SynthesisEngine.

    Priority chain: examples > existing cases > LLM generation.
    """

    async def test_examples_based_resolution_no_llm_call(self) -> None:
        """When variable_definitions have examples, pick from examples. No LLM call."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        meta_responses = [
            _make_llm_response("Hi there", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        target_responses = [
            _make_llm_response("Hello!", role=ModelRole.TARGET),
        ]
        scorer_result = CaseResult(case_id="", score=0, passed=True, reason="OK")

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        variable_definitions = [
            VariableDefinition(
                name="stock",
                var_type="string",
                description="Stock ticker symbol",
                examples=["AAPL", "GOOG", "MSFT"],
            ),
            VariableDefinition(
                name="currency",
                var_type="string",
                description="Currency code",
                examples=["USD", "EUR"],
            ),
        ]

        persona = _make_persona()
        config = SynthesisConfig(num_conversations=1, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="You are a helpful assistant. Stock: {{ stock }}, Currency: {{ currency }}",
            personas=[persona],
            config=config,
            existing_cases=[],
            tools=None,
            mocks=None,
            variable_definitions=variable_definitions,
            prompt_purpose="Stock information assistant",
        )

        assert result.total_conversations == 1
        conv = result.conversations[0]
        # Variables should be from the examples lists
        assert conv.variables["stock"] in ["AAPL", "GOOG", "MSFT"]
        assert conv.variables["currency"] in ["USD", "EUR"]

    async def test_existing_cases_resolution_no_examples(self) -> None:
        """When no examples but existing cases exist, sample from cases (existing behavior)."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        meta_responses = [
            _make_llm_response("Hello", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        target_responses = [
            _make_llm_response("Hi!", role=ModelRole.TARGET),
        ]
        scorer_result = CaseResult(case_id="", score=0, passed=True, reason="OK")

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        # Variable definitions without examples
        variable_definitions = [
            VariableDefinition(
                name="stock",
                var_type="string",
                description="Stock ticker symbol",
            ),
        ]

        # Existing cases with variables
        existing_cases = [
            TestCase(
                variables={"stock": "TSLA", "extra": "value"},
                chat_history=[{"role": "user", "content": "test"}],
            ),
        ]

        persona = _make_persona()
        config = SynthesisConfig(num_conversations=1, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="Stock: {{ stock }}",
            personas=[persona],
            config=config,
            existing_cases=existing_cases,
            tools=None,
            mocks=None,
            variable_definitions=variable_definitions,
            prompt_purpose="Stock assistant",
        )

        assert result.total_conversations == 1
        conv = result.conversations[0]
        # Should sample from existing cases
        assert conv.variables["stock"] == "TSLA"

    async def test_llm_generation_no_examples_no_cases(self) -> None:
        """When no examples AND no existing cases, call LLM to generate values."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        # Meta provider: first call is for variable generation (returns JSON),
        # then normal conversation calls
        llm_var_response = _make_llm_response(
            json.dumps({"stock": "NVDA", "amount": 100}),
            role=ModelRole.META,
        )
        meta_responses = [
            llm_var_response,  # Variable generation call
            _make_llm_response("Hello", role=ModelRole.META),  # Conversation
            _make_llm_response("[END]", role=ModelRole.META),  # End
        ]
        target_responses = [
            _make_llm_response("Hi!", role=ModelRole.TARGET),
        ]
        scorer_result = CaseResult(case_id="", score=0, passed=True, reason="OK")

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        variable_definitions = [
            VariableDefinition(
                name="stock",
                var_type="string",
                description="Stock ticker symbol",
            ),
            VariableDefinition(
                name="amount",
                var_type="integer",
                description="Number of shares",
                constraints={"min": 1, "max": 1000},
            ),
        ]

        persona = _make_persona()
        config = SynthesisConfig(num_conversations=1, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="Stock: {{ stock }}, Amount: {{ amount }}",
            personas=[persona],
            config=config,
            existing_cases=[],
            tools=None,
            mocks=None,
            variable_definitions=variable_definitions,
            prompt_purpose="Stock trading assistant",
        )

        assert result.total_conversations == 1
        conv = result.conversations[0]
        # LLM generated values
        assert conv.variables["stock"] == "NVDA"
        assert conv.variables["amount"] == 100

        # Verify the meta provider was called for variable generation
        # The first call should be the LLM generation call (before conversation)
        first_call = engine._meta_provider.chat_completion.call_args_list[0]
        first_messages = first_call.kwargs.get("messages") or first_call[1].get("messages", [])
        # The variable generation prompt should contain variable metadata
        gen_prompt = " ".join(msg.get("content", "") for msg in first_messages)
        assert "stock" in gen_prompt.lower()

    async def test_examples_override_existing_cases(self) -> None:
        """Examples take priority over existing cases for the same variable."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        meta_responses = [
            _make_llm_response("Hi", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        target_responses = [
            _make_llm_response("Hello!", role=ModelRole.TARGET),
        ]
        scorer_result = CaseResult(case_id="", score=0, passed=True, reason="OK")

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        # Variable definitions WITH examples
        variable_definitions = [
            VariableDefinition(
                name="stock",
                var_type="string",
                examples=["AAPL", "GOOG"],
            ),
        ]

        # Existing cases with DIFFERENT variable values
        existing_cases = [
            TestCase(
                variables={"stock": "TSLA"},
                chat_history=[{"role": "user", "content": "test"}],
            ),
        ]

        persona = _make_persona()
        config = SynthesisConfig(num_conversations=1, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="Stock: {{ stock }}",
            personas=[persona],
            config=config,
            existing_cases=existing_cases,
            tools=None,
            mocks=None,
            variable_definitions=variable_definitions,
            prompt_purpose="",
        )

        conv = result.conversations[0]
        # Should use examples, NOT existing cases
        assert conv.variables["stock"] in ["AAPL", "GOOG"]
        assert conv.variables["stock"] != "TSLA"

    async def test_mixed_scenario_examples_and_fallback(self) -> None:
        """Some variables have examples, others fall through to existing cases."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        meta_responses = [
            _make_llm_response("Hi", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        target_responses = [
            _make_llm_response("Hello!", role=ModelRole.TARGET),
        ]
        scorer_result = CaseResult(case_id="", score=0, passed=True, reason="OK")

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        # stock has examples, currency does NOT
        variable_definitions = [
            VariableDefinition(
                name="stock",
                var_type="string",
                examples=["AAPL", "GOOG"],
            ),
            VariableDefinition(
                name="currency",
                var_type="string",
                description="Currency code",
            ),
        ]

        # Existing cases have currency
        existing_cases = [
            TestCase(
                variables={"stock": "TSLA", "currency": "GBP"},
                chat_history=[{"role": "user", "content": "test"}],
            ),
        ]

        persona = _make_persona()
        config = SynthesisConfig(num_conversations=1, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="Stock: {{ stock }}, Currency: {{ currency }}",
            personas=[persona],
            config=config,
            existing_cases=existing_cases,
            tools=None,
            mocks=None,
            variable_definitions=variable_definitions,
            prompt_purpose="Stock assistant",
        )

        conv = result.conversations[0]
        # stock from examples
        assert conv.variables["stock"] in ["AAPL", "GOOG"]
        # currency from existing cases
        assert conv.variables["currency"] == "GBP"

    async def test_variable_generation_once_per_run(self) -> None:
        """Variable generation happens once per run_synthesis call, not per conversation."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        # Two conversations: persona says something + [END], repeated twice
        meta_responses = [
            _make_llm_response("Q1", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
            _make_llm_response("Q2", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        target_responses = [
            _make_llm_response("A1", role=ModelRole.TARGET),
            _make_llm_response("A2", role=ModelRole.TARGET),
        ]
        scorer_result = CaseResult(case_id="", score=0, passed=True, reason="OK")

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        variable_definitions = [
            VariableDefinition(
                name="stock",
                var_type="string",
                examples=["AAPL"],
            ),
        ]

        persona = _make_persona()
        # 2 conversations
        config = SynthesisConfig(num_conversations=2, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="Stock: {{ stock }}",
            personas=[persona],
            config=config,
            existing_cases=[],
            tools=None,
            mocks=None,
            variable_definitions=variable_definitions,
            prompt_purpose="",
        )

        assert result.total_conversations == 2
        # Both conversations should use the SAME variable values
        assert result.conversations[0].variables == result.conversations[1].variables

    async def test_template_validation_with_generated_variables(self) -> None:
        """Generated variables are validated by rendering through TemplateRenderer."""
        prompt_id = "test-prompt"
        dataset_service = await _setup_db_services(prompt_id)

        meta_responses = [
            _make_llm_response("Hi", role=ModelRole.META),
            _make_llm_response("[END]", role=ModelRole.META),
        ]
        target_responses = [
            _make_llm_response("Hello!", role=ModelRole.TARGET),
        ]
        scorer_result = CaseResult(case_id="", score=0, passed=True, reason="OK")

        engine = _build_synthesis_engine(
            meta_responses, target_responses, scorer_result, dataset_service
        )

        variable_definitions = [
            VariableDefinition(
                name="name",
                var_type="string",
                examples=["Alice"],
            ),
        ]

        persona = _make_persona()
        config = SynthesisConfig(num_conversations=1, max_turns=10)

        result = await engine.run_synthesis(
            prompt_id=prompt_id,
            prompt_template="Hello {{ name }}, welcome!",
            personas=[persona],
            config=config,
            existing_cases=[],
            tools=None,
            mocks=None,
            variable_definitions=variable_definitions,
            prompt_purpose="Greeting bot",
        )

        assert result.total_conversations == 1
        # Variable should render successfully in the template
        assert result.conversations[0].variables["name"] == "Alice"
