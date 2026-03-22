"""DatasetService: CRUD operations for evaluation test cases.

Provides:
- DatasetService: Service for adding, listing, getting, importing,
  deleting, updating, and summarizing test cases within prompt datasets.

Test cases are stored as rows in the test_cases database table,
keyed by prompt_id. No filesystem reads or writes for CRUD operations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.dataset.models import DatasetSummary, PriorityTier, TestCase
from api.dataset.schemas import DatasetImportSchema
from api.exceptions import PromptNotFoundError
from api.registry.models import VariableDefinition
from api.registry.validation import validate_test_case_variables
from api.storage.models import Prompt, TestCaseRecord

logger = logging.getLogger(__name__)


def _row_to_test_case(row: TestCaseRecord) -> TestCase:
    """Convert a TestCaseRecord ORM row to a TestCase domain model.

    Args:
        row: The database row to convert.

    Returns:
        A TestCase Pydantic model populated from the row data.
    """
    return TestCase(
        id=row.id,
        name=row.name,
        description=row.description,
        chat_history=row.chat_history,
        variables=row.variables,
        tools=row.tools,
        expected_output=row.expected_output,
        tier=PriorityTier(row.tier),
        tags=row.tags,
        created_at=row.created_at,
    )


class DatasetService:
    """Service for managing evaluation test case datasets via the database.

    Each prompt's test cases are stored as rows in the test_cases table,
    keyed by prompt_id. The service manages its own database sessions
    internally using the provided session factory.

    Attributes:
        session_factory: Async session factory for database access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the DatasetService.

        Args:
            session_factory: Async session factory for creating database sessions.
        """
        self.session_factory = session_factory

    async def add_case(self, prompt_id: str, case: TestCase) -> tuple[TestCase, list[str]]:
        """Add a test case to a prompt's dataset in the database.

        Validates variables against the prompt's variable schema if one exists
        (warn-but-allow). Inserts a TestCaseRecord row.

        Args:
            prompt_id: The prompt identifier.
            case: The TestCase to add.

        Returns:
            Tuple of (added TestCase, list of validation warning strings).

        Raises:
            PromptNotFoundError: If the prompt does not exist in the database.
        """
        async with self.session_factory() as session:
            await self._ensure_prompt_exists(session, prompt_id)

            # Validate variables against schema (warn-but-allow)
            warnings = await self._validate_variables(session, prompt_id, case.variables)

            # Insert test case row
            record = TestCaseRecord(
                id=case.id,
                prompt_id=prompt_id,
                name=case.name,
                description=case.description,
                chat_history=case.chat_history,
                variables=case.variables,
                tools=case.tools,
                expected_output=case.expected_output,
                tier=case.tier.value,
                tags=case.tags,
            )
            session.add(record)
            await session.commit()

            logger.info(
                "Added case '%s' to prompt '%s' (tier=%s)",
                case.id,
                prompt_id,
                case.tier.value,
            )
            return case, warnings

    async def list_cases(self, prompt_id: str) -> list[TestCase]:
        """List all test cases for a prompt, sorted by ID.

        Args:
            prompt_id: The prompt identifier.

        Returns:
            List of TestCase objects sorted by ID.
            Returns empty list if no test cases exist.
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(TestCaseRecord)
                .where(TestCaseRecord.prompt_id == prompt_id)
                .order_by(TestCaseRecord.id)
            )
            rows = result.scalars().all()
            return [_row_to_test_case(row) for row in rows]

    async def get_case(self, prompt_id: str, case_id: str) -> TestCase:
        """Get a specific test case by ID.

        Args:
            prompt_id: The prompt identifier.
            case_id: The test case identifier.

        Returns:
            The matching TestCase.

        Raises:
            ValueError: If no case with the given ID is found.
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(TestCaseRecord).where(
                    TestCaseRecord.id == case_id,
                    TestCaseRecord.prompt_id == prompt_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(
                    f"Test case '{case_id}' not found for prompt '{prompt_id}'"
                )
            return _row_to_test_case(row)

    async def import_cases(self, prompt_id: str, file_path: Path) -> list[TestCase]:
        """Import test cases from a JSON or YAML file into the database.

        Supports both list format and {"cases": [...]} wrapper format.
        YAML files are detected by .yaml or .yml suffix.

        Args:
            prompt_id: The prompt identifier.
            file_path: Path to the import file (JSON or YAML).

        Returns:
            List of imported TestCase objects.

        Raises:
            PromptNotFoundError: If the prompt does not exist in the database.
        """
        content = file_path.read_text(encoding="utf-8")

        # Parse based on file extension
        if file_path.suffix in (".yaml", ".yml"):
            raw = yaml.safe_load(content)
        else:
            raw = json.loads(content)

        # Validate structure
        schema = DatasetImportSchema.from_file_content(raw)

        # Create and add each case
        imported: list[TestCase] = []
        for case_dict in schema.cases:
            case = TestCase(**case_dict)
            created, _warnings = await self.add_case(prompt_id, case)
            imported.append(created)

        logger.info(
            "Imported %d cases into prompt '%s' from '%s'",
            len(imported),
            prompt_id,
            file_path.name,
        )
        return imported

    async def delete_case(self, prompt_id: str, case_id: str) -> None:
        """Delete a test case by ID.

        Args:
            prompt_id: The prompt identifier.
            case_id: The test case identifier.

        Raises:
            ValueError: If no case with the given ID is found.
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(TestCaseRecord).where(
                    TestCaseRecord.id == case_id,
                    TestCaseRecord.prompt_id == prompt_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(
                    f"Test case '{case_id}' not found for prompt '{prompt_id}'"
                )
            await session.delete(row)
            await session.commit()
            logger.info("Deleted case '%s' from prompt '%s'", case_id, prompt_id)

    async def summary(self, prompt_id: str) -> DatasetSummary:
        """Get a summary of a prompt's dataset with tier counts.

        Args:
            prompt_id: The prompt identifier.

        Returns:
            DatasetSummary with total and per-tier case counts.
        """
        async with self.session_factory() as session:
            # Count by tier in a single query
            result = await session.execute(
                select(TestCaseRecord.tier, func.count())
                .where(TestCaseRecord.prompt_id == prompt_id)
                .group_by(TestCaseRecord.tier)
            )
            tier_counts: dict[str, int] = dict(result.all())

            total = sum(tier_counts.values())
            return DatasetSummary(
                prompt_id=prompt_id,
                total_cases=total,
                critical_count=tier_counts.get(PriorityTier.CRITICAL.value, 0),
                normal_count=tier_counts.get(PriorityTier.NORMAL.value, 0),
                low_count=tier_counts.get(PriorityTier.LOW.value, 0),
            )

    async def update_case(self, prompt_id: str, case_id: str, case: TestCase) -> TestCase:
        """Update an existing test case in the database.

        Args:
            prompt_id: The prompt identifier.
            case_id: The test case identifier to update.
            case: The new TestCase data to write.

        Returns:
            The updated TestCase.

        Raises:
            PromptNotFoundError: If the prompt does not exist in the database.
            ValueError: If no case with the given ID is found.
        """
        async with self.session_factory() as session:
            await self._ensure_prompt_exists(session, prompt_id)

            result = await session.execute(
                select(TestCaseRecord).where(
                    TestCaseRecord.id == case_id,
                    TestCaseRecord.prompt_id == prompt_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(
                    f"Test case '{case_id}' not found for prompt '{prompt_id}'"
                )

            # Update fields
            row.name = case.name
            row.description = case.description
            row.chat_history = case.chat_history
            row.variables = case.variables
            row.tools = case.tools
            row.expected_output = case.expected_output
            row.tier = case.tier.value
            row.tags = case.tags

            await session.commit()

            # Ensure returned case has the correct ID
            case.id = case_id
            logger.info("Updated case '%s' for prompt '%s'", case_id, prompt_id)
            return case

    async def _validate_variables(
        self, session: AsyncSession, prompt_id: str, variables: dict
    ) -> list[str]:
        """Validate test case variables against the prompt's variable schema.

        Queries the Prompt row for its variables JSON and runs validation.
        Returns empty list if no schema exists.

        Args:
            session: Active database session.
            prompt_id: The prompt identifier.
            variables: Dict of variable name -> value from the test case.

        Returns:
            List of warning message strings. Empty if no schema or no violations.
        """
        try:
            result = await session.execute(
                select(Prompt.variables).where(Prompt.id == prompt_id)
            )
            variables_json = result.scalar_one_or_none()
            if not variables_json:
                return []

            schema = [VariableDefinition(**v) for v in variables_json]
            return validate_test_case_variables(variables, schema)
        except Exception:
            logger.warning(
                "Failed to load variable schema for prompt '%s'", prompt_id
            )
            return []

    async def _ensure_prompt_exists(
        self, session: AsyncSession, prompt_id: str
    ) -> None:
        """Ensure the prompt exists in the database.

        Args:
            session: Active database session.
            prompt_id: The prompt identifier.

        Raises:
            PromptNotFoundError: If the prompt does not exist.
        """
        result = await session.execute(
            select(Prompt.id).where(Prompt.id == prompt_id)
        )
        if result.scalar_one_or_none() is None:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' not found")
