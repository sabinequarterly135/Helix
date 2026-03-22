"""Tests for dataset invalidation detection.

Covers InvalidationRecord model fields, InvalidationService.check_artifacts(),
InvalidationService.flag_cases(), and backward compatibility of TestCase
with optional invalidation field.
"""

from datetime import datetime


from api.dataset.invalidation import InvalidationRecord, InvalidationService
from api.dataset.models import TestCase


class TestInvalidationRecord:
    """Tests for the InvalidationRecord model."""

    def test_stores_all_fields(self) -> None:
        rec = InvalidationRecord(
            reason="artifact_change",
            changed_field="target_model",
            old_fingerprint="aaa",
            new_fingerprint="bbb",
        )
        assert rec.reason == "artifact_change"
        assert rec.changed_field == "target_model"
        assert rec.old_fingerprint == "aaa"
        assert rec.new_fingerprint == "bbb"
        assert isinstance(rec.invalidated_at, datetime)

    def test_acknowledged_defaults_false(self) -> None:
        rec = InvalidationRecord(reason="variable_change", changed_field="variable:x")
        assert rec.acknowledged is False

    def test_fingerprints_default_none(self) -> None:
        rec = InvalidationRecord(reason="variable_change", changed_field="variable:x")
        assert rec.old_fingerprint is None
        assert rec.new_fingerprint is None


class TestTestCaseInvalidationField:
    """Tests for backward-compatible invalidation field on TestCase."""

    def test_testcase_invalidation_defaults_none(self) -> None:
        tc = TestCase()
        assert tc.invalidation is None

    def test_testcase_with_invalidation_record(self) -> None:
        rec = InvalidationRecord(reason="artifact_change", changed_field="tools_hash")
        tc = TestCase(invalidation=rec)
        assert tc.invalidation is not None
        assert tc.invalidation.reason == "artifact_change"

    def test_existing_json_without_invalidation_deserializes(self) -> None:
        """Existing case JSON without invalidation field still deserializes."""
        raw = {
            "id": "case-1",
            "name": "legacy case",
            "variables": {"x": 1},
            "tier": "normal",
        }
        tc = TestCase.model_validate(raw)
        assert tc.id == "case-1"
        assert tc.invalidation is None


class TestInvalidationServiceCheckArtifacts:
    """Tests for InvalidationService.check_artifacts()."""

    def test_returns_empty_when_fingerprints_match(self) -> None:
        result = InvalidationService.check_artifacts("abc123", "abc123")
        assert result == []

    def test_returns_record_when_fingerprints_differ(self) -> None:
        result = InvalidationService.check_artifacts("old_fp", "new_fp")
        assert len(result) == 1
        assert result[0].reason == "artifact_change"
        assert result[0].old_fingerprint == "old_fp"
        assert result[0].new_fingerprint == "new_fp"
        assert result[0].changed_field == "artifacts"

    def test_returns_per_field_records_when_changed_fields_provided(self) -> None:
        result = InvalidationService.check_artifacts(
            "old_fp", "new_fp", changed_fields=["target_model", "tools_hash"]
        )
        assert len(result) == 2
        assert result[0].changed_field == "target_model"
        assert result[1].changed_field == "tools_hash"


class TestInvalidationServiceFlagCases:
    """Tests for InvalidationService.flag_cases()."""

    def test_flag_cases_sets_invalidation_field(self) -> None:
        cases = [TestCase(id="c1"), TestCase(id="c2")]
        records = [InvalidationRecord(reason="artifact_change", changed_field="target_model")]
        flagged = InvalidationService.flag_cases(cases, records)
        assert len(flagged) == 2
        assert flagged[0].invalidation is not None
        assert flagged[0].invalidation.reason == "artifact_change"
        assert flagged[1].invalidation is not None
