"""Shared Jinja2 template renderer.

Provides a reusable renderer that loads templates from a given directory
and renders them with explicit template variables.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


class TemplateRenderer:
    """Renders Jinja2 templates from one or more directories.

    Templates and Jinja ``{% include %}`` partials are resolved by searching
    the directories in the order provided. This lets one renderer draw from
    a primary template set plus shared partials in a sibling directory.
    """

    def __init__(self, prompts_dirs: list[Path]) -> None:
        self._env = Environment(
            loader=FileSystemLoader([str(path) for path in prompts_dirs]),
            autoescape=False,
            keep_trailing_newline=False,
        )

    def render(self, template_name: str, template_variables: dict[str, object]) -> str:
        """Render a named template with the given variables."""
        template = self._env.get_template(name=template_name)
        return template.render(template_variables).strip()
