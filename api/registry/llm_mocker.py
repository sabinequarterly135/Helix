"""LLM-based tool mock response generator.

Generates realistic tool responses by prompting an LLM with format guide
examples. Supports scenario types (success, failure, edge_case) and
session-level caching to avoid redundant LLM calls.

Used as a drop-in alternative to MockMatcher when tool_mocker_mode is "llm".
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from api.gateway.protocol import LLMProvider
from api.types import ModelRole

logger = logging.getLogger(__name__)

# Scenario-specific instructions for the system prompt
_SCENARIO_INSTRUCTIONS: dict[str, str] = {
    "success": (
        "Generate a SUCCESSFUL tool response. The response should represent "
        "a normal, expected outcome where the operation completes without errors."
    ),
    "failure": (
        "Generate a FAILURE tool response. The response should represent an "
        "error condition such as: resource not found, timeout, permission denied, "
        "invalid input, or service unavailable. Use realistic error messages."
    ),
    "edge_case": (
        "Generate an EDGE CASE tool response. The response should represent "
        "an unusual but valid outcome such as: empty results, boundary values, "
        "null/missing optional fields, very large values, or unexpected but "
        "technically correct data."
    ),
}


class LLMMocker:
    """Generates mock tool responses using an LLM provider.

    Uses format guide examples as reference to produce JSON responses
    that match the expected structure. Includes session caching to
    prevent redundant LLM calls for identical inputs.

    Args:
        provider: LLMProvider instance for making LLM calls.
        model: Model name to use for generation.
    """

    def __init__(self, provider: LLMProvider, model: str) -> None:
        self._provider = provider
        self._model = model
        self._cache: dict[tuple[str, str, str], str] = {}

    async def generate_mock_response(
        self,
        tool_name: str,
        call_args: dict[str, Any],
        format_guide_examples: list[str],
        scenario_type: str = "success",
    ) -> str | None:
        """Generate a mock tool response using the LLM.

        Args:
            tool_name: Name of the tool being mocked.
            call_args: Arguments passed to the tool call.
            format_guide_examples: List of example JSON response strings.
            scenario_type: Type of scenario ("success", "failure", "edge_case").

        Returns:
            Valid JSON string matching the format guide structure, or None
            if generation fails (enabling static fallback).
        """
        cache_key = self._make_cache_key(tool_name, call_args, scenario_type)

        # Check cache first
        if cache_key in self._cache:
            logger.debug("Cache hit for %s/%s", tool_name, scenario_type)
            return self._cache[cache_key]

        # Build messages
        system_prompt = self._build_system_prompt(
            tool_name, call_args, format_guide_examples, scenario_type
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Generate a mock JSON response for tool '{tool_name}' "
                    f"with arguments: {json.dumps(call_args)}"
                ),
            },
        ]

        try:
            response = await self._provider.chat_completion(
                messages=messages,
                model=self._model,
                role=ModelRole.TOOL_MOCKER,
            )

            content = response.content
            if content is None:
                logger.warning("LLM returned None content for tool '%s'", tool_name)
                return None

            # Strip markdown code fences if present
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                # Remove first line (```json or ```) and last line (```)
                lines = [line for line in lines if not line.strip().startswith("```")]
                content = "\n".join(lines).strip()

            # Validate JSON
            json.loads(content)

            # Cache and return
            self._cache[cache_key] = content
            return content

        except json.JSONDecodeError:
            logger.warning(
                "LLM returned invalid JSON for tool '%s': %.100s",
                tool_name,
                content if "content" in dir() else "<no content>",
            )
            return None
        except Exception:
            logger.warning("LLM call failed for tool '%s'", tool_name, exc_info=True)
            return None

    async def generate_sample(
        self,
        tool_name: str,
        format_guide_examples: list[str],
        scenario_type: str = "success",
    ) -> str | None:
        """Generate a sample/preview mock response.

        Convenience method that calls generate_mock_response with empty
        call_args for previewing what the LLM would generate.

        Args:
            tool_name: Name of the tool to generate a sample for.
            format_guide_examples: List of example JSON response strings.
            scenario_type: Type of scenario ("success", "failure", "edge_case").

        Returns:
            Valid JSON string preview, or None if generation fails.
        """
        return await self.generate_mock_response(
            tool_name=tool_name,
            call_args={},
            format_guide_examples=format_guide_examples,
            scenario_type=scenario_type,
        )

    def clear_cache(self) -> None:
        """Empty the session cache, forcing new LLM calls for subsequent requests."""
        self._cache.clear()

    def _make_cache_key(
        self, tool_name: str, call_args: dict[str, Any], scenario_type: str
    ) -> tuple[str, str, str]:
        """Create a cache key from tool name, args hash, and scenario type.

        Args:
            tool_name: Name of the tool.
            call_args: Tool call arguments (hashed for key).
            scenario_type: Scenario type string.

        Returns:
            Tuple of (tool_name, args_hash, scenario_type).
        """
        args_str = json.dumps(call_args, sort_keys=True)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()
        return (tool_name, args_hash, scenario_type)

    def _build_system_prompt(
        self,
        tool_name: str,
        call_args: dict[str, Any],
        format_guide_examples: list[str],
        scenario_type: str,
    ) -> str:
        """Build the system prompt for mock response generation.

        Args:
            tool_name: Name of the tool being mocked.
            call_args: Arguments passed to the tool call.
            format_guide_examples: List of example JSON response strings.
            scenario_type: Type of scenario for generation.

        Returns:
            System prompt string.
        """
        examples_text = "\n\n".join(
            f"Example {i + 1}:\n{ex}" for i, ex in enumerate(format_guide_examples)
        )

        scenario_instruction = _SCENARIO_INSTRUCTIONS.get(
            scenario_type, _SCENARIO_INSTRUCTIONS["success"]
        )

        return (
            f"You are a tool response simulator. Your job is to generate realistic "
            f"mock JSON responses for the tool '{tool_name}'.\n\n"
            f"## Format Guide Examples\n\n"
            f"The following are example responses showing the expected JSON structure:\n\n"
            f"{examples_text}\n\n"
            f"## Scenario Type\n\n"
            f"{scenario_instruction}\n\n"
            f"## Tool Call Details\n\n"
            f"Tool: {tool_name}\n"
            f"Arguments: {json.dumps(call_args)}\n\n"
            f"## Instructions\n\n"
            f"- Return ONLY valid JSON matching the structure shown in the examples\n"
            f"- Do NOT include any explanation, markdown formatting, or code fences\n"
            f"- Match the field names and types from the examples exactly\n"
            f"- Generate realistic, varied values appropriate for the scenario type"
        )
