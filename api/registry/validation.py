"""Variable validation utilities for test case creation.

Provides warn-but-allow validation: checks test case variables against
variable schema definitions, returning warning messages but never blocking
case creation.

Provides:
- validate_test_case_variables: Validate variables dict against schema list.
"""

import logging
import re
from typing import Any

from api.registry.models import VariableDefinition

logger = logging.getLogger(__name__)

# Type checking functions: var_type string -> callable that returns True if value matches
TYPE_CHECKERS: dict[str, Any] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "json": lambda v: isinstance(v, (dict, list)),
    "list": lambda v: isinstance(v, list),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}

# Constraints applicable per var_type
CONSTRAINT_APPLICABILITY: dict[str, set[str]] = {
    "string": {"min_length", "max_length", "pattern", "enum"},
    "integer": {"min", "max", "enum"},
    "float": {"min", "max"},
    "number": {"min", "max"},
    "boolean": set(),
    "json": set(),
    "list": {"min_length", "max_length"},
    "array": {"min_length", "max_length"},
    "object": set(),
}


def _check_constraint(
    var_name: str,
    value: Any,
    constraint_name: str,
    constraint_value: Any,
    var_type: str | None,
) -> list[str]:
    """Check a single constraint against a value. Returns list of warnings."""
    warnings: list[str] = []

    # Check applicability if var_type is known
    if var_type and var_type in CONSTRAINT_APPLICABILITY:
        applicable = CONSTRAINT_APPLICABILITY[var_type]
        if constraint_name not in applicable:
            warnings.append(
                f"Variable '{var_name}': constraint '{constraint_name}' "
                f"is not applicable to type '{var_type}'"
            )
            return warnings

    # Apply the constraint check
    if constraint_name == "min_length":
        if hasattr(value, "__len__") and len(value) < constraint_value:
            warnings.append(
                f"Variable '{var_name}': constraint 'min_length={constraint_value}' "
                f"violated (length={len(value)})"
            )
    elif constraint_name == "max_length":
        if hasattr(value, "__len__") and len(value) > constraint_value:
            warnings.append(
                f"Variable '{var_name}': constraint 'max_length={constraint_value}' "
                f"violated (length={len(value)})"
            )
    elif constraint_name == "pattern":
        if isinstance(value, str) and not re.search(constraint_value, value):
            warnings.append(
                f"Variable '{var_name}': constraint 'pattern={constraint_value}' violated"
            )
    elif constraint_name == "enum":
        if value not in constraint_value:
            warnings.append(
                f"Variable '{var_name}': constraint 'enum={constraint_value}' "
                f"violated (got {value!r})"
            )
    elif constraint_name == "min":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value < constraint_value:
                warnings.append(
                    f"Variable '{var_name}': constraint 'min={constraint_value}' "
                    f"violated (got {value})"
                )
    elif constraint_name == "max":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value > constraint_value:
                warnings.append(
                    f"Variable '{var_name}': constraint 'max={constraint_value}' "
                    f"violated (got {value})"
                )

    return warnings


_MAX_NESTED_DEPTH = 2


def _validate_nested(
    var_name_prefix: str,
    value: Any,
    schema: list[VariableDefinition],
    depth: int,
) -> list[str]:
    """Validate nested sub-fields against an items_schema.

    Recurses into items_schema for array elements (list of dicts) or
    object fields (dict). Stops recursion when depth >= _MAX_NESTED_DEPTH.

    Depth tracking: the top-level validate_test_case_variables passes depth=1
    for the first nesting level. Each recursion increments by 1. When depth
    reaches _MAX_NESTED_DEPTH, the function returns immediately without
    validating sub-fields (preventing infinite recursion).

    Args:
        var_name_prefix: Dot-notation prefix for warning messages (e.g. "items[0]").
        value: The value to validate (a dict for one element/object).
        schema: List of VariableDefinition sub-fields.
        depth: Current recursion depth (1-based from the top-level call).

    Returns:
        List of warning message strings.
    """
    warnings: list[str] = []
    if depth >= _MAX_NESTED_DEPTH:
        return warnings
    if not isinstance(value, dict):
        return warnings

    schema_map = {v.name: v for v in schema}

    for field_name, field_value in value.items():
        defn = schema_map.get(field_name)
        if defn is None:
            continue  # Unknown sub-fields are silently allowed in nested context

        full_name = f"{var_name_prefix}.{field_name}"

        # Type check
        if defn.var_type:
            checker = TYPE_CHECKERS.get(defn.var_type)
            if checker and not checker(field_value):
                warnings.append(
                    f"Variable '{full_name}': expected type '{defn.var_type}', "
                    f"got {type(field_value).__name__}"
                )

        # Recurse into nested items_schema if depth allows
        if defn.items_schema:
            if defn.var_type == "array" and isinstance(field_value, list):
                for idx, elem in enumerate(field_value):
                    warnings.extend(
                        _validate_nested(
                            f"{full_name}[{idx}]",
                            elem,
                            defn.items_schema,
                            depth + 1,
                        )
                    )
            elif defn.var_type == "object" and isinstance(field_value, dict):
                warnings.extend(
                    _validate_nested(
                        full_name,
                        field_value,
                        defn.items_schema,
                        depth + 1,
                    )
                )

    # Check for missing required sub-fields
    for defn in schema:
        if defn.required and defn.name not in value:
            full_name = f"{var_name_prefix}.{defn.name}"
            warnings.append(f"Required variable '{full_name}' missing")

    return warnings


def validate_test_case_variables(
    variables: dict[str, Any],
    schema: list[VariableDefinition],
) -> list[str]:
    """Validate test case variables against variable schema definitions.

    Checks for:
    - Unknown variables (not defined in schema)
    - Missing required variables
    - Type mismatches (value type vs var_type)
    - Constraint violations (min_length, max_length, pattern, enum, min, max)
    - Inapplicable constraints (e.g. min_length on integer)

    Returns a list of warning messages. Does NOT raise exceptions --
    validation is warn-but-allow per design decision.

    Args:
        variables: Dict of variable name -> value from the test case.
        schema: List of VariableDefinition objects defining the schema.

    Returns:
        List of warning message strings. Empty list means all valid.
    """
    warnings: list[str] = []
    schema_map = {v.name: v for v in schema}

    # Check each provided variable
    for var_name, var_value in variables.items():
        defn = schema_map.get(var_name)
        if defn is None:
            warnings.append(f"Variable '{var_name}' not defined in schema")
            continue

        # Type check
        if defn.var_type:
            checker = TYPE_CHECKERS.get(defn.var_type)
            if checker and not checker(var_value):
                warnings.append(
                    f"Variable '{var_name}': expected type '{defn.var_type}', "
                    f"got {type(var_value).__name__}"
                )

        # Recursive validation into items_schema for array/object types
        if defn.items_schema and defn.var_type in ("array", "object"):
            if defn.var_type == "array" and isinstance(var_value, list):
                for idx, elem in enumerate(var_value):
                    warnings.extend(
                        _validate_nested(
                            f"{var_name}[{idx}]",
                            elem,
                            defn.items_schema,
                            depth=1,
                        )
                    )
            elif defn.var_type == "object" and isinstance(var_value, dict):
                warnings.extend(
                    _validate_nested(
                        var_name,
                        var_value,
                        defn.items_schema,
                        depth=1,
                    )
                )

        # Constraint checks
        if defn.constraints:
            for constraint_name, constraint_value in defn.constraints.items():
                constraint_warnings = _check_constraint(
                    var_name, var_value, constraint_name, constraint_value, defn.var_type
                )
                warnings.extend(constraint_warnings)

    # Check for missing required variables
    for defn in schema:
        if defn.required and defn.name not in variables:
            warnings.append(f"Required variable '{defn.name}' missing")

    # Log all warnings
    for w in warnings:
        logger.warning("Variable validation: %s", w)

    return warnings
