"""Shared types used across all Helix sub-packages."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ModelRole(StrEnum):
    """Role of an LLM model in the evolution pipeline."""

    META = "meta"  # Critic/author model for evolution
    TARGET = "target"  # Model the prompt is being optimized for
    JUDGE = "judge"  # LLM judge for evaluation scoring
    TOOL_MOCKER = "tool_mocker"  # LLM-based tool mock generation


class OTelAttributes(BaseModel):
    """OTel-compatible observability attributes following gen_ai semantic conventions.

    Provides trace/span IDs and service metadata without requiring the
    OpenTelemetry SDK. Fields map to standard OTel attribute names via
    to_otel_attributes().

    Field mapping to OTel attributes:
        trace_id -> W3C trace-id (32 hex chars)
        span_id  -> W3C span-id (16 hex chars)
        service_name -> service.name resource attribute
    """

    trace_id: str | None = None
    span_id: str | None = None
    service_name: str | None = None

    @staticmethod
    def generate_trace_id() -> str:
        """Generate a W3C-compatible 32-character hex trace ID."""
        return uuid.uuid4().hex  # 32 hex chars

    @staticmethod
    def generate_span_id() -> str:
        """Generate a W3C-compatible 16-character hex span ID."""
        return uuid.uuid4().hex[:16]  # 16 hex chars

    def to_otel_attributes(self) -> dict[str, str]:
        """Convert to OTel-compatible dotted attribute names for export."""
        attrs: dict[str, str] = {}
        if self.trace_id:
            attrs["trace_id"] = self.trace_id
        if self.span_id:
            attrs["span_id"] = self.span_id
        if self.service_name:
            attrs["service.name"] = self.service_name
        return attrs


class LLMResponse(BaseModel):
    """Response from an LLM API call with cost and usage tracking."""

    content: str | None
    tool_calls: list[dict] | None = None
    model_used: str
    role: ModelRole
    input_tokens: int
    output_tokens: int
    cost_usd: float
    generation_id: str | None = None
    timestamp: datetime
    finish_reason: str | None = None
    otel: OTelAttributes | None = None


class CostRecord(BaseModel):
    """Cost and usage record for a single LLM API call or aggregated run."""

    total_cost_usd: float | None
    input_tokens: int
    output_tokens: int
    provider: str | None = None
    model: str | None = None
    latency_ms: float | None = None
    generation_time_ms: float | None = None
