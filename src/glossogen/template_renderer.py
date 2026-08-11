"""Shared Jinja2 template renderer.

Provides a reusable renderer that loads templates from a given directory
and renders them with explicit template variables.

Rendering is strict: a name the caller did not pass raises instead of
resolving to the empty string. Prompts are the experiment here, so the
permissive default turned a misspelled variable into a budget line with no
number and a whole ``{% if %}`` block that silently disappeared, in a prompt
that still looked plausible enough to run fifteen rounds against.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


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
            undefined=StrictUndefined,
        )

    def render(self, template_name: str, template_variables: dict[str, object]) -> str:
        """Render a named template with the given variables."""
        template = self._env.get_template(name=template_name)
        return template.render(template_variables).strip()
