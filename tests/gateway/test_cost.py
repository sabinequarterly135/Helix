"""Tests for CostTracker and estimate_cost_from_tokens.

COST-01: System tracks total LLM API calls, input tokens, output tokens,
and estimated dollar cost per evolution run.
"""

from datetime import datetime, timezone

import pytest

from api.types import LLMResponse, ModelRole


def _make_response(
    role: ModelRole = ModelRole.META,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cost_usd: float = 0.01,
    model: str = "anthropic/claude-sonnet-4",
) -> LLMResponse:
    """Helper to create test LLMResponse objects."""
    return LLMResponse(
        content="test response",
        model_used=model,
        role=role,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        timestamp=datetime.now(timezone.utc),
    )


class TestEstimateCostFromTokens:
    """Test static pricing table cost estimation."""

    def test_known_model_returns_cost(self):
        """COST-01: estimate_cost_from_tokens returns correct cost for known models."""
        from api.gateway.cost import estimate_cost_from_tokens

        cost = estimate_cost_from_tokens("openai/gpt-4o-mini", 1000, 500)
        assert cost is not None
        assert cost > 0

    def test_claude_sonnet_returns_cost(self):
        """COST-01: Pricing for claude-sonnet-4."""
        from api.gateway.cost import estimate_cost_from_tokens

        cost = estimate_cost_from_tokens("anthropic/claude-sonnet-4", 1000, 500)
        assert cost is not None
        assert cost > 0

    def test_unknown_model_returns_none(self):
        """COST-01: estimate_cost_from_tokens returns None for unknown models."""
        from api.gateway.cost import estimate_cost_from_tokens

        cost = estimate_cost_from_tokens("some-vendor/unknown-model-xyz", 1000, 500)
        assert cost is None

    def test_cost_calculation_accuracy(self):
        """COST-01: Cost = (input * input_rate / 1M) + (output * output_rate / 1M)."""
        from api.gateway.cost import MODEL_PRICING, estimate_cost_from_tokens

        # Pick a model from the pricing table and verify calculation
        model = "openai/gpt-4o-mini"
        pricing = MODEL_PRICING[model]
        input_tokens = 1_000_000
        output_tokens = 1_000_000

        cost = estimate_cost_from_tokens(model, input_tokens, output_tokens)
        expected = pricing["input_per_million"] + pricing["output_per_million"]
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_pricing_table_has_minimum_models(self):
        """COST-01: Static pricing table has at least 8 models."""
        from api.gateway.cost import MODEL_PRICING

        assert len(MODEL_PRICING) >= 8


class TestGeminiDirectPricing:
    """GEM-03: Static pricing table includes Gemini direct API models."""

    def test_gemini_flash_pricing(self):
        """estimate_cost_from_tokens('gemini-2.5-flash', 1000, 500) returns correct cost."""
        from api.gateway.cost import estimate_cost_from_tokens

        cost = estimate_cost_from_tokens("gemini-2.5-flash", 1000, 500)
        assert cost is not None
        # gemini-2.5-flash: $0.15/M input, $0.60/M output
        expected = (1000 * 0.15 / 1_000_000) + (500 * 0.60 / 1_000_000)
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_gemini_pro_pricing(self):
        """estimate_cost_from_tokens('gemini-2.5-pro', 1000, 500) returns correct cost."""
        from api.gateway.cost import estimate_cost_from_tokens

        cost = estimate_cost_from_tokens("gemini-2.5-pro", 1000, 500)
        assert cost is not None
        # gemini-2.5-pro: $1.25/M input, $10.0/M output
        expected = (1000 * 1.25 / 1_000_000) + (500 * 10.0 / 1_000_000)
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_gemini_flash_lite_pricing(self):
        """estimate_cost_from_tokens('gemini-2.0-flash-lite', 1000, 500) returns correct cost."""
        from api.gateway.cost import estimate_cost_from_tokens

        cost = estimate_cost_from_tokens("gemini-2.0-flash-lite", 1000, 500)
        assert cost is not None
        # gemini-2.0-flash-lite: $0.0/M input, $0.0/M output (free tier)
        assert cost == pytest.approx(0.0)


class TestCostTracker:
    """Test CostTracker aggregation."""

    def test_record_stores_response(self):
        """COST-01: CostTracker.record stores per-call data."""
        from api.gateway.cost import CostTracker

        tracker = CostTracker()
        response = _make_response()
        tracker.record(response)
        assert len(tracker._records) == 1

    def test_summary_aggregates_totals(self):
        """COST-01: CostTracker.summary() returns aggregate totals."""
        from api.gateway.cost import CostTracker

        tracker = CostTracker()
        tracker.record(_make_response(input_tokens=100, output_tokens=50, cost_usd=0.01))
        tracker.record(_make_response(input_tokens=200, output_tokens=100, cost_usd=0.02))

        summary = tracker.summary()
        assert summary["total_calls"] == 2
        assert summary["total_input_tokens"] == 300
        assert summary["total_output_tokens"] == 150
        assert summary["total_cost_usd"] == pytest.approx(0.03)

    def test_summary_empty_tracker(self):
        """COST-01: summary() with no records returns zeros."""
        from api.gateway.cost import CostTracker

        tracker = CostTracker()
        summary = tracker.summary()
        assert summary["total_calls"] == 0
        assert summary["total_input_tokens"] == 0
        assert summary["total_output_tokens"] == 0
        assert summary["total_cost_usd"] == 0.0

    def test_by_role_breakdown(self):
        """COST-01: CostTracker.by_role() breaks down costs by ModelRole."""
        from api.gateway.cost import CostTracker

        tracker = CostTracker()
        tracker.record(_make_response(role=ModelRole.META, cost_usd=0.10))
        tracker.record(_make_response(role=ModelRole.META, cost_usd=0.05))
        tracker.record(_make_response(role=ModelRole.TARGET, cost_usd=0.02))
        tracker.record(_make_response(role=ModelRole.JUDGE, cost_usd=0.03))

        by_role = tracker.by_role()
        assert ModelRole.META in by_role
        assert ModelRole.TARGET in by_role
        assert ModelRole.JUDGE in by_role
        assert by_role[ModelRole.META]["total_calls"] == 2
        assert by_role[ModelRole.META]["total_cost_usd"] == pytest.approx(0.15)
        assert by_role[ModelRole.TARGET]["total_calls"] == 1
        assert by_role[ModelRole.JUDGE]["total_calls"] == 1

    def test_reset_clears_records(self):
        """COST-01: CostTracker.reset() clears all records."""
        from api.gateway.cost import CostTracker

        tracker = CostTracker()
        tracker.record(_make_response())
        tracker.record(_make_response())
        assert tracker.summary()["total_calls"] == 2

        tracker.reset()
        assert tracker.summary()["total_calls"] == 0

    def test_cost_tracker_summary_snapshot_safety(self):
        """EVO-01: summary() uses snapshot copy for safe concurrent reads.

        Verifies that summary() returns consistent totals when 100 records
        are present -- a baseline correctness test ensuring snapshot iteration.
        """
        from api.gateway.cost import CostTracker

        tracker = CostTracker()
        for i in range(100):
            tracker.record(_make_response(input_tokens=10, output_tokens=5, cost_usd=0.001))

        summary = tracker.summary()
        assert summary["total_calls"] == 100
        assert summary["total_input_tokens"] == 1000
        assert summary["total_output_tokens"] == 500
        assert summary["total_cost_usd"] == pytest.approx(0.1)

        # Verify by_role also works consistently with many records
        by_role = tracker.by_role()
        meta_totals = by_role[ModelRole.META]
        assert meta_totals["total_calls"] == 100
        assert meta_totals["total_input_tokens"] == 1000
