"""TemplateRenderer: Jinja2 template rendering with variable injection.

Uses StrictUndefined to ensure missing variables raise errors instead of
silently rendering as empty strings (Pitfall 1 from research).
"""

from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

from api.exceptions import GenePrompterError


class TemplateRenderError(GenePrompterError):
    """Error raised when template rendering fails.

    Wraps Jinja2 TemplateSyntaxError and UndefinedError with a single
    exception type for simpler error handling upstream.
    """

    pass


class TemplateRenderer:
    """Renders Jinja2 templates with variable injection using StrictUndefined.

    StrictUndefined ensures that any variable referenced in the template but
    not provided in the variables dict raises an error, rather than silently
    rendering as an empty string.

    Example:
        renderer = TemplateRenderer()
        result = renderer.render(
            "Hello {{ name }}, your role is {{ role }}.",
            {"name": "Alice", "role": "admin"},
        )
        # result == "Hello Alice, your role is admin."
    """

    def __init__(self) -> None:
        self._env = Environment(undefined=StrictUndefined)

    def render(self, template_source: str, variables: dict[str, Any]) -> str:
        """Render a Jinja2 template with the given variables.

        Args:
            template_source: Jinja2 template string.
            variables: Dictionary mapping variable names to their values.

        Returns:
            The rendered template string.

        Raises:
            TemplateRenderError: If the template has invalid syntax or
                references variables not present in the variables dict.
        """
        try:
            template = self._env.from_string(template_source)
            return template.render(**variables)
        except TemplateSyntaxError as exc:
            raise TemplateRenderError(f"Invalid template syntax: {exc.message}") from exc
        except UndefinedError as exc:
            raise TemplateRenderError(f"Missing template variable: {exc.message}") from exc
