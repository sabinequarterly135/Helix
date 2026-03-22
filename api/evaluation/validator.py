"""TemplateValidator: variable extraction and preservation checking.

Uses jinja2.Environment.parse() + jinja2.meta.find_undeclared_variables() for
reliable variable extraction, including variables used with filters (e.g.,
{{ name | upper }} correctly extracts "name").

Same pattern used by PromptRegistry._extract_variables in the registry package.
"""

import difflib

from jinja2 import Environment, meta

from api.evaluation.models import ValidationResult


class TemplateValidator:
    """Validates that evolved templates preserve required variables.

    Provides two core operations:
    1. extract_variables: Find all variable names in a Jinja2 template.
    2. validate_preserved: Check that an evolved template preserves all
       required variables from the original.

    Example:
        validator = TemplateValidator()
        result = validator.validate_preserved(
            original_template="Hello {{ name }}, role: {{ role }}.",
            evolved_template="Welcome {{ name }}!",
        )
        # result.valid == False, result.missing_variables == ["role"]
    """

    def __init__(self) -> None:
        self._env = Environment()

    def extract_variables(self, template_source: str) -> set[str]:
        """Extract all variable names from a Jinja2 template.

        Uses Environment.parse() + meta.find_undeclared_variables() which
        correctly handles variables with filters ({{ name | upper }} extracts
        "name"), conditionals, and loops.

        Args:
            template_source: Jinja2 template string.

        Returns:
            Set of variable names found in the template.
        """
        ast = self._env.parse(template_source)
        return meta.find_undeclared_variables(ast)

    @staticmethod
    def _detect_renames(
        missing: list[str],
        new_vars: set[str],
    ) -> dict[str, str]:
        """Detect likely variable renames (missing -> new with similar name).

        Uses difflib.SequenceMatcher with a 0.5 similarity threshold.
        Each new variable can only be matched to one missing variable.

        Args:
            missing: Variables that are required but absent from evolved template.
            new_vars: Variables present in evolved but not in original template.

        Returns:
            Dict mapping missing_var -> likely_new_var.
        """
        renames: dict[str, str] = {}
        remaining_new = set(new_vars)

        for missing_var in missing:
            best_match = None
            best_ratio = 0.0

            for new_var in remaining_new:
                ratio = difflib.SequenceMatcher(None, missing_var, new_var).ratio()
                if ratio > best_ratio and ratio >= 0.5:
                    best_ratio = ratio
                    best_match = new_var

            if best_match is not None:
                renames[missing_var] = best_match
                remaining_new.discard(best_match)

        return renames

    def validate_preserved(
        self,
        original_template: str,
        evolved_template: str,
        anchor_variables: set[str] | None = None,
    ) -> ValidationResult:
        """Validate that an evolved template preserves required variables.

        If anchor_variables is provided, only those specific variables are
        checked for preservation. Otherwise, all variables from the original
        template are required to be present in the evolved template.

        New variables in the evolved template are allowed and not flagged.

        Args:
            original_template: The original Jinja2 template.
            evolved_template: The evolved Jinja2 template to validate.
            anchor_variables: Optional set of variable names that must be
                preserved. If None, all original variables are required.

        Returns:
            ValidationResult with valid flag, missing variables list,
            and the full variable sets from both templates.
        """
        original_vars = self.extract_variables(original_template)
        evolved_vars = self.extract_variables(evolved_template)

        # Determine which variables must be preserved
        required_vars = anchor_variables if anchor_variables is not None else original_vars

        # Find missing required variables
        missing = sorted(required_vars - evolved_vars)

        # Detect likely renames: new vars in evolved that are similar to missing vars
        renamed: dict[str, str] = {}
        if missing:
            new_vars = evolved_vars - original_vars
            renamed = self._detect_renames(missing, new_vars)

        return ValidationResult(
            valid=len(missing) == 0,
            missing_variables=missing,
            original_variables=sorted(original_vars),
            evolved_variables=sorted(evolved_vars),
            renamed_variables=renamed,
        )
