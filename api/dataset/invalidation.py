"""Dataset invalidation detection for artifact and variable changes.

Provides:
- InvalidationRecord: tracks why and when a dataset case was invalidated
- InvalidationService: compares fingerprints and flags affected cases

The service accepts fingerprint strings as parameters (not ArtifactConfig or
VariableDefinition directly) to avoid cross-package imports.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InvalidationRecord(BaseModel):
    """Record of why and when a dataset case was invalidated.

    Attributes:
        reason: Category of change -- "artifact_change" or "variable_change".
        changed_field: Specific field that changed, e.g. "target_model", "variable:customer_name".
        old_fingerprint: Fingerprint before the change (None if not applicable).
        new_fingerprint: Fingerprint after the change (None if variable was removed).
        invalidated_at: Timestamp when the invalidation was detected.
        acknowledged: Whether a user has acknowledged and reviewed this invalidation.
    """

    reason: str
    changed_field: str
    old_fingerprint: str | None = None
    new_fingerprint: str | None = None
    invalidated_at: datetime = Field(default_factory=datetime.now)
    acknowledged: bool = False


class InvalidationService:
    """Service for detecting invalidation conditions and flagging cases.

    All methods are static -- no instance state needed.
    Accepts fingerprint strings as parameters to avoid cross-package imports.
    """

    @staticmethod
    def check_artifacts(
        old_fingerprint: str,
        new_fingerprint: str,
        changed_fields: list[str] | None = None,
    ) -> list[InvalidationRecord]:
        """Compare artifact fingerprints, return invalidation records if changed.

        Args:
            old_fingerprint: Previous artifact fingerprint.
            new_fingerprint: Current artifact fingerprint.
            changed_fields: Optional list of specific fields that changed.
                If provided, one record per field; otherwise one record
                with changed_field="artifacts".

        Returns:
            List of InvalidationRecord (empty if fingerprints match).
        """
        if old_fingerprint == new_fingerprint:
            return []

        if changed_fields:
            return [
                InvalidationRecord(
                    reason="artifact_change",
                    changed_field=field,
                    old_fingerprint=old_fingerprint,
                    new_fingerprint=new_fingerprint,
                )
                for field in changed_fields
            ]

        return [
            InvalidationRecord(
                reason="artifact_change",
                changed_field="artifacts",
                old_fingerprint=old_fingerprint,
                new_fingerprint=new_fingerprint,
            )
        ]

    @staticmethod
    def flag_cases(
        cases: list[Any],
        records: list[InvalidationRecord],
    ) -> list[Any]:
        """Apply invalidation records to affected cases.

        Sets the invalidation field on each case to the first matching record.
        Cases are flagged in memory -- persisting to disk is the caller's
        responsibility.

        Args:
            cases: List of TestCase objects to flag.
            records: List of InvalidationRecord to apply.

        Returns:
            List of flagged cases (same objects, mutated in place).
        """
        if not records:
            return cases

        first_record = records[0]
        for case in cases:
            case.invalidation = first_record

        return cases
