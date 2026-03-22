"""Tests for TemplateValidator: variable extraction and preservation checking."""

from api.evaluation.models import ValidationResult
from api.evaluation.validator import TemplateValidator


class TestVariableExtraction:
    """Test TemplateValidator.extract_variables."""

    def test_extract_simple_variables(self):
        validator = TemplateValidator()
        variables = validator.extract_variables("Hello {{ name }}, your role is {{ role }}.")
        assert variables == {"name", "role"}

    def test_extract_variables_with_filters(self):
        """Filters should not affect variable extraction -- {{ name | upper }} extracts 'name'."""
        validator = TemplateValidator()
        variables = validator.extract_variables("{{ name | upper }} {{ age | int }}")
        assert "name" in variables
        assert "age" in variables

    def test_extract_no_variables(self):
        validator = TemplateValidator()
        variables = validator.extract_variables("Plain text with no variables.")
        assert variables == set()

    def test_extract_variables_in_conditionals(self):
        validator = TemplateValidator()
        template = "{% if admin %}{{ name }}{% else %}{{ fallback }}{% endif %}"
        variables = validator.extract_variables(template)
        assert "admin" in variables
        assert "name" in variables
        assert "fallback" in variables

    def test_extract_variables_in_loops(self):
        validator = TemplateValidator()
        template = "{% for item in items %}{{ item.name }}{% endfor %}"
        variables = validator.extract_variables(template)
        assert "items" in variables


class TestVariablePreservation:
    """Test TemplateValidator.validate_preserved."""

    def test_all_variables_preserved(self):
        validator = TemplateValidator()
        original = "Hello {{ name }}, you are {{ role }}."
        evolved = "Welcome {{ name }}! Your role: {{ role }}. Be great."
        result = validator.validate_preserved(original, evolved)
        assert isinstance(result, ValidationResult)
        assert result.valid is True
        assert result.missing_variables == []

    def test_missing_variables_detected(self):
        validator = TemplateValidator()
        original = "{{ name }} is {{ role }} at {{ company }}."
        evolved = "{{ name }} works hard."
        result = validator.validate_preserved(original, evolved)
        assert result.valid is False
        assert "role" in result.missing_variables
        assert "company" in result.missing_variables
        assert "name" not in result.missing_variables

    def test_new_variables_allowed(self):
        """Evolved template may add new variables -- this is not flagged."""
        validator = TemplateValidator()
        original = "Hello {{ name }}."
        evolved = "Hello {{ name }}, today is {{ day }}."
        result = validator.validate_preserved(original, evolved)
        assert result.valid is True
        assert result.missing_variables == []

    def test_anchor_variables_only_checked(self):
        """When anchor_variables provided, only those are checked."""
        validator = TemplateValidator()
        original = "{{ name }} {{ role }} {{ optional_var }}"
        evolved = "{{ name }} {{ role }}"
        # Only check name and role as anchors -- optional_var loss is OK
        result = validator.validate_preserved(original, evolved, anchor_variables={"name", "role"})
        assert result.valid is True

    def test_anchor_variable_missing(self):
        """Missing anchor variable should be flagged."""
        validator = TemplateValidator()
        original = "{{ name }} {{ role }} {{ company }}"
        evolved = "{{ role }} {{ company }}"
        result = validator.validate_preserved(original, evolved, anchor_variables={"name", "role"})
        assert result.valid is False
        assert "name" in result.missing_variables
        assert "role" not in result.missing_variables

    def test_original_and_evolved_variables_populated(self):
        """ValidationResult should contain the lists of original and evolved variables."""
        validator = TemplateValidator()
        original = "{{ a }} {{ b }}"
        evolved = "{{ b }} {{ c }}"
        result = validator.validate_preserved(original, evolved)
        assert sorted(result.original_variables) == ["a", "b"]
        assert sorted(result.evolved_variables) == ["b", "c"]

    def test_empty_templates(self):
        validator = TemplateValidator()
        result = validator.validate_preserved("No variables here.", "No variables here either.")
        assert result.valid is True
        assert result.missing_variables == []


class TestRejectMissingVars:
    """Test that missing variables are clearly reported for rejection."""

    def test_clear_missing_list(self):
        validator = TemplateValidator()
        original = "{{ x }} {{ y }} {{ z }}"
        evolved = "{{ x }}"
        result = validator.validate_preserved(original, evolved)
        assert result.valid is False
        assert sorted(result.missing_variables) == ["y", "z"]


class TestRenamedVariableDetection:
    """Test detection of renamed (not just missing) variables."""

    def test_renamed_variable_detected(self):
        """business_name -> restaurant_name should be detected as rename."""
        validator = TemplateValidator()
        original = "Hello {{ business_name }}, welcome to {{ city }}."
        evolved = "Hello {{ restaurant_name }}, welcome to {{ city }}."
        result = validator.validate_preserved(original, evolved)
        assert result.valid is False
        assert "business_name" in result.missing_variables
        assert result.renamed_variables == {"business_name": "restaurant_name"}

    def test_dropped_variable_not_flagged_as_rename(self):
        """A variable dropped with no similar new var is not a rename."""
        validator = TemplateValidator()
        original = "{{ name }} {{ role }}"
        evolved = "{{ name }}"
        result = validator.validate_preserved(original, evolved)
        assert result.valid is False
        assert "role" in result.missing_variables
        assert result.renamed_variables == {}

    def test_multiple_renames_detected(self):
        """Multiple simultaneous renames detected."""
        validator = TemplateValidator()
        original = "{{ business_name }} {{ user_input }}"
        evolved = "{{ restaurant_name }} {{ customer_input }}"
        result = validator.validate_preserved(original, evolved)
        assert result.valid is False
        assert len(result.renamed_variables) == 2
        assert result.renamed_variables["business_name"] == "restaurant_name"
        assert result.renamed_variables["user_input"] == "customer_input"

    def test_no_renames_when_all_preserved(self):
        """No renames reported when template is valid."""
        validator = TemplateValidator()
        original = "{{ name }} {{ role }}"
        evolved = "{{ name }} {{ role }} {{ extra }}"
        result = validator.validate_preserved(original, evolved)
        assert result.valid is True
        assert result.renamed_variables == {}

    def test_low_similarity_not_flagged(self):
        """Dissimilar variable names should not be flagged as renames."""
        validator = TemplateValidator()
        original = "{{ x }}"
        evolved = "{{ completely_different_variable_name }}"
        result = validator.validate_preserved(original, evolved)
        assert result.valid is False
        assert result.renamed_variables == {}

    def test_renamed_variables_default_empty(self):
        """ValidationResult.renamed_variables defaults to empty dict."""
        result = ValidationResult(valid=True)
        assert result.renamed_variables == {}
