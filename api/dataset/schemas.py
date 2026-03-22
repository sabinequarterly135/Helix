"""Import/export file format schemas for dataset test cases.

Provides:
- DatasetImportSchema: Validates imported test case data from JSON/YAML files
"""

from typing import Any

from pydantic import BaseModel


class DatasetImportSchema(BaseModel):
    """Schema for imported dataset files.

    Supports two formats:
    - A list of case dicts: [{...}, {...}]
    - A wrapper object: {"cases": [{...}, {...}]}

    Attributes:
        cases: List of case dictionaries to import.
    """

    cases: list[dict[str, Any]]

    @classmethod
    def from_file_content(cls, raw: Any) -> "DatasetImportSchema":
        """Parse raw file content into a DatasetImportSchema.

        Handles both list format and {"cases": [...]} wrapper format.

        Args:
            raw: The parsed file content (list or dict).

        Returns:
            DatasetImportSchema with the cases list.

        Raises:
            ValueError: If the input format is not recognized.
            TypeError: If the input is not a list or dict.
        """
        if isinstance(raw, list):
            return cls(cases=raw)
        if isinstance(raw, dict) and "cases" in raw:
            return cls(cases=raw["cases"])
        raise ValueError(
            f"Expected a list of cases or a dict with 'cases' key, got {type(raw).__name__}"
        )
