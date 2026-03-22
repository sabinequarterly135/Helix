"""Tests for OTel-compatible observability attributes.

Covers OTelAttributes model fields, ID generation, to_otel_attributes() mapping,
JSON round-trip, and backward compatibility of otel field on key data models.
"""

import json
from datetime import datetime


from api.types import OTelAttributes, LLMResponse, ModelRole
from api.dataset.models import TestCase
from api.evaluation.models import CaseResult
from api.evolution.models import Candidate


class TestOTelAttributes:
    """Tests for the OTelAttributes model."""

    def test_defaults_all_none(self) -> None:
        attrs = OTelAttributes()
        assert attrs.trace_id is None
        assert attrs.span_id is None
        assert attrs.service_name is None

    def test_generate_trace_id_32_hex(self) -> None:
        tid = OTelAttributes.generate_trace_id()
        assert len(tid) == 32
        int(tid, 16)  # raises if not valid hex

    def test_generate_span_id_16_hex(self) -> None:
        sid = OTelAttributes.generate_span_id()
        assert len(sid) == 16
        int(sid, 16)  # raises if not valid hex

    def test_to_otel_attributes_maps_dotted_names(self) -> None:
        attrs = OTelAttributes(
            trace_id="a" * 32,
            span_id="b" * 16,
            service_name="gene-prompter",
        )
        result = attrs.to_otel_attributes()
        assert result["trace_id"] == "a" * 32
        assert result["span_id"] == "b" * 16
        assert result["service.name"] == "gene-prompter"

    def test_to_otel_attributes_omits_none(self) -> None:
        attrs = OTelAttributes(trace_id="abc123")
        result = attrs.to_otel_attributes()
        assert "trace_id" in result
        assert "span_id" not in result
        assert "service.name" not in result

    def test_json_round_trip(self) -> None:
        attrs = OTelAttributes(
            trace_id="a" * 32,
            span_id="b" * 16,
            service_name="test-svc",
        )
        data = json.loads(attrs.model_dump_json())
        restored = OTelAttributes.model_validate(data)
        assert restored.trace_id == attrs.trace_id
        assert restored.span_id == attrs.span_id
        assert restored.service_name == attrs.service_name


class TestOTelIntegration:
    """Tests for optional otel field on key data models."""

    def test_testcase_otel_none(self) -> None:
        tc = TestCase()
        assert tc.otel is None

    def test_testcase_otel_set(self) -> None:
        tc = TestCase(otel=OTelAttributes(trace_id="abc123"))
        assert tc.otel is not None
        assert tc.otel.trace_id == "abc123"

    def test_caseresult_otel_none(self) -> None:
        cr = CaseResult(case_id="c1", score=0.8)
        assert cr.otel is None

    def test_caseresult_otel_set(self) -> None:
        cr = CaseResult(case_id="c1", score=0.8, otel=OTelAttributes(span_id="x" * 16))
        assert cr.otel is not None
        assert cr.otel.span_id == "x" * 16

    def test_candidate_otel_none(self) -> None:
        c = Candidate(template="hello")
        assert c.otel is None

    def test_llmresponse_otel_none(self) -> None:
        resp = LLMResponse(
            content="hi",
            model_used="test",
            role=ModelRole.TARGET,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.001,
            timestamp=datetime.now(),
        )
        assert resp.otel is None

    def test_existing_json_without_otel_deserializes(self) -> None:
        """All models with existing JSON lacking otel field still work."""
        tc_raw = {"id": "c1", "tier": "normal"}
        tc = TestCase.model_validate(tc_raw)
        assert tc.otel is None

        cr_raw = {"case_id": "c1", "score": 0.5}
        cr = CaseResult.model_validate(cr_raw)
        assert cr.otel is None

        cand_raw = {"template": "hello"}
        cand = Candidate.model_validate(cand_raw)
        assert cand.otel is None
