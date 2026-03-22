"""Tests for registry variable validation utility (Phase 31 / PROMPT-02).

Covers:
- validate_test_case_variables() with empty inputs
- Type mismatch warnings
- Constraint violation warnings
- Unknown variable warnings
- Missing required variable warnings
- Constraint applicability warnings (inapplicable constraints)
- Passing validations (no warnings)
"""

from api.registry.models import VariableDefinition
from api.registry.validation import validate_test_case_variables


class TestValidateEmpty:
    """Test validate_test_case_variables with empty/minimal inputs."""

    def test_empty_variables_empty_schema(self):
        """Empty variables and empty schema returns empty warnings."""
        warnings = validate_test_case_variables({}, [])
        assert warnings == []

    def test_no_violations_returns_empty(self):
        """Valid variables against matching schema returns empty warnings."""
        schema = [VariableDefinition(name="x", var_type="string")]
        warnings = validate_test_case_variables({"x": "hello"}, schema)
        assert warnings == []


class TestTypeMismatch:
    """Test type mismatch detection."""

    def test_string_type_with_integer_value(self):
        """Integer value for string-typed variable produces warning."""
        schema = [VariableDefinition(name="x", var_type="string")]
        warnings = validate_test_case_variables({"x": 5}, schema)
        assert len(warnings) == 1
        assert "x" in warnings[0]
        assert "string" in warnings[0]

    def test_integer_type_with_string_value(self):
        """String value for integer-typed variable produces warning."""
        schema = [VariableDefinition(name="x", var_type="integer")]
        warnings = validate_test_case_variables({"x": "hello"}, schema)
        assert len(warnings) == 1
        assert "integer" in warnings[0]

    def test_boolean_type_with_integer_value(self):
        """Integer value for boolean-typed variable produces warning."""
        schema = [VariableDefinition(name="x", var_type="boolean")]
        warnings = validate_test_case_variables({"x": 1}, schema)
        assert len(warnings) == 1
        assert "boolean" in warnings[0]

    def test_no_var_type_skips_type_check(self):
        """Variable with no var_type skips type checking."""
        schema = [VariableDefinition(name="x")]
        warnings = validate_test_case_variables({"x": 42}, schema)
        assert warnings == []

    def test_float_type_accepts_int(self):
        """Float type accepts integer values (int is subset of float)."""
        schema = [VariableDefinition(name="x", var_type="float")]
        warnings = validate_test_case_variables({"x": 5}, schema)
        assert warnings == []

    def test_number_type_accepts_float(self):
        """Number type accepts float values."""
        schema = [VariableDefinition(name="x", var_type="number")]
        warnings = validate_test_case_variables({"x": 3.14}, schema)
        assert warnings == []

    def test_json_type_accepts_dict(self):
        """JSON type accepts dict values."""
        schema = [VariableDefinition(name="x", var_type="json")]
        warnings = validate_test_case_variables({"x": {"key": "value"}}, schema)
        assert warnings == []

    def test_json_type_accepts_list(self):
        """JSON type accepts list values."""
        schema = [VariableDefinition(name="x", var_type="json")]
        warnings = validate_test_case_variables({"x": [1, 2, 3]}, schema)
        assert warnings == []

    def test_list_type_with_string_value(self):
        """String value for list-typed variable produces warning."""
        schema = [VariableDefinition(name="x", var_type="list")]
        warnings = validate_test_case_variables({"x": "not a list"}, schema)
        assert len(warnings) == 1
        assert "list" in warnings[0]


class TestConstraintViolations:
    """Test constraint validation."""

    def test_min_length_violation(self):
        """String shorter than min_length produces warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="string",
                constraints={"min_length": 3},
            )
        ]
        warnings = validate_test_case_variables({"x": "ab"}, schema)
        assert len(warnings) == 1
        assert "min_length" in warnings[0]

    def test_max_length_violation(self):
        """String longer than max_length produces warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="string",
                constraints={"max_length": 5},
            )
        ]
        warnings = validate_test_case_variables({"x": "toolong"}, schema)
        assert len(warnings) == 1
        assert "max_length" in warnings[0]

    def test_pattern_violation(self):
        """String not matching pattern produces warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="string",
                constraints={"pattern": r"^\d{3}$"},
            )
        ]
        warnings = validate_test_case_variables({"x": "abc"}, schema)
        assert len(warnings) == 1
        assert "pattern" in warnings[0]

    def test_pattern_passes(self):
        """String matching pattern produces no warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="string",
                constraints={"pattern": r"^\d{3}$"},
            )
        ]
        warnings = validate_test_case_variables({"x": "123"}, schema)
        assert warnings == []

    def test_enum_violation_string(self):
        """String not in enum list produces warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="string",
                constraints={"enum": ["a", "b", "c"]},
            )
        ]
        warnings = validate_test_case_variables({"x": "d"}, schema)
        assert len(warnings) == 1
        assert "enum" in warnings[0]

    def test_enum_passes(self):
        """String in enum list produces no warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="string",
                constraints={"enum": ["a", "b", "c"]},
            )
        ]
        warnings = validate_test_case_variables({"x": "a"}, schema)
        assert warnings == []

    def test_min_violation_number(self):
        """Number below min produces warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="integer",
                constraints={"min": 10},
            )
        ]
        warnings = validate_test_case_variables({"x": 5}, schema)
        assert len(warnings) == 1
        assert "min" in warnings[0]

    def test_max_violation_number(self):
        """Number above max produces warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="integer",
                constraints={"max": 100},
            )
        ]
        warnings = validate_test_case_variables({"x": 150}, schema)
        assert len(warnings) == 1
        assert "max" in warnings[0]

    def test_min_max_passes(self):
        """Number within min/max range produces no warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="integer",
                constraints={"min": 1, "max": 100},
            )
        ]
        warnings = validate_test_case_variables({"x": 50}, schema)
        assert warnings == []

    def test_string_passes_all_constraints(self):
        """String satisfying min_length, max_length, pattern produces no warnings."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="string",
                constraints={"min_length": 3, "max_length": 10, "pattern": r"^hello"},
            )
        ]
        warnings = validate_test_case_variables({"x": "hello"}, schema)
        assert warnings == []

    def test_enum_violation_number(self):
        """Number not in enum list produces warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="integer",
                constraints={"enum": [1, 2, 3]},
            )
        ]
        warnings = validate_test_case_variables({"x": 5}, schema)
        assert len(warnings) == 1
        assert "enum" in warnings[0]


class TestConstraintApplicability:
    """Test inapplicable constraint warnings."""

    def test_min_length_on_integer_warns(self):
        """min_length constraint on integer type produces inapplicability warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="integer",
                constraints={"min_length": 3},
            )
        ]
        warnings = validate_test_case_variables({"x": 42}, schema)
        assert len(warnings) >= 1
        assert any("not applicable" in w.lower() or "inapplicable" in w.lower() for w in warnings)

    def test_min_max_on_string_warns(self):
        """min/max constraints on string type produces inapplicability warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="string",
                constraints={"min": 5},
            )
        ]
        warnings = validate_test_case_variables({"x": "hello"}, schema)
        assert len(warnings) >= 1
        assert any("not applicable" in w.lower() or "inapplicable" in w.lower() for w in warnings)


class TestUnknownVariables:
    """Test detection of variables not defined in schema."""

    def test_unknown_variable_warns(self):
        """Variable not in schema produces 'not defined' warning."""
        schema = [VariableDefinition(name="x", required=False)]
        warnings = validate_test_case_variables({"unknown": 1}, schema)
        assert len(warnings) == 1
        assert "unknown" in warnings[0]
        assert "not defined" in warnings[0].lower()


class TestMissingRequired:
    """Test detection of missing required variables."""

    def test_missing_required_warns(self):
        """Missing required variable produces warning."""
        schema = [VariableDefinition(name="x", required=True)]
        warnings = validate_test_case_variables({}, schema)
        assert len(warnings) == 1
        assert "x" in warnings[0]
        assert "required" in warnings[0].lower() or "missing" in warnings[0].lower()

    def test_missing_optional_no_warning(self):
        """Missing optional variable produces no warning."""
        schema = [VariableDefinition(name="x", required=False)]
        warnings = validate_test_case_variables({}, schema)
        assert warnings == []

    def test_multiple_issues(self):
        """Multiple violations produce multiple warnings."""
        schema = [
            VariableDefinition(name="x", required=True, var_type="string"),
            VariableDefinition(name="y", required=True, var_type="integer"),
        ]
        # x missing, y has wrong type, z is unknown
        warnings = validate_test_case_variables({"y": "not-an-int", "z": 1}, schema)
        assert len(warnings) >= 3  # missing x, type mismatch y, unknown z


class TestListConstraints:
    """Test constraints applied to list types."""

    def test_list_min_length(self):
        """List shorter than min_length produces warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="list",
                constraints={"min_length": 3},
            )
        ]
        warnings = validate_test_case_variables({"x": [1]}, schema)
        assert len(warnings) == 1
        assert "min_length" in warnings[0]

    def test_list_max_length(self):
        """List longer than max_length produces warning."""
        schema = [
            VariableDefinition(
                name="x",
                var_type="list",
                constraints={"max_length": 2},
            )
        ]
        warnings = validate_test_case_variables({"x": [1, 2, 3]}, schema)
        assert len(warnings) == 1
        assert "max_length" in warnings[0]


# -- Phase 45: Nested variable type validation --


class TestArrayAndObjectTypeCheckers:
    """Test 'array' and 'object' type checker entries."""

    def test_array_type_accepts_list(self):
        """'array' type checker: isinstance(v, list) returns True for lists."""
        schema = [VariableDefinition(name="x", var_type="array")]
        warnings = validate_test_case_variables({"x": [1, 2, 3]}, schema)
        assert warnings == []

    def test_array_type_rejects_dict(self):
        """'array' type checker rejects dicts."""
        schema = [VariableDefinition(name="x", var_type="array")]
        warnings = validate_test_case_variables({"x": {"a": 1}}, schema)
        assert len(warnings) == 1
        assert "array" in warnings[0]

    def test_object_type_accepts_dict(self):
        """'object' type checker: isinstance(v, dict) returns True for dicts."""
        schema = [VariableDefinition(name="x", var_type="object")]
        warnings = validate_test_case_variables({"x": {"key": "val"}}, schema)
        assert warnings == []

    def test_object_type_rejects_list(self):
        """'object' type checker rejects lists."""
        schema = [VariableDefinition(name="x", var_type="object")]
        warnings = validate_test_case_variables({"x": [1, 2]}, schema)
        assert len(warnings) == 1
        assert "object" in warnings[0]


class TestRecursiveNestedValidation:
    """Test recursive validation into items_schema."""

    def test_array_with_items_schema_validates_elements(self):
        """Array variable with items_schema validates each element's fields against sub-schema, returns warnings for type mismatches."""
        schema = [
            VariableDefinition(
                name="items",
                var_type="array",
                items_schema=[
                    VariableDefinition(name="name", var_type="string"),
                    VariableDefinition(name="qty", var_type="integer"),
                ],
            )
        ]
        # Second element has wrong type for 'qty'
        warnings = validate_test_case_variables(
            {"items": [{"name": "apple", "qty": 3}, {"name": "banana", "qty": "five"}]},
            schema,
        )
        assert len(warnings) >= 1
        assert any("items[1].qty" in w for w in warnings)
        assert any("integer" in w for w in warnings)

    def test_object_with_items_schema_validates_fields(self):
        """Object variable with items_schema validates sub-field values against sub-schema, returns warnings for missing required sub-fields."""
        schema = [
            VariableDefinition(
                name="address",
                var_type="object",
                items_schema=[
                    VariableDefinition(name="street", var_type="string", required=True),
                    VariableDefinition(name="city", var_type="string", required=True),
                ],
            )
        ]
        # Missing 'city'
        warnings = validate_test_case_variables(
            {"address": {"street": "123 Main St"}},
            schema,
        )
        assert len(warnings) >= 1
        assert any("address.city" in w for w in warnings)

    def test_depth_cap_at_2_levels(self):
        """Recursive validation: max 2 levels deep -- items_schema within items_schema validated but their items_schema not recursed further."""
        inner_inner = VariableDefinition(
            name="deep_field",
            var_type="string",
        )
        inner = VariableDefinition(
            name="nested",
            var_type="object",
            items_schema=[inner_inner],
        )
        outer = VariableDefinition(
            name="top",
            var_type="object",
            items_schema=[inner],
        )
        # depth 0: top -> depth 1: nested -> depth 2: deep_field (should NOT recurse)
        # Provide a bad value at depth 2 -- it should NOT be caught since we cap at 2
        warnings = validate_test_case_variables(
            {"top": {"nested": {"deep_field": 123}}},  # 123 is wrong type for string
            [outer],
        )
        # The depth-2 field should not be validated (depth cap), so no warning about deep_field
        assert not any("deep_field" in w for w in warnings)

    def test_non_nested_array_no_recursion(self):
        """Non-nested array without items_schema: only type-checks the top-level value, no recursion."""
        schema = [VariableDefinition(name="tags", var_type="array")]
        warnings = validate_test_case_variables({"tags": ["a", "b", "c"]}, schema)
        assert warnings == []

    def test_non_nested_object_no_recursion(self):
        """Non-nested object without items_schema: only type-checks the top-level value, no recursion."""
        schema = [VariableDefinition(name="meta", var_type="object")]
        warnings = validate_test_case_variables({"meta": {"key": "val"}}, schema)
        assert warnings == []

    def test_warn_but_allow_preserved(self):
        """Warn-but-allow pattern preserved: all validation returns warnings, never raises."""
        schema = [
            VariableDefinition(
                name="items",
                var_type="array",
                items_schema=[
                    VariableDefinition(name="x", var_type="integer", required=True),
                ],
            )
        ]
        # Everything is wrong: not a list at all
        warnings = validate_test_case_variables({"items": "not-a-list"}, schema)
        # Should get type mismatch warning but not raise
        assert len(warnings) >= 1
        assert any("array" in w for w in warnings)

    def test_array_element_type_mismatch_dot_notation(self):
        """Nested warnings use dot-notation prefix: 'items[0].name'."""
        schema = [
            VariableDefinition(
                name="items",
                var_type="array",
                items_schema=[
                    VariableDefinition(name="name", var_type="string"),
                ],
            )
        ]
        warnings = validate_test_case_variables(
            {"items": [{"name": 123}]},
            schema,
        )
        assert len(warnings) >= 1
        assert any("items[0].name" in w for w in warnings)
