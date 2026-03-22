"""MockMatcher engine for scenario-based mock response resolution.

Provides the MockMatcher class which resolves tool call arguments against
mock definitions using first-match-wins semantics with wildcard support
and Jinja2 template rendering.
"""

from __future__ import annotations

import logging
from typing import Any

from jinja2 import Template, TemplateSyntaxError, UndefinedError

from api.registry.schemas import MockDefinition

logger = logging.getLogger(__name__)


class MockMatcher:
    """Resolves tool call arguments against mock scenario definitions.

    Supports:
    - Exact argument matching
    - Wildcard "*" matching (any value, key must exist)
    - Jinja2 template rendering in response strings
    - First-match-wins ordering
    """

    @staticmethod
    def match(
        tool_name: str,
        call_args: dict[str, Any],
        mocks: list[MockDefinition],
    ) -> str | None:
        """Resolve a mock response for a tool call.

        Args:
            tool_name: The name of the tool being called.
            call_args: The arguments passed to the tool call.
            mocks: List of mock definitions to search through.

        Returns:
            Rendered response string if a matching scenario is found, None otherwise.
        """
        # Find the mock definition for this tool
        for mock_def in mocks:
            if mock_def.tool_name != tool_name:
                continue

            # Search scenarios in order (first match wins)
            for scenario in mock_def.scenarios:
                if MockMatcher._args_match(call_args, scenario.match_args):
                    return MockMatcher._render_response(scenario.response, call_args)

        return None

    @staticmethod
    def _args_match(call_args: dict[str, Any], match_args: dict[str, Any]) -> bool:
        """Check if call_args satisfy match_args constraints.

        For each key in match_args:
        - If value is "*", check that the key exists in call_args (any value).
        - Otherwise, check exact equality.

        Empty match_args matches any call_args.

        Args:
            call_args: The actual arguments from the tool call.
            match_args: The scenario's match criteria.

        Returns:
            True if all match_args constraints are satisfied.
        """
        for key, expected in match_args.items():
            if key not in call_args:
                return False
            if expected != "*" and call_args[key] != expected:
                return False
        return True

    @staticmethod
    def _render_response(template_str: str, call_args: dict[str, Any]) -> str:
        """Render a Jinja2 template string with call arguments.

        On rendering errors (UndefinedError, TemplateSyntaxError), logs a warning
        and returns the raw template string.

        Args:
            template_str: Jinja2 template string (e.g. "Hello {{ name }}").
            call_args: Arguments to substitute into the template.

        Returns:
            Rendered string, or raw template_str on error.
        """
        try:
            template = Template(template_str)
            return template.render(**call_args)
        except (UndefinedError, TemplateSyntaxError) as exc:
            logger.warning(
                "Jinja2 rendering error for template '%s': %s",
                template_str,
                exc,
            )
            return template_str
