"""Tests for TemplateRenderer: Jinja2 variable injection with StrictUndefined."""

import pytest

from api.evaluation.renderer import TemplateRenderError, TemplateRenderer


class TestTemplateRendering:
    """Test TemplateRenderer.render for variable injection."""

    def test_render_simple_template(self):
        renderer = TemplateRenderer()
        result = renderer.render(
            "Hello {{ name }}, welcome to {{ place }}!",
            {"name": "Alice", "place": "Wonderland"},
        )
        assert result == "Hello Alice, welcome to Wonderland!"

    def test_render_template_with_no_variables(self):
        renderer = TemplateRenderer()
        result = renderer.render("Static text with no variables.", {})
        assert result == "Static text with no variables."

    def test_render_raises_on_missing_variable(self):
        """StrictUndefined should raise TemplateRenderError when a variable is missing."""
        renderer = TemplateRenderer()
        with pytest.raises(TemplateRenderError):
            renderer.render("Hello {{ name }}", {})

    def test_render_raises_on_invalid_syntax(self):
        """Invalid Jinja2 syntax should raise TemplateRenderError."""
        renderer = TemplateRenderer()
        with pytest.raises(TemplateRenderError):
            renderer.render("Hello {{ name", {"name": "Bob"})

    def test_render_with_filters(self):
        """Templates with Jinja2 filters should work correctly."""
        renderer = TemplateRenderer()
        result = renderer.render(
            "Hello {{ name | upper }}!",
            {"name": "alice"},
        )
        assert result == "Hello ALICE!"

    def test_render_with_conditionals(self):
        renderer = TemplateRenderer()
        template = "{% if admin %}Admin: {{ name }}{% else %}User: {{ name }}{% endif %}"
        result = renderer.render(template, {"admin": True, "name": "Bob"})
        assert result == "Admin: Bob"

    def test_render_with_loop(self):
        renderer = TemplateRenderer()
        template = "{% for item in items %}{{ item }} {% endfor %}"
        result = renderer.render(template, {"items": ["a", "b", "c"]})
        assert result == "a b c "

    def test_render_multiline_template(self):
        renderer = TemplateRenderer()
        template = """You are a {{ role }}.
Your task is to help with {{ task }}.
Be {{ tone }}."""
        result = renderer.render(
            template,
            {"role": "assistant", "task": "coding", "tone": "helpful"},
        )
        assert "You are a assistant." in result
        assert "Your task is to help with coding." in result
        assert "Be helpful." in result

    def test_render_partial_missing_raises(self):
        """Even with some variables provided, missing ones should raise."""
        renderer = TemplateRenderer()
        with pytest.raises(TemplateRenderError):
            renderer.render(
                "{{ greeting }} {{ name }}",
                {"greeting": "Hi"},
            )
