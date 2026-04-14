"""Renders Jinja2 templates for Veyru evaluation prompts."""

from pathlib import Path

from schmidt.template_renderer import TemplateRenderer

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_RENDERER = TemplateRenderer(prompts_dir=_PROMPTS_DIR)


def render_veyru_prompt(template_name: str, template_variables: dict[str, object]) -> str:
    """Render a named template from the Veyru evaluation prompts directory."""
    return _RENDERER.render(template_name=template_name, template_variables=template_variables)
