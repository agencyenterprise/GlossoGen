"""Renders Jinja2 templates for Salon evaluation prompts."""

from pathlib import Path

from glossogen.template_renderer import TemplateRenderer

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_RENDERER = TemplateRenderer(prompts_dirs=[_PROMPTS_DIR])


def render_salon_evaluation_prompt(
    template_name: str,
    template_variables: dict[str, object],
) -> str:
    """Render a named template from the Salon evaluation prompts directory."""
    return _RENDERER.render(template_name=template_name, template_variables=template_variables)
