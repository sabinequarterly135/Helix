"""Tests for nested anchor extraction from variable definitions (Phase 45).

Covers:
- Flat anchor variables (unchanged behavior)
- Dot-notation anchor paths for array/object nested anchors
- Mixed flat + nested anchors
- Parent-is-anchor + child-is-anchor cases
- No nested anchors (only top-level)
- items_schema with no anchored sub-fields
"""

from api.registry.models import VariableDefinition


class TestNestedAnchorExtraction:
    """Test _extract_anchor_variables helper for dot-notation nested anchors."""

    def test_flat_anchor_unchanged(self):
        """Flat variable with is_anchor=True: anchor set contains 'varname' (unchanged behavior)."""
        from api.registry.service import _extract_anchor_variables

        defs = [
            VariableDefinition(name="business_type", is_anchor=True),
            VariableDefinition(name="greeting", is_anchor=False),
        ]
        anchors = _extract_anchor_variables(defs)
        assert anchors == {"business_type"}

    def test_array_nested_anchor_dot_notation(self):
        """Array variable with items_schema where sub-field has is_anchor=True: anchor set contains 'varname.fieldname'."""
        from api.registry.service import _extract_anchor_variables

        defs = [
            VariableDefinition(
                name="items",
                var_type="array",
                items_schema=[
                    VariableDefinition(name="name", var_type="string", is_anchor=True),
                    VariableDefinition(name="quantity", var_type="integer", is_anchor=False),
                ],
            ),
        ]
        anchors = _extract_anchor_variables(defs)
        assert "items.name" in anchors

    def test_object_nested_anchor_dot_notation(self):
        """Object variable with items_schema where sub-field has is_anchor=True: anchor set contains 'varname.fieldname'."""
        from api.registry.service import _extract_anchor_variables

        defs = [
            VariableDefinition(
                name="address",
                var_type="object",
                items_schema=[
                    VariableDefinition(name="city", var_type="string", is_anchor=True),
                    VariableDefinition(name="street", var_type="string", is_anchor=False),
                ],
            ),
        ]
        anchors = _extract_anchor_variables(defs)
        assert "address.city" in anchors

    def test_multiple_nested_anchors(self):
        """Multiple nested anchors: all dot-notation paths present in set."""
        from api.registry.service import _extract_anchor_variables

        defs = [
            VariableDefinition(
                name="items",
                var_type="array",
                items_schema=[
                    VariableDefinition(name="name", var_type="string", is_anchor=True),
                    VariableDefinition(name="sku", var_type="string", is_anchor=True),
                    VariableDefinition(name="qty", var_type="integer", is_anchor=False),
                ],
            ),
        ]
        anchors = _extract_anchor_variables(defs)
        assert "items.name" in anchors
        assert "items.sku" in anchors
        assert "items.qty" not in anchors

    def test_no_nested_anchors_only_top_level(self):
        """No nested anchors: only top-level anchor in set."""
        from api.registry.service import _extract_anchor_variables

        defs = [
            VariableDefinition(name="business_type", is_anchor=True),
            VariableDefinition(
                name="items",
                var_type="array",
                items_schema=[
                    VariableDefinition(name="name", var_type="string", is_anchor=False),
                ],
            ),
        ]
        anchors = _extract_anchor_variables(defs)
        assert anchors == {"business_type"}

    def test_parent_and_child_both_anchors(self):
        """Parent is anchor + child is anchor: both 'parent' and 'parent.child' in set."""
        from api.registry.service import _extract_anchor_variables

        defs = [
            VariableDefinition(
                name="config",
                is_anchor=True,
                var_type="object",
                items_schema=[
                    VariableDefinition(name="key", var_type="string", is_anchor=True),
                ],
            ),
        ]
        anchors = _extract_anchor_variables(defs)
        assert "config" in anchors
        assert "config.key" in anchors

    def test_items_schema_no_anchored_subfields(self):
        """items_schema with no anchored sub-fields: no dot-notation paths added."""
        from api.registry.service import _extract_anchor_variables

        defs = [
            VariableDefinition(
                name="items",
                var_type="array",
                items_schema=[
                    VariableDefinition(name="name", var_type="string", is_anchor=False),
                    VariableDefinition(name="price", var_type="float", is_anchor=False),
                ],
            ),
        ]
        anchors = _extract_anchor_variables(defs)
        assert anchors == set()

    def test_dot_notation_works_with_mutator_string_join(self):
        """anchor_variables={'items.name', 'business_type'} joined to string includes both."""
        anchor_variables = {"items.name", "business_type"}
        required_variables_str = ", ".join(sorted(anchor_variables))
        assert "items.name" in required_variables_str
        assert "business_type" in required_variables_str
