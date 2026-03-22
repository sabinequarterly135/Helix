"""Tests for the RCC (Refinement through Critical Conversation) engine.

Tests use AsyncMock for the LiteLLMProvider and real instances of
TemplateValidator and CostTracker (both are pure logic, no I/O).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from api.evaluation.models import (
    CaseResult,
    EvaluationReport,
    FitnessScore,
)
from api.evaluation.validator import TemplateValidator
from api.evolution.models import Candidate
from api.evolution.rcc import RCCEngine
from api.gateway.litellm_provider import LiteLLMProvider
from api.gateway.cost import CostTracker
from api.types import LLMResponse, ModelRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(content: str) -> LLMResponse:
    """Build a minimal LLMResponse for mocking."""
    return LLMResponse(
        content=content,
        model_used="test-meta-model",
        role=ModelRole.META,
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
        timestamp=datetime.now(timezone.utc),
    )


def _make_parent(
    template: str = "Hello {{ name }}, your role is {{ role }}.",
    fitness: float = 0.7,
    case_results: list[CaseResult] | None = None,
) -> Candidate:
    """Build a parent Candidate with optional evaluation."""
    if case_results is None:
        case_results = [
            CaseResult(case_id="c1", score=1.0, passed=True, reason="ok"),
            CaseResult(
                case_id="c2",
                tier="critical",
                score=0.0,
                passed=False,
                reason="Wrong greeting format",
            ),
        ]
    report = EvaluationReport(
        fitness=FitnessScore(score=fitness),
        case_results=case_results,
        total_cases=len(case_results),
    )
    return Candidate(
        template=template,
        fitness_score=fitness,
        evaluation=report,
    )


def _build_engine(
    mock_client: AsyncMock,
    cost_tracker: CostTracker | None = None,
    max_retries: int = 3,
) -> RCCEngine:
    """Build an RCCEngine with the given mock client."""
    return RCCEngine(
        client=mock_client,
        cost_tracker=cost_tracker or CostTracker(),
        validator=TemplateValidator(),
        meta_model="test-meta-model",
        max_retries=max_retries,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSingleTurnRCC:
    """n_seq=1: critic called once, author called once."""

    @pytest.mark.asyncio
    async def test_single_turn_rcc(self):
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            _make_llm_response("The greeting is too generic."),
            _make_llm_response(
                "<revised_template>Welcome {{ name }}, your role is {{ role }}!</revised_template>"
            ),
        ]

        engine = _build_engine(mock_client)
        parent = _make_parent()

        candidate = await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=1,
            generation=1,
        )

        assert candidate.template == "Welcome {{ name }}, your role is {{ role }}!"
        assert mock_client.chat_completion.call_count == 2


class TestMultiTurnRCC:
    """n_seq=3: critic/author called 3 times each."""

    @pytest.mark.asyncio
    async def test_multi_turn_rcc(self):
        mock_client = AsyncMock(spec=LiteLLMProvider)
        # 3 turns x 2 calls each = 6 total calls
        mock_client.chat_completion.side_effect = [
            # Turn 1
            _make_llm_response("Critique turn 1"),
            _make_llm_response("<revised_template>Rev1 {{ name }} {{ role }}</revised_template>"),
            # Turn 2
            _make_llm_response("Critique turn 2"),
            _make_llm_response("<revised_template>Rev2 {{ name }} {{ role }}</revised_template>"),
            # Turn 3
            _make_llm_response("Critique turn 3"),
            _make_llm_response("<revised_template>Rev3 {{ name }} {{ role }}</revised_template>"),
        ]

        engine = _build_engine(mock_client)
        parent = _make_parent()

        candidate = await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=3,
            generation=2,
        )

        # Final template is from last turn
        assert candidate.template == "Rev3 {{ name }} {{ role }}"
        assert mock_client.chat_completion.call_count == 6


class TestNoParentFreshGeneration:
    """Empty parents list triggers fresh generation."""

    @pytest.mark.asyncio
    async def test_no_parent_fresh_generation(self):
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            _make_llm_response(
                "<revised_template>Fresh {{ name }} prompt for {{ role }}</revised_template>"
            ),
        ]

        engine = _build_engine(mock_client)

        candidate = await engine.run_conversation(
            parents=[],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=3,
            generation=1,
        )

        # Only one LLM call (fresh generation), not 6 (critic+author x 3)
        assert mock_client.chat_completion.call_count == 1
        assert candidate.template == "Fresh {{ name }} prompt for {{ role }}"
        assert candidate.parent_ids == []
        assert candidate.generation == 1


class TestVariablePreservationRetry:
    """Author drops a variable; retry succeeds on second attempt."""

    @pytest.mark.asyncio
    async def test_variable_preservation_retry(self):
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            # Critic
            _make_llm_response("The prompt needs improvement."),
            # Author attempt 1: drops {{ role }}
            _make_llm_response("<revised_template>Hello {{ name }}!</revised_template>"),
            # Author attempt 2 (retry): includes both variables
            _make_llm_response(
                "<revised_template>Hello {{ name }}, assigned {{ role }}.</revised_template>"
            ),
        ]

        engine = _build_engine(mock_client, max_retries=3)
        parent = _make_parent()

        candidate = await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=1,
            generation=1,
        )

        # 1 critic + 2 author attempts = 3 calls
        assert mock_client.chat_completion.call_count == 3
        assert candidate.template == "Hello {{ name }}, assigned {{ role }}."


class TestAllRetriesFailKeepsPrevious:
    """All retries produce invalid templates; falls back to previous template."""

    @pytest.mark.asyncio
    async def test_all_retries_fail_keeps_previous(self):
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            # Critic
            _make_llm_response("Issues found."),
            # All 3 author attempts drop {{ role }}
            _make_llm_response("<revised_template>Fail1 {{ name }}</revised_template>"),
            _make_llm_response("<revised_template>Fail2 {{ name }}</revised_template>"),
            _make_llm_response("<revised_template>Fail3 {{ name }}</revised_template>"),
        ]

        engine = _build_engine(mock_client, max_retries=3)
        parent = _make_parent(template="Hello {{ name }}, your role is {{ role }}.")

        candidate = await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=1,
            generation=1,
        )

        # Falls back to parent's template (previous valid one)
        assert candidate.template == "Hello {{ name }}, your role is {{ role }}."
        # 1 critic + 3 failed author attempts = 4 calls
        assert mock_client.chat_completion.call_count == 4


class TestTemplateExtraction:
    """Template extraction from LLM response content."""

    @pytest.mark.asyncio
    async def test_template_extraction_with_delimiters(self):
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            _make_llm_response("Critique here."),
            _make_llm_response(
                "Sure, here is the revised template:\n\n"
                "<revised_template>\nHello {{ name }}, welcome as {{ role }}!\n</revised_template>\n\n"
                "I made the greeting more welcoming."
            ),
        ]

        engine = _build_engine(mock_client)
        parent = _make_parent()

        candidate = await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=1,
            generation=1,
        )

        assert candidate.template == "Hello {{ name }}, welcome as {{ role }}!"

    @pytest.mark.asyncio
    async def test_template_extraction_without_delimiters(self):
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            _make_llm_response("Critique here."),
            _make_llm_response("Hello {{ name }}, welcome as {{ role }}!"),
        ]

        engine = _build_engine(mock_client)
        parent = _make_parent()

        candidate = await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=1,
            generation=1,
        )

        # Uses full content when no delimiters
        assert candidate.template == "Hello {{ name }}, welcome as {{ role }}!"


class TestCandidateLineage:
    """Candidate tracks parent_ids and generation number."""

    @pytest.mark.asyncio
    async def test_candidate_tracks_lineage(self):
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            _make_llm_response("Critique."),
            _make_llm_response("<revised_template>{{ name }} {{ role }}</revised_template>"),
        ]

        engine = _build_engine(mock_client)
        parent1 = _make_parent(fitness=0.8)
        parent2 = _make_parent(fitness=0.6)

        candidate = await engine.run_conversation(
            parents=[parent1, parent2],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=1,
            generation=5,
        )

        assert candidate.generation == 5
        assert parent1.id in candidate.parent_ids
        assert parent2.id in candidate.parent_ids
        assert len(candidate.parent_ids) == 2


class TestCostTrackerRecordsAllCalls:
    """Cost tracker has records for all meta-model calls."""

    @pytest.mark.asyncio
    async def test_cost_tracker_records_all_calls(self):
        mock_client = AsyncMock(spec=LiteLLMProvider)
        # n_seq=2: 2 critic + 2 author = 4 calls
        mock_client.chat_completion.side_effect = [
            _make_llm_response("Critique 1"),
            _make_llm_response("<revised_template>T1 {{ name }} {{ role }}</revised_template>"),
            _make_llm_response("Critique 2"),
            _make_llm_response("<revised_template>T2 {{ name }} {{ role }}</revised_template>"),
        ]

        cost_tracker = CostTracker()
        engine = _build_engine(mock_client, cost_tracker=cost_tracker)
        parent = _make_parent()

        await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=2,
            generation=1,
        )

        summary = cost_tracker.summary()
        assert summary["total_calls"] == 4
        assert summary["total_cost_usd"] == pytest.approx(0.004)


class TestFailingCaseFormatting:
    """Failing cases are formatted with case_id, tier, score, reason."""

    def test_format_failing_cases(self):
        case_results = [
            CaseResult(
                case_id="c1",
                tier="critical",
                score=0.0,
                passed=False,
                reason="Wrong output format",
            ),
            CaseResult(case_id="c2", score=1.0, passed=True, reason="ok"),
            CaseResult(
                case_id="c3",
                tier="normal",
                score=0.3,
                passed=False,
                reason="Missing details",
            ),
        ]

        result = RCCEngine._format_failing_cases(case_results)
        assert "c1" in result
        assert "critical" in result
        assert "Wrong output format" in result
        assert "c3" in result
        assert "Missing details" in result
        # c2 should NOT be in failing cases (it passed)
        assert "c2" not in result

    def test_format_failing_cases_none_failing(self):
        case_results = [
            CaseResult(case_id="c1", score=1.0, passed=True, reason="ok"),
        ]
        result = RCCEngine._format_failing_cases(case_results)
        assert "No failing cases" in result


class TestPassingCasesSummary:
    """Passing cases are summarized (not full detail) for context."""

    def test_format_passing_summary(self):
        case_results = [
            CaseResult(case_id="c1", score=1.0, passed=True, reason="ok"),
            CaseResult(case_id="c2", score=0.0, passed=False, reason="fail"),
            CaseResult(case_id="c3", score=1.0, passed=True, reason="good"),
        ]

        result = RCCEngine._format_passing_summary(case_results)
        assert "2 case(s) passed" in result
        assert "c1" in result
        assert "c3" in result

    def test_format_passing_summary_none_passing(self):
        case_results = [
            CaseResult(case_id="c1", score=0.0, passed=False, reason="fail"),
        ]
        result = RCCEngine._format_passing_summary(case_results)
        assert "No passing cases" in result


class TestRetryMessageDistinguishesRenames:
    """Retry messages should distinguish renamed vars from dropped vars."""

    @pytest.mark.asyncio
    async def test_retry_mentions_rename_when_variable_renamed(self):
        """When author renames a variable, retry message should mention the rename."""
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            # Critic
            _make_llm_response("The prompt needs improvement."),
            # Author attempt 1: renames role_name -> role_title (string-similar)
            _make_llm_response(
                "<revised_template>Hello {{ name }}, your title is {{ role_title }}.</revised_template>"
            ),
            # Author attempt 2 (retry): correct
            _make_llm_response(
                "<revised_template>Hello {{ name }}, your role is {{ role_name }}.</revised_template>"
            ),
        ]

        engine = _build_engine(mock_client, max_retries=3)
        parent = _make_parent(
            template="Hello {{ name }}, your role is {{ role_name }}.",
        )

        await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role_name }}.",
            anchor_variables={"name", "role_name"},
            purpose="Generate greetings",
            n_seq=1,
            generation=1,
        )

        # The retry call (3rd call = index 2) should mention "renamed" or "RENAMED"
        retry_call_args = mock_client.chat_completion.call_args_list[2]
        messages = retry_call_args.kwargs.get("messages") or retry_call_args[0][0]
        user_content = messages[1]["content"]
        # Should mention the rename, not just "dropped"
        assert "role_name" in user_content
        assert "role_title" in user_content
        # Should contain rename-related language
        assert "renamed" in user_content.lower() or "RENAMED" in user_content

    @pytest.mark.asyncio
    async def test_retry_says_dropped_when_variable_simply_removed(self):
        """When author just drops a variable with no rename, message says dropped."""
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            _make_llm_response("Critique."),
            # Author drops role entirely (no similar new var)
            _make_llm_response("<revised_template>Hello {{ name }}!</revised_template>"),
            # Retry: correct
            _make_llm_response(
                "<revised_template>Hello {{ name }}, role: {{ role }}.</revised_template>"
            ),
        ]

        engine = _build_engine(mock_client, max_retries=3)
        parent = _make_parent()

        await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=1,
            generation=1,
        )

        retry_call_args = mock_client.chat_completion.call_args_list[2]
        messages = retry_call_args.kwargs.get("messages") or retry_call_args[0][0]
        user_content = messages[1]["content"]
        assert "dropped" in user_content.lower()
        assert "role" in user_content


class TestCriticPromptIncludesVariables:
    """Critic prompt must include explicit variable names to prevent Gemini renames."""

    @pytest.mark.asyncio
    async def test_critic_system_prompt_contains_variable_names(self):
        """CRITIC_SYSTEM_PROMPT sent to LLM must list the anchor variable names."""
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            _make_llm_response("Critique."),
            _make_llm_response("<revised_template>{{ name }} {{ role }}</revised_template>"),
        ]
        engine = _build_engine(mock_client)
        parent = _make_parent()

        await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=1,
            generation=1,
        )

        # First call is critic; check system message content
        critic_call_args = mock_client.chat_completion.call_args_list[0]
        messages = critic_call_args.kwargs.get("messages") or critic_call_args[0][0]
        system_content = messages[0]["content"]
        assert "name" in system_content
        assert "role" in system_content

    @pytest.mark.asyncio
    async def test_critic_user_prompt_contains_variable_names(self):
        """CRITIC_USER_PROMPT sent to LLM must list the anchor variable names."""
        mock_client = AsyncMock(spec=LiteLLMProvider)
        mock_client.chat_completion.side_effect = [
            _make_llm_response("Critique."),
            _make_llm_response("<revised_template>{{ name }} {{ role }}</revised_template>"),
        ]
        engine = _build_engine(mock_client)
        parent = _make_parent()

        await engine.run_conversation(
            parents=[parent],
            original_template="Hello {{ name }}, your role is {{ role }}.",
            anchor_variables={"name", "role"},
            purpose="Generate greetings",
            n_seq=1,
            generation=1,
        )

        critic_call_args = mock_client.chat_completion.call_args_list[0]
        messages = critic_call_args.kwargs.get("messages") or critic_call_args[0][0]
        user_content = messages[1]["content"]
        assert "name" in user_content
        assert "role" in user_content
