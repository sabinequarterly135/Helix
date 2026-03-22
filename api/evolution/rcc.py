"""RCC (Refinement through Critical Conversation) engine.

Implements the core evolution mechanism from the Mind Evolution paper:
a critic identifies prompt failures and an author revises the prompt.
Each conversation runs N_seq turns of critic-then-author, with each
turn building on the previous revision.

The engine uses the configured meta-model (ModelRole.META) for both
critic and author steps, keeping it separate from the target model
used for fitness evaluation.
"""

from __future__ import annotations

import logging
import re

from api.evaluation.models import CaseResult
from api.evaluation.validator import TemplateValidator
from api.evolution.models import Candidate
from api.evolution.prompts import (
    AUTHOR_SYSTEM_PROMPT,
    AUTHOR_USER_PROMPT,
    CRITIC_SYSTEM_PROMPT,
    CRITIC_USER_PROMPT,
    FRESH_GENERATION_PROMPT,
)
from api.gateway.cost import CostTracker
from api.gateway.protocol import LLMProvider
from api.types import ModelRole

logger = logging.getLogger(__name__)

# Regex for extracting template from <revised_template> delimiters
_TEMPLATE_RE = re.compile(
    r"<revised_template>\s*(.*?)\s*</revised_template>",
    re.DOTALL,
)


class RCCEngine:
    """Refinement through Critical Conversation engine.

    Runs multi-turn critic-author conversations to evolve prompt templates.
    Each conversation selects the best parent, runs N_seq turns of
    critic analysis followed by author revision, and returns a new
    Candidate with the evolved template.

    If no parents are provided (Pr_no_parents case), generates a fresh
    candidate from the purpose description alone.

    Args:
        client: LLM provider for API calls.
        cost_tracker: Tracker for recording meta-model call costs.
        validator: Template validator for checking variable preservation.
        meta_model: OpenRouter model identifier for critic/author calls.
        max_retries: Maximum retries when author drops required variables.
    """

    def __init__(
        self,
        client: LLMProvider,
        cost_tracker: CostTracker,
        validator: TemplateValidator,
        meta_model: str,
        max_retries: int = 3,
        extra_kwargs: dict | None = None,
    ) -> None:
        self._client = client
        self._cost_tracker = cost_tracker
        self._validator = validator
        self._meta_model = meta_model
        self._max_retries = max_retries
        self._extra_kwargs = extra_kwargs

    async def run_conversation(
        self,
        parents: list[Candidate],
        original_template: str,
        anchor_variables: set[str],
        purpose: str,
        n_seq: int,
        generation: int,
    ) -> Candidate:
        """Run N_seq turns of critic-author refinement.

        If parents is empty (no-parent case), generate a fresh candidate
        from the purpose description. Otherwise, use the best parent's
        template as starting point and its evaluation for critic feedback.

        Args:
            parents: Parent candidates to refine from (empty for fresh generation).
            original_template: The original template for variable validation.
            anchor_variables: Variables that must be preserved in the evolved template.
            purpose: Description of what the prompt is optimized for.
            n_seq: Number of sequential refinement turns.
            generation: Generation number for the new candidate.

        Returns:
            A new Candidate with the evolved template.
        """
        if not parents:
            return await self._generate_fresh(
                original_template=original_template,
                anchor_variables=anchor_variables,
                purpose=purpose,
                generation=generation,
            )

        # Select best parent by fitness score
        best_parent = max(parents, key=lambda c: c.fitness_score)
        current_template = best_parent.template

        # Get case results from best parent's evaluation (if available)
        case_results: list[CaseResult] = []
        if best_parent.evaluation is not None:
            case_results = best_parent.evaluation.case_results

        required_variables_str = ", ".join(sorted(anchor_variables))

        for turn in range(n_seq):
            logger.debug(
                "RCC turn %d/%d for generation %d",
                turn + 1,
                n_seq,
                generation,
            )

            # Format case feedback for critic
            failing_formatted = self._format_failing_cases(case_results)
            passing_summary = self._format_passing_summary(case_results)

            # Critic step
            critic_messages = [
                {
                    "role": "system",
                    "content": CRITIC_SYSTEM_PROMPT.format(
                        purpose=purpose,
                        required_variables=required_variables_str,
                    ),
                },
                {
                    "role": "user",
                    "content": CRITIC_USER_PROMPT.format(
                        template=current_template,
                        failing_cases_formatted=failing_formatted,
                        passing_cases_summary=passing_summary,
                        required_variables=required_variables_str,
                    ),
                },
            ]
            critic_response = await self._client.chat_completion(
                messages=critic_messages,
                model=self._meta_model,
                role=ModelRole.META,
                **(self._extra_kwargs or {}),
            )
            self._cost_tracker.record(critic_response)
            critic_analysis = critic_response.content or ""

            # Author step with retry on variable loss
            revised = await self._author_with_retry(
                critic_analysis=critic_analysis,
                current_template=current_template,
                original_template=original_template,
                anchor_variables=anchor_variables,
            )

            if revised is not None:
                current_template = revised
            else:
                # All retries failed -- keep the previous turn's template
                logger.warning(
                    "All %d author retries failed on turn %d; keeping previous template",
                    self._max_retries,
                    turn + 1,
                )

        parent_ids = [p.id for p in parents]
        return Candidate(
            template=current_template,
            generation=generation,
            parent_ids=parent_ids,
        )

    async def _author_with_retry(
        self,
        critic_analysis: str,
        current_template: str,
        original_template: str,
        anchor_variables: set[str],
    ) -> str | None:
        """Call author and retry up to max_retries if variables are dropped.

        Returns the revised template if valid, or None if all retries fail.
        """
        required_variables_str = ", ".join(sorted(anchor_variables))

        for attempt in range(self._max_retries):
            if attempt == 0:
                # First attempt: normal author prompt
                author_messages = [
                    {
                        "role": "system",
                        "content": AUTHOR_SYSTEM_PROMPT.format(
                            required_variables=required_variables_str,
                        ),
                    },
                    {
                        "role": "user",
                        "content": AUTHOR_USER_PROMPT.format(
                            critic_analysis=critic_analysis,
                            template=current_template,
                            required_variables=required_variables_str,
                        ),
                    },
                ]
            else:
                # Retry: add explicit feedback about dropped/renamed variables
                validation = self._validator.validate_preserved(
                    original_template,
                    last_attempt_template,  # noqa: F821 -- assigned in previous iteration
                    anchor_variables,
                )

                # Build feedback distinguishing renames from drops
                feedback_parts = []
                if validation.renamed_variables:
                    rename_details = ", ".join(
                        f"{old} -> {new}" for old, new in validation.renamed_variables.items()
                    )
                    feedback_parts.append(
                        f"You RENAMED these variables: {rename_details}. "
                        "You MUST use the ORIGINAL variable names, not new names."
                    )

                # Report remaining dropped variables (not accounted for by renames)
                dropped = [
                    v for v in validation.missing_variables if v not in validation.renamed_variables
                ]
                if dropped:
                    dropped_str = ", ".join(dropped)
                    feedback_parts.append(f"You DROPPED these required variables: {dropped_str}.")

                feedback = " ".join(feedback_parts)
                feedback += f" Required variables: {required_variables_str}"

                author_messages = [
                    {
                        "role": "system",
                        "content": AUTHOR_SYSTEM_PROMPT.format(
                            required_variables=required_variables_str,
                        ),
                    },
                    {
                        "role": "user",
                        "content": AUTHOR_USER_PROMPT.format(
                            critic_analysis=critic_analysis,
                            template=current_template,
                            required_variables=required_variables_str,
                        )
                        + f"\n\nIMPORTANT: {feedback}",
                    },
                ]

            author_response = await self._client.chat_completion(
                messages=author_messages,
                model=self._meta_model,
                role=ModelRole.META,
                **(self._extra_kwargs or {}),
            )
            self._cost_tracker.record(author_response)

            last_attempt_template = self._extract_template(author_response.content or "")

            # Validate variable preservation
            validation = self._validator.validate_preserved(
                original_template,
                last_attempt_template,
                anchor_variables,
            )

            if validation.valid:
                return last_attempt_template

            logger.warning(
                "Author dropped variables on attempt %d/%d: %s",
                attempt + 1,
                self._max_retries,
                validation.missing_variables,
            )

        return None

    async def _generate_fresh(
        self,
        original_template: str,
        anchor_variables: set[str],
        purpose: str,
        generation: int,
    ) -> Candidate:
        """Generate a fresh candidate from purpose description (no-parent case).

        Args:
            original_template: The original template for variable reference.
            anchor_variables: Variables that must be present in the new template.
            purpose: What the prompt is being optimized for.
            generation: Generation number for the new candidate.

        Returns:
            A new Candidate with a freshly generated template.
        """
        required_variables_str = ", ".join(sorted(anchor_variables))
        variable_descriptions = "\n".join(
            f"- {var}: (used in template)" for var in sorted(anchor_variables)
        )

        messages = [
            {
                "role": "user",
                "content": FRESH_GENERATION_PROMPT.format(
                    purpose=purpose,
                    required_variables=required_variables_str,
                    variable_descriptions=variable_descriptions,
                ),
            },
        ]

        response = await self._client.chat_completion(
            messages=messages,
            model=self._meta_model,
            role=ModelRole.META,
            **(self._extra_kwargs or {}),
        )
        self._cost_tracker.record(response)

        template = self._extract_template(response.content or "")

        return Candidate(
            template=template,
            generation=generation,
            parent_ids=[],
        )

    @staticmethod
    def _format_failing_cases(case_results: list[CaseResult]) -> str:
        """Format failing cases for the critic prompt.

        Includes case_id, tier, score, and reason for each failing case.
        """
        failing = [cr for cr in case_results if not cr.passed]
        if not failing:
            return "(No failing cases)"

        lines = []
        for cr in failing:
            lines.append(f"- Case {cr.case_id} [tier={cr.tier}, score={cr.score:.2f}]: {cr.reason}")
        return "\n".join(lines)

    @staticmethod
    def _format_passing_summary(case_results: list[CaseResult]) -> str:
        """Brief summary of passing cases (not full detail) for context."""
        passing = [cr for cr in case_results if cr.passed]
        if not passing:
            return "(No passing cases)"

        return f"{len(passing)} case(s) passed: {', '.join(cr.case_id for cr in passing)}"

    @staticmethod
    def _extract_template(response_content: str) -> str:
        """Extract template from <revised_template> delimiters or use full content.

        Looks for content between <revised_template> and </revised_template> tags.
        If no delimiters are found, returns the entire response content stripped.
        """
        match = _TEMPLATE_RE.search(response_content)
        if match:
            return match.group(1).strip()
        return response_content.strip()
